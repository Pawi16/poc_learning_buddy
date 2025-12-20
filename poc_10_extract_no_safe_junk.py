import pdfplumber
import json
import re
from collections import defaultdict
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from typing import List

# --- 1. CONFIGURATION ---
llm = ChatOllama(model="llama3", temperature=0)

# --- 2. DATA MODELS ---
class SplitStrategy(BaseModel):
    target_font_sizes: List[float] = Field(..., description="List of font sizes that represent Topic Headers.")
    reasoning: str = Field(..., description="Explain why based on the text samples (e.g. 'Size 13 has numbering 1.1', 'Size 10 looks like page headers').")

# --- 3. CLEANING FILTERS ---
def is_junk(text, top, page_height):
    # 1. Geometry: Top/Bottom 10% 
    if top < (page_height * 0.10) or top > (page_height * 0.90): return True
    # 2. Content: Page numbers
    if re.match(r'^\d+$', text.strip()): return True
    # 3. Content: Captions
    if text.strip().lower().startswith(('figure', 'table', 'box')): return True
    return False

# --- 4. STEP 1: SCAN PDF STATS ---
def scan_pdf_stats(pdf_path):
    print(f"🔬 Scanning PDF structure: {pdf_path}...")
    
    # Stats: Size -> {count, total_len, examples}
    font_stats = defaultdict(lambda: {'count': 0, 'total_len': 0, 'examples': []})
    all_lines = []

    with pdfplumber.open(pdf_path) as pdf:
        # Scan first 20 pages
        for page in pdf.pages[:20]:
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue
            
            current_line = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line[-1]['top']) < 5:
                    current_line.append(word)
                else:
                    record_line(current_line, font_stats, all_lines, page.height)
                    current_line = [word]
            record_line(current_line, font_stats, all_lines, page.height)
            
        # Read rest
        for page in pdf.pages[20:]:
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue
            current_line = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line[-1]['top']) < 5:
                    current_line.append(word)
                else:
                    record_content_only(current_line, all_lines, page.height)
                    current_line = [word]
            record_content_only(current_line, all_lines, page.height)

    return font_stats, all_lines

def record_line(words, stats, all_lines, h):
    size = round(max([w['size'] for w in words]), 1)
    text = " ".join([w['text'] for w in words])
    
    stats[size]['count'] += 1
    stats[size]['total_len'] += len(text)
    
    # 🌟 UPGRADE: Capture more context (150 chars) and more examples (5)
    if len(stats[size]['examples']) < 5:
        clean_sample = re.sub(r'\s+', ' ', text).strip()
        stats[size]['examples'].append(clean_sample[:150])

    all_lines.append({'text': text, 'size': size, 'top': words[0]['top'], 'height': h})

def record_content_only(words, all_lines, h):
    size = round(max([w['size'] for w in words]), 1)
    text = " ".join([w['text'] for w in words])
    all_lines.append({'text': text, 'size': size, 'top': words[0]['top'], 'height': h})

# --- 5. STEP 2: ASK AI (CONTEXT AWARE) ---
def get_split_sizes_from_ai(font_stats):
    print("\n🧠 Consulting AI on Splitting Logic...")
    
    if not font_stats: return [18.0], 12.0
    body_size = max(font_stats, key=lambda k: font_stats[k]['count'])
    
    # Format Report
    report = []
    sorted_sizes = sorted(font_stats.keys(), reverse=True)
    
    for size in sorted_sizes:
        d = font_stats[size]
        avg_len = int(d['total_len'] / d['count'])
        tag = " [**BODY TEXT**]" if size == body_size else ""
        
        # Format examples as a bullet list for the AI to read easily
        ex_list = "\n         - " + "\n         - ".join(d['examples'])
        
        report.append(f"SIZE {size}{tag} (Count: {d['count']}, AvgLen: {avg_len}):{ex_list}")
        
    context = "\n".join(report)

    # 🌟 UPGRADE: Prompt asks to analyze the TEXT content
    prompt = f"""
    You are a Document Layout Engineer. Analyze the text samples to find the Topic Headers.
    
    FONT DATA:
    -----------------------------------------
    {context}
    -----------------------------------------
    
    TASK:
    Return the list of font sizes that represent **Topic Headers**.
    
    CRITICAL ANALYSIS RULES:
    1. **READ THE SAMPLES:** - If samples look like "Chapter 1", "1. Introduction", "Summary", "References" -> IT IS A HEADER.
       - If samples look like "Page 1 of 5", "Copyright 2024", "http://..." -> IT IS JUNK (Ignore it).
       - If samples look like full sentences ("The quick brown fox...") -> IT IS BODY TEXT (Ignore it).
       
    2. **SIZE RULE:** MUST be larger than Body Text (Size {body_size}).
    
    OUTPUT:
    Return the list of floats (e.g. [24.0, 13.0]).
    """
    
    response = llm.with_structured_output(SplitStrategy).invoke(prompt)
    print(f"   -> AI Reasoning: {response.reasoning}")
    print(f"   -> AI Selected Triggers: {response.target_font_sizes}")
    
    return response.target_font_sizes, body_size

# --- 6. STEP 3: SPLIT (WITH SAFETY) ---
def split_by_target_sizes(all_lines, target_sizes, body_size):
    print(f"\n✂️  Splitting content using sizes: {target_sizes} (Body: {body_size})...")
    
    # Safety Filter
    valid_targets = {t for t in target_sizes if t > body_size}
    if len(valid_targets) != len(target_sizes):
        print(f"   ⚠️ Removed invalid targets <= body size. Active triggers: {valid_targets}")

    topics = []
    current_topic = {"title": "Introduction", "content": ""}
    current_header_size = 0 
    
    for line in all_lines:
        text = re.sub(r'\(cid:\d+\)', '', line['text']).strip()
        size = line['size']
        top = line['top']
        h = line['height']
        
        if is_junk(text, top, h): continue

        is_header = any(abs(size - t) < 0.2 for t in valid_targets)
        
        if is_header:
            # Merge Logic
            if abs(size - current_header_size) < 0.2 and len(current_topic['content']) < 10:
                current_topic['title'] += " " + text
                print(f"   ➕ Merged Title: {current_topic['title']}")
            else:
                if len(current_topic['content']) > 50: topics.append(current_topic)
                print(f"   🔹 Topic: {text} (Size {size})")
                current_topic = {"title": text, "content": ""}
                current_header_size = size
        else:
            current_topic['content'] += text + "\n"

    if current_topic['content']: topics.append(current_topic)
    return topics

# --- MAIN ---
if __name__ == "__main__":
    pdf_file = "data/pdf/Effective Java chapter 1.pdf"
    
    stats, lines = scan_pdf_stats(pdf_file)
    split_sizes, body_size = get_split_sizes_from_ai(stats)
    final_topics = split_by_target_sizes(lines, split_sizes, body_size)
    
    with open("data/context_aware_split.json", "w", encoding="utf-8") as f:
        json.dump(final_topics, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Done! Extracted {len(final_topics)} topics.")