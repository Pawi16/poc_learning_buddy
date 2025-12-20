import pdfplumber
import json
import re
from collections import defaultdict
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from typing import List

# --- 1. SETUP ---
llm = ChatOllama(model="llama3", temperature=0)

# --- 2. DATA MODELS ---
class HeaderAnalysis(BaseModel):
    header_font_sizes: List[float] = Field(..., description="List of font sizes that act as headers. e.g. [24.0, 18.5]")
    reasoning: str = Field(..., description="Why you chose these sizes.")

# --- 3. LOGIC FILTERS (The Safety Net) ---
def clean_text(text):
    text = re.sub(r'\(cid:\d+\)', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def is_valid_header(text, top, page_height, font_size, header_sizes):
    """
    Final check: Even if the LLM says this font size is a header,
    we must ensure it's not a Page Number or Caption.
    """
    text_clean = clean_text(text).lower()

    # 1. Check if size matches what LLM selected (Allow 0.1 float tolerance)
    is_llm_selected = any(abs(font_size - h) < 0.2 for h in header_sizes)
    if not is_llm_selected:
        return False

    # 2. Geometry Rule (Ignore header/footer margins)
    if top < (page_height * 0.08) or top > (page_height * 0.90):
        return False

    # 3. Content Rules (No Captions, No Digits)
    if text_clean.startswith("figure") or text_clean.startswith("table") or text_clean.startswith("fig"):
        return False
    if re.match(r'^\d+$', text_clean): # Page numbers like "12"
        return False
    
    return True

# --- 4. STEP 1: SCAN PDF & PREPARE STATS ---
def scan_pdf_structure(pdf_path):
    print(f"🔍 Scanning PDF: {pdf_path}...")
    
    font_stats = defaultdict(lambda: {'count': 0, 'total_chars': 0, 'examples': []})
    all_lines = [] 

    with pdfplumber.open(pdf_path) as pdf:
        # Scan first 20 pages for pattern analysis
        for i, page in enumerate(pdf.pages):
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue

            # Group words to lines
            current_line = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line[-1]['top']) < 5:
                    current_line.append(word)
                else:
                    record_line(current_line, font_stats, all_lines, page.height)
                    current_line = [word]
            record_line(current_line, font_stats, all_lines, page.height)
            
            if i == 20: break # Stop scanning stats after 20 pages (efficiency)
            
        # Continue reading remaining pages just for content (skip stats)
        for page in pdf.pages[21:]:
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue
            current_line = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line[-1]['top']) < 5:
                    current_line.append(word)
                else:
                    # We store line but don't update stats map
                    record_line_content_only(current_line, all_lines, page.height)
                    current_line = [word]
            record_line_content_only(current_line, all_lines, page.height)

    return font_stats, all_lines

def record_line(words, stats, all_lines, page_height):
    if not words: return
    sizes = [w['size'] for w in words]
    size = round(max(sizes), 1)
    text = " ".join([w['text'] for w in words])
    
    # Update LLM Stats
    stats[size]['count'] += 1
    stats[size]['total_chars'] += len(text)
    if len(stats[size]['examples']) < 3: 
        stats[size]['examples'].append(text[:30]) # Save snippets for LLM

    # Store for Splitting
    all_lines.append({
        "size": size, "text": text, "top": words[0]['top'], "height": page_height
    })

def record_line_content_only(words, all_lines, page_height):
    if not words: return
    sizes = [w['size'] for w in words]
    size = round(max(sizes), 1)
    text = " ".join([w['text'] for w in words])
    all_lines.append({
        "size": size, "text": text, "top": words[0]['top'], "height": page_height
    })

# --- 5. STEP 2: ASK LLM ---
def get_ai_header_sizes(font_stats):
    print("\n🧠 Sending Font Data to LLM...")
    
    # Format data for Llama
    summary = []
    sorted_sizes = sorted(font_stats.keys(), reverse=True)
    
    for size in sorted_sizes:
        data = font_stats[size]
        avg_len = int(data['total_chars'] / data['count'])
        ex = ", ".join(data['examples'])
        summary.append(f"- Size {size}: {data['count']} lines. Avg Len: {avg_len}. Ex: '{ex}...'")
    
    context = "\n".join(summary)
    
    response = llm.with_structured_output(HeaderAnalysis).invoke(f"""
        Analyze this PDF font data to find Section Headers.
        
        DATA:
        {context}
        
        RULES:
        1. Headers are usually LARGER than body text.
        2. Headers appear LESS frequently than body text.
        3. Headers are usually SHORT (Titles), not full paragraphs.
        
        Task: Return the list of Font Sizes that are likely Headers.
    """)
    
    print(f"   -> AI Reasoning: {response.reasoning}")
    print(f"   -> AI Selected Sizes: {response.header_font_sizes}")
    return response.header_font_sizes

# --- 6. STEP 3: SPLIT WITH HYBRID LOGIC ---
def split_document(all_lines, header_sizes):
    print("\n✂️  Splitting Document...")
    
    topics = []
    current_topic = {"title": "Introduction", "content": ""}
    
    for line in all_lines:
        text = line['text']
        size = line['size']
        top = line['top']
        h = line['height']
        
        # 🌟 THE MAGIC CHECK:
        # 1. Does LLM think it's a header size?
        # 2. Does Logic think it's valid (not a page number)?
        if is_valid_header(text, top, h, size, header_sizes):
            
            # Save previous
            if len(current_topic['content']) > 50:
                topics.append(current_topic)
            
            # Start New
            current_topic = {
                "title": clean_text(text),
                "content": ""
            }
        else:
            # It's content (or a filtered-out header like a page number)
            # If it's a page number (filtered out), we actually don't want it in content either.
            # But simplistic approach: just add it. 
            # Better approach: check regex again to exclude page numbers from content.
            if not re.match(r'^\d+$', clean_text(text)):
                current_topic['content'] += clean_text(text) + "\n"

    if current_topic['content']:
        topics.append(current_topic)
        
    return topics

# --- MAIN ---
if __name__ == "__main__":
    pdf_file = "data/pdf/sample_textbook_chapter_1.pdf"
    
    # 1. Scan & Stats
    stats, lines = scan_pdf_structure(pdf_file)
    
    # 2. AI Decision
    ai_headers = get_ai_header_sizes(stats)
    
    # 3. Hybrid Split
    final_topics = split_document(lines, ai_headers)
    
    # 4. Save
    with open("data/hybrid_structured_content.json", "w", encoding="utf-8") as f:
        json.dump(final_topics, f, indent=2, ensure_ascii=False)
        
    print(f"\n✅ Created {len(final_topics)} Smart Topics.")
    print("   Check data/hybrid_structured_content.json")
    
    # Preview
    for t in final_topics[:5]:
        print(f"   📌 {t['title']}")