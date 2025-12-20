import pdfplumber
import json
import re
from collections import defaultdict
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from typing import List

# --- 1. SETUP ---
llm = ChatOllama(model="llama3", temperature=0)

# --- 2. DATA MODEL ---
# We ask for a LIST of sizes, not just H1/H2
class SplitStrategy(BaseModel):
    target_font_sizes: List[float] = Field(..., description="A list of ALL font sizes that should trigger a new topic split (e.g. [24.0, 18.0, 13.0]).")
    reasoning: str = Field(..., description="Explain why these specific sizes represent topic headers.")

# --- 3. CLEANING FILTERS (Safety Net) ---
def is_junk(text, top, page_height):
    # Top/Bottom 10% is usually junk
    if top < (page_height * 0.10) or top > (page_height * 0.90): return True
    # Digits only (Page nums)
    if re.match(r'^\d+$', text.strip()): return True
    # Captions
    if text.strip().lower().startswith(('figure', 'table', 'fig.')): return True
    return False

# --- 4. STEP 1: SCAN PDF ---
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
            
        # Read rest of content
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
    if len(stats[size]['examples']) < 3:
        stats[size]['examples'].append(text[:60])

    all_lines.append({'text': text, 'size': size, 'top': words[0]['top'], 'height': h})

def record_content_only(words, all_lines, h):
    size = round(max([w['size'] for w in words]), 1)
    text = " ".join([w['text'] for w in words])
    all_lines.append({'text': text, 'size': size, 'top': words[0]['top'], 'height': h})

# --- 5. STEP 2: ASK AI (THE NEW LOGIC) ---
def get_split_sizes_from_ai(font_stats):
    print("\n🧠 Consulting AI on Splitting Logic...")
    
    # 1. Identify Body Text (Max Frequency)
    body_size = max(font_stats, key=lambda k: font_stats[k]['count'])
    
    # 2. Format Report
    report = []
    sorted_sizes = sorted(font_stats.keys(), reverse=True)
    
    for size in sorted_sizes:
        d = font_stats[size]
        avg_len = int(d['total_len'] / d['count'])
        tag = "**BODY TEXT**" if size == body_size else ""
        ex = " | ".join(d['examples'])
        report.append(f"Size {size} {tag}: {d['count']} lines. AvgLen: {avg_len}. Ex: [{ex}]")
        
    context = "\n".join(report)

    # 3. The Clear Prompt
    prompt = f"""
    You are a Document Layout Engineer.
    I need to split this PDF into "Study Topics".
    
    Here is the Font Analysis of the document:
    -----------------------------------------
    {context}
    -----------------------------------------
    
    TASK:
    Select the list of font sizes that represent **Topic Headers**.
    
    LOGIC RULES:
    1. **Exclude Body Text:** Do not select Size {body_size}.
    2. **Include Hierarchy:** Select BOTH the main Chapter titles AND the Sub-section titles (e.g. 1.1, 1.2).
    3. **Look for Titles:** Headers usually have short line lengths and often contain numbering (1.1, 1.2) or words like "Introduction", "Summary".
    4. **Ignore Junk:** Do not select tiny fonts or running headers (often smaller than body).
    
    OUTPUT:
    Return a list of floats (e.g. [18.0, 14.0]) that I should use as triggers to split the text.
    """
    
    response = llm.with_structured_output(SplitStrategy).invoke(prompt)
    
    print(f"   -> AI Logic: {response.reasoning}")
    print(f"   -> Split Triggers: {response.target_font_sizes}")
    
    return response.target_font_sizes

# --- 6. STEP 3: SPLIT ---
def split_by_target_sizes(all_lines, target_sizes):
    print(f"\n✂️  Splitting content using sizes: {target_sizes}...")
    
    topics = []
    current_topic = {"title": "Introduction", "content": ""}
    
    # Track the size of the current topic's header
    current_header_size = 0 
    
    # Create a set for fast lookup (allow 0.2 float tolerance)
    targets = set(target_sizes)

    for line in all_lines:
        text = re.sub(r'\(cid:\d+\)', '', line['text']).strip()
        size = line['size']
        top = line['top']
        h = line['height']
        
        # 1. Filter Junk
        if is_junk(text, top, h): continue

        # 2. Check if Header
        is_header = any(abs(size - t) < 0.2 for t in targets)
        
        if is_header:
            # 🌟 MERGE LOGIC:
            # If this line is the same size as the previous topic's header,
            # and the previous topic has NO content yet, it's a multi-line title.
            if abs(size - current_header_size) < 0.2 and len(current_topic['content']) < 5:
                current_topic['title'] += " " + text
                print(f"   ➕ Merged Title: {current_topic['title']}")
            
            else:
                # Save previous
                if len(current_topic['content']) > 50:
                    topics.append(current_topic)
                
                # Start New
                print(f"   🔹 Topic: {text} (Size {size})")
                current_topic = {
                    "title": text,
                    "content": ""
                }
                current_header_size = size # Remember this size
        else:
            current_topic['content'] += text + "\n"

    if current_topic['content']:
        topics.append(current_topic)
    return topics

# --- MAIN ---
if __name__ == "__main__":
    pdf_file = "data/pdf/sample_textbook_chapter_1.pdf"
    
    # 1. Scan
    stats, lines = scan_pdf_stats(pdf_file)
    
    # 2. Ask AI
    split_sizes = get_split_sizes_from_ai(stats)
    
    # 3. Split
    final_topics = split_by_target_sizes(lines, split_sizes)
    
    # 4. Save
    with open("data/ai_list_split.json", "w", encoding="utf-8") as f:
        json.dump(final_topics, f, indent=2, ensure_ascii=False)
        
    print(f"\n✅ Done! Extracted {len(final_topics)} topics.")