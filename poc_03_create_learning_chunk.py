import re
import json
from typing import List, Dict
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama

# --- 1. DATA MODELS (tuned for "Exam Notes") ---

class ConceptNote(BaseModel):
    title: str = Field(..., description="Concept Title (e.g., 'Packet Switching')")
    # Changed description to ask for specific note-taking format
    note_content: str = Field(..., description="Exam-style notes. Use bullet points, bold keywords, and short sentences. Focus on definitions and key differences.")
    importance_level: str = Field(..., description="High/Medium/Low based on how likely it is to be on an exam.")

class TopicNotes(BaseModel):
    chunks: List[ConceptNote] = Field(..., description="List of key concepts found in this section.")

# --- 2. PYTHON SPLITTER (The "Table of Contents" Reader) ---

def parse_markdown_sections(markdown_text: str) -> List[Dict[str, str]]:
    """
    Robustly splits markdown by '## ' headers to get logical sections.
    """
    # Regex to find headers like '## 1.1 What Is the Internet?'
    pattern = re.compile(r'(^|\n)##\s+(.+)\n')
    matches = list(pattern.finditer(markdown_text))
    
    sections = []
    if not matches:
        return [{"title": "Full Document", "content": markdown_text}]

    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(markdown_text)
        content = markdown_text[start:end].strip()
        
        # Only keep sections with actual content
        if len(content) > 200: 
            sections.append({"title": title, "content": content})
        
    return sections

# --- 3. MAIN SCRIPT ---

llm = ChatOllama(model="llama3", temperature=0.1, num_ctx=8192)

def generate_exam_notes():
    source_file = "data/md/extracted_text.md"
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            context_text = f.read()
    except FileNotFoundError:
        print("❌ File not found.")
        return

    # 1. STRUCTURE (Python does the hard work)
    print("\n📚 Phase 1: Scanning Chapters (Python)...")
    topics = parse_markdown_sections(context_text)
    
    # Filter out homework/junk sections automatically
    valid_topics = [t for t in topics if "problem" not in t['title'].lower() and "review" not in t['title'].lower()]
    
    print(f"   Found {len(valid_topics)} study topics.")

    # 2. SUMMARIZATION (AI acts as the Buddy)
    print("\n📝 Phase 2: Writing Exam Notes...")
    
    final_notes = []

    writer_llm = llm.with_structured_output(TopicNotes)

    for index, topic in enumerate(valid_topics): 
        print(f"   > Taking notes on: {topic['title']}...", end="", flush=True)
        
        # Prompt explicitly asks for "Student Note Style"
        note_data = writer_llm.invoke(f"""
            You are a Computer Science student preparing for a final exam.
            Your goal is to summarize the text below into **High-Quality Study Notes**.
            
            TOPIC: {topic['title']}
            SOURCE TEXT:
            {topic['content'][:12000]} 
            
            INSTRUCTIONS:
            1. Extract the core concepts.
            2. **Style:** Use Bullet points (•), **Bold** for terminology, and keep it concise.
            3. **Focus:** identifying Definitions, Pros/Cons, and Processes.
            4. If there is a comparison (e.g., A vs B), make it clear.
            
            OUTPUT FORMAT:
            Create a list of 'ConceptNote' objects.
        """)

        final_notes.append({
            "section_title": topic['title'],
            "notes": [note.model_dump() for note in note_data.chunks]
        })
        
        print(" Done.")

    # 3. SAVE
    with open("data/exam_prep_notes.json", "w", encoding="utf-8") as f:
        json.dump(final_notes, f, indent=2, ensure_ascii=False)

    print("\n✅ Exam Notes Generated!")

if __name__ == "__main__":
    generate_exam_notes()
    