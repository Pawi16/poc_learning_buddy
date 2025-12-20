import json
import numpy as np
from langchain_ollama import ChatOllama
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from pydantic import BaseModel, Field
from typing import List

# --- 1. SETUP MODELS ---
llm = ChatOllama(model="llama3", temperature=0.1)
embedder = SentenceTransformer('all-MiniLM-L6-v2') 

# --- 2. THE SEMANTIC SPLITTER ---
def split_text_semantically(text: str, threshold: float = 0.45) -> List[str]:
    print("   ...Calculating semantic vectors...")
    
    # Clean and split into sentences
    sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if len(s) > 10]
    
    if not sentences:
        return []

    # Convert sentences to Vectors
    embeddings = embedder.encode(sentences)

    # Calculate similarity
    similarities = []
    for i in range(len(embeddings) - 1):
        sim = cosine_similarity([embeddings[i]], [embeddings[i+1]])[0][0]
        similarities.append(sim)

    # Cut text at "Deep Valleys"
    chunks = []
    current_chunk = [sentences[0]]
    
    for i in range(len(similarities)):
        if similarities[i] < threshold:
            chunks.append(". ".join(current_chunk) + ".")
            current_chunk = [sentences[i+1]]
        else:
            current_chunk.append(sentences[i+1])
            
    if current_chunk:
        chunks.append(". ".join(current_chunk) + ".")
        
    return chunks

# --- 3. DATA MODELS ---
class ConceptNote(BaseModel):
    concept_name: str = Field(..., description="Name of the concept identified.")
    explanation: str = Field(..., description="Clear, study-buddy style explanation.")

class ChunkSummary(BaseModel):
    topics: List[ConceptNote] = Field(..., description="List of concepts found in this chunk.")

# --- 4. MAIN PIPELINE ---
def generate_notes_from_messy_text():
    source_file = "data/md/extracted_text.md"
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            # Using 30k chars to test a decent chunk of the file
            full_text = f.read()[:30000] 
    except FileNotFoundError:
        print("❌ File not found.")
        return

    # STEP 1: SPLIT
    print("\n🔪 Phase 1: Semantic Chunking...")
    chunks = split_text_semantically(full_text, threshold=0.45) 
    print(f"\n📦 Created {len(chunks)} chunks.")

    # 🔍 DEBUG SAVE: Save the raw chunks to inspect them
    debug_data = {
        "total_chunks": len(chunks),
        "chunks": chunks
    }
    with open("data/debug_semantic_chunks.json", "w", encoding="utf-8") as f:
        json.dump(debug_data, f, indent=2, ensure_ascii=False)
    print("   -> 🐛 Debug file saved: 'data/debug_semantic_chunks.json'")

    # STEP 2: GENERATE NOTES
    print("\n🧠 Phase 2: Generating Study Notes...")
    final_notes = []
    writer_llm = llm.with_structured_output(ChunkSummary)

    # Processing first 3 chunks for demo speed
    for i, chunk_text in enumerate(chunks[:3]):
        if len(chunk_text) < 200: continue
        
        print(f"   > Analyzing Chunk {i+1} ({len(chunk_text)} chars)...", end="", flush=True)
        try:
            response = writer_llm.invoke(f"""
                You are a Study Buddy. 
                Read this text segment (grouped by semantic similarity).
                
                TEXT: {chunk_text}
                
                TASK: Identify main concepts and write bullet notes.
            """)
            
            final_notes.append({
                "chunk_id": i+1,
                "raw_chunk_preview": chunk_text[:100] + "...", # Preview in final file too
                "extracted_concepts": [n.model_dump() for n in response.topics]
            })
            print(" Done.")
        except Exception as e:
            print(f" Error: {e}")

    # SAVE FINAL NOTES
    with open("data/semantic_notes.json", "w", encoding="utf-8") as f:
        json.dump(final_notes, f, indent=2, ensure_ascii=False)

    print("\n✅ Saved to data/semantic_notes.json")

if __name__ == "__main__":
    generate_notes_from_messy_text()