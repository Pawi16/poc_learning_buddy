import pdfplumber
import json
import re
from collections import defaultdict
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from typing import List

# --- 1. CONFIGURATION ---
llm = ChatOllama(model="qwen2.5:14b", temperature=0)

# --- 2. DATA MODELS ---
class SplitStrategy(BaseModel):
    target_font_sizes: List[float] = Field(..., description="A list of ALL font sizes that represent Topic Headers.")
    reasoning: str = Field(..., description="Explain why. Mention specific text patterns found in the samples.")

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
    font_stats = defaultdict(lambda: {'count': 0, 'total_len': 0, 'examples': []})
    all_lines = []

    with pdfplumber.open(pdf_path) as pdf:
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

    # Debug File Generation (Exactly what you liked)
    print("📝 Saving Font Analysis Report to file...")
    try:
        if font_stats:
            body_size = max(font_stats, key=lambda k: font_stats[k]['count'])
            sorted_sizes = sorted(font_stats.keys(), reverse=True)
            report_lines = []
            report_lines.append(f"📌 DETECTED BODY TEXT SIZE: {body_size} pt\n" + "-"*80)

            for size in sorted_sizes:
                d = font_stats[size]
                avg_len = int(d['total_len'] / d['count'])
                tag = " [BODY]" if size == body_size else ""
                if size > body_size: tag = " [HEADER?]"
                if size < body_size: tag = " [SMALL]"

                report_lines.append(f"SIZE {size:<6} {tag}")
                report_lines.append(f"  • Occurrences: {d['count']}")
                report_lines.append(f"  • Avg Length:  {avg_len} chars")
                report_lines.append(f"  • Samples:")
                for ex in d['examples']:
                    clean_ex = ex.replace('\n', ' ')
                    report_lines.append(f"      - \"{clean_ex}\"")
                report_lines.append("-" * 40)

            with open("data/font_stats_debug.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines))
    except Exception as e:
        print(f"❌ Error saving report: {e}")

    return font_stats, all_lines

def record_line(words, stats, all_lines, h):
    size = round(max([w['size'] for w in words]), 1)
    text = " ".join([w['text'] for w in words])
    stats[size]['count'] += 1
    stats[size]['total_len'] += len(text)
    if len(stats[size]['examples']) < 5:
        stats[size]['examples'].append(text[:100])
    all_lines.append({'text': text, 'size': size, 'top': words[0]['top'], 'height': h})

def record_content_only(words, all_lines, h):
    size = round(max([w['size'] for w in words]), 1)
    text = " ".join([w['text'] for w in words])
    all_lines.append({'text': text, 'size': size, 'top': words[0]['top'], 'height': h})

# --- 5. STEP 2: ASK AI (WITH RICH CONTEXT) ---
def get_split_sizes_from_ai(font_stats):
    print("\n🧠 Consulting AI on Splitting Logic...")
    
    if not font_stats: return [18.0], 12.0
    body_size = max(font_stats, key=lambda k: font_stats[k]['count'])
    
    # --- 🌟 REPLICATING THE RICH DEBUG FORMAT FOR AI ---
    report = []
    sorted_sizes = sorted(font_stats.keys(), reverse=True)
    
    for size in sorted_sizes:
        d = font_stats[size]
        avg_len = int(d['total_len'] / d['count'])
        
        # Explicitly tag the types so AI doesn't have to guess
        tag = " [BODY]" if size == body_size else ""
        if size > body_size: tag = " [HEADER?]" # Helper tag
        if size < body_size: tag = " [SMALL/JUNK]" # Helper tag
        
        # Format examples vertically for better readability
        ex_list = ""
        for ex in d['examples']:
            clean_ex = ex.replace('\n', ' ')
            ex_list += f"\n      - \"{clean_ex}\""
            
        entry = f"SIZE {size:<6}{tag}\n  • Occurrences: {d['count']}\n  • Avg Length:  {avg_len} chars\n  • Samples:{ex_list}\n" + "-"*40
        report.append(entry)
        
    context = "\n".join(report)
    print(context)

    # PROMPT
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
    2. **Include Hierarchy:** Select BOTH the main Chapter titles AND the Sub-section titles.
    3. **Ignore Junk:** Do not select tiny fonts or running headers (often smaller than body).
    4. Do not select fonts that smaller than  {body_size}.
    5. Topic header need to be HEADER type and have higher occurences that other header font size in provide document (also show reasoning how it)

    
    OUTPUT:
    Return a list of floats representing the header sizes found.
    """
    
    response = llm.with_structured_output(SplitStrategy).invoke(prompt)
    print(f"   -> AI Logic: {response.reasoning}")
    print(f"   -> AI Selected Triggers: {response.target_font_sizes}")
    
    return response.target_font_sizes, body_size

# --- 6. STEP 3: SPLIT ---
def split_by_target_sizes(all_lines, target_sizes, body_size):
    print(f"\n✂️  Splitting content using sizes: {target_sizes}...")
    
    # 🛡️ Safety: Double check against Body Size
    valid_targets = {t for t in target_sizes if t > body_size}

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

if __name__ == "__main__":
    pdf_file = "data/pdf/Effective Java chapter 1.pdf"
    
    stats, lines = scan_pdf_stats(pdf_file)
    split_sizes, body_size = get_split_sizes_from_ai(stats)
    final_topics = split_by_target_sizes(lines, split_sizes, body_size)
    
    with open("data/final_rich_split.json", "w", encoding="utf-8") as f:
        json.dump(final_topics, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Done! Extracted {len(final_topics)} topics.")