import time
import json
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from typing import List

# --- 1. CONFIGURATION ---
# We try to give it a fighting chance by increasing the context window to 32k tokens.
# Standard Llama 3 is 8k. Qwen 2.5 supports up to 128k, but 32k is a safe local limit.
llm = ChatOllama(
    model="qwen2.5:14b", 
    temperature=0,
    num_ctx=32768  # Attempt to fit ~25,000 words
)

# --- 2. DATA MODELS (Target Output) ---
class ConceptNote(BaseModel):
    title: str = Field(..., description="Concept name")
    details: str = Field(..., description="Definition and key points")

class TopicSection(BaseModel):
    topic_name: str = Field(..., description="Name of the section/item (e.g. 'Item 1')")
    notes: List[ConceptNote] = Field(..., description="List of notes for this specific topic")

class FullStudyGuide(BaseModel):
    all_topics: List[TopicSection] = Field(..., description="List of ALL topics found in the text.")

# --- 3. THE "NAIVE" GENERATOR ---
def generate_notes_naive(markdown_file, output_file):
    print(f"📖 Reading raw text from: {markdown_file}...")
    
    try:
        with open(markdown_file, "r", encoding="utf-8") as f:
            full_text = f.read()
    except FileNotFoundError:
        print(f"❌ Error: Could not find {markdown_file}. Please ensure you have the raw text.")
        return

    # METRICS
    char_count = len(full_text)
    est_tokens = char_count / 4  # Rough estimate
    
    print(f"📊 Statistics:")
    print(f"   - Characters: {char_count}")
    print(f"   - Est. Tokens: {int(est_tokens)}")
    
    # WARNING SYSTEM
    limit = 30000 # Safety limit for context
    input_text = full_text
    
    if est_tokens > limit:
        print(f"⚠️  WARNING: Text is too long for one prompt!")
        print(f"   - Truncating to first {limit} tokens to prevent crash.")
        # Rough cut to fit context
        input_text = full_text[:(limit * 4)] 
        print(f"   - ✂️  LOST CONTENT: {char_count - len(input_text)} characters ignored.")
    else:
        print("   - ✅ Text fits within context window (mostly).")

    print("\n🧠 Sending Massive Prompt to AI (One-Shot)...")
    print("   (This may take a while...)")
    
    start_time = time.time()
    
    prompt = f"""
    You are a student preparing for a final exam.
    Analyze the following Textbook Content and extract **ALL** study topics.
    
    SOURCE TEXT:
    {input_text}
    
    INSTRUCTIONS:
    1. Identify every distinct 'Item', 'Section', or 'Chapter'.
    2. For EACH topic, create a list of detailed concept notes.
    3. **Do not summarize the whole book into one paragraph.** Break it down.
    4. Be as comprehensive as possible.
    
    OUTPUT FORMAT:
    Return a JSON object with a list of 'all_topics'.
    """

    try:
        # We ask for the Full Study Guide in one go
        response = llm.with_structured_output(FullStudyGuide).invoke(prompt)
        
        duration = time.time() - start_time
        topic_count = len(response.all_topics)
        
        print("\n" + "="*60)
        print(f"✅ GENERATION COMPLETE ({duration:.2f}s)")
        print(f"   - Topics Found: {topic_count}")
        print("="*60)

        # Print Preview
        for t in response.all_topics[:5]:
            print(f"   🔹 {t.topic_name} ({len(t.notes)} notes)")
        if topic_count > 5: print("   ... (more)")

        # Save
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(response.dict(), f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        print("   -> This usually happens because the output was too long for the model to finish.")

# --- MAIN ---
if __name__ == "__main__":
    # Ensure this file exists! 
    # If you don't have a markdown file, rename your .pdf to .txt or export it.
    input_md = "data/md/extracted_text.md" 
    output_json = "data/naive_one_shot_notes.json"
    
    generate_notes_naive(input_md, output_json)