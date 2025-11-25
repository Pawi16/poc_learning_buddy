import time
from typing import List
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama

# --- 1. DEFINE THE BLUEPRINT ---
class TopicPlan(BaseModel):
    title: str = Field(..., description="The title of the topic")
    description: str = Field(..., description="A 1-sentence description of what this topic covers")

class ModulePlan(BaseModel):
    title: str = Field(..., description="A concise title for the module based on the file content")
    overview: str = Field(..., description="A high-level summary of the entire module (2-3 sentences)")
    topics: List[TopicPlan] = Field(..., description="List of 5-10 logical topics extracted from the text")

# --- 2. SETUP LOCAL LLM ---
llm = ChatOllama(
    model="llama3", 
    temperature=0, 
    format="json" 
)

def create_module_from_markdown():
    # A. READ THE PREPARED MARKDOWN FILE
    # This assumes you ran poc_01 or created this file manually
    source_file = "data/md/extracted_text.md" 
    
    print(f"📖 Reading text from {source_file}...")
    
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            markdown_text = f.read()
    except FileNotFoundError:
        print(f"❌ Error: File '{source_file}' not found.")
        print("   Please run poc_01 first or create the file manually.")
        return

    print(f"✅ Loaded {len(markdown_text)} characters.")

    # B. GENERATE STRUCTURE
    print("🧠 Generating Module Structure (Local Llama 3)...")
    start_time = time.time()
    
    # Bind the Pydantic model to the LLM
    structured_llm = llm.with_structured_output(ModulePlan)

    # Run the chain
    # We slice [:30000] to ensure we don't overflow the local model's context context
    module_plan = structured_llm.invoke(
        f"Analyze the following text and create a structured learning module.\n\nTEXT:\n{markdown_text[:30000]}"
    )

    end_time = time.time()
    
    # C. PRINT RESULTS
    if module_plan:
        print("\n" + "="*50)
        print(f"📦 MODULE: {module_plan.title}")
        print(f"📝 OVERVIEW: {module_plan.overview}")
        print("="*50)
        
        for i, topic in enumerate(module_plan.topics):
            print(f"\n🔹 TOPIC {i+1}: {topic.title}")
            print(f"   {topic.description}")

        print("\n" + "="*50)
        print(f"✅ Success! Generated in {end_time - start_time:.2f} seconds.")
    else:
        print("❌ Failed to generate structure.")

if __name__ == "__main__":
    create_module_from_markdown()