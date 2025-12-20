import pdfplumber
import json
import re
import numpy as np
from collections import Counter

# --- 1. CLEANING FUNCTIONS ---

def clean_text(text):
    """Fixes encoding issues like (cid:2) and extra spaces."""
    # Remove CID codes (common in PDFs)
    text = re.sub(r'\(cid:\d+\)', '', text)
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_valid_header(text, top, page_height, prev_text):
    """
    Decides if a line is a REAL topic header or just PDF junk.
    """
    text_clean = clean_text(text).lower()
    
    # RULE 1: Geometry (Ignore Top 10% and Bottom 10% of page)
    # This kills "CHAPTER 1 • COMPUTER NETWORKS..." at the top of every page
    if top < (page_height * 0.08): 
        return False 
    if top > (page_height * 0.90): 
        return False

    # RULE 2: Ignore Captions
    if text_clean.startswith("figure") or text_clean.startswith("fig."):
        return False
    if text_clean.startswith("table"):
        return False

    # RULE 3: Ignore Page Numbers (Just digits)
    if re.match(r'^\d+$', text_clean):
        return False

    # RULE 4: Ignore Fragments (sentences cut off)
    # If it ends with a comma or lowercase, it's likely a broken sentence, not a title
    if text_clean.endswith(',') or (len(text) > 0 and text[0].islower()):
        return False
    
    # RULE 5: Duplicate Check (The header is same as previous header)
    if text == prev_text:
        return False

    return True

# --- 2. EXTRACTION LOGIC ---

def get_font_size_stats(pdf_path):
    print("📊 Analyzing font sizes...")
    sizes = []
    with pdfplumber.open(pdf_path) as pdf:
        # Check first 5 pages
        for page in pdf.pages[:5]: 
            words = page.extract_words(extra_attrs=["size"])
            for w in words:
                sizes.append(round(w['size']))
    
    if not sizes: return 12, 14

    size_counts = Counter(sizes)
    body_size = size_counts.most_common(1)[0][0]
    
    # Header threshold: Body + 1.2 (slightly more sensitive)
    header_threshold = body_size + 1.2
    
    print(f"   -> Body Size: {body_size} | Header Threshold: > {header_threshold}")
    return body_size, header_threshold

def extract_clean_topics(pdf_path):
    _, header_threshold = get_font_size_stats(pdf_path)
    
    structured_content = []
    current_topic = {"title": "Introduction", "content": ""}
    
    print("📖 Extracting content with smart filters...")
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            width = page.width
            height = page.height
            
            # Extract words with size AND position (top)
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue
            
            # Group into lines
            current_line_words = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line_words[-1]['top']) < 5:
                    current_line_words.append(word)
                else:
                    process_clean_line(current_line_words, header_threshold, height, current_topic, structured_content)
                    current_line_words = [word]
            
            process_clean_line(current_line_words, header_threshold, height, current_topic, structured_content)

    if current_topic["content"]:
        structured_content.append(current_topic)
        
    return structured_content

def process_clean_line(words, threshold, page_height, current_topic, structured_list):
    if not words: return

    line_text = " ".join([w['text'] for w in words])
    cleaned_text = clean_text(line_text)
    
    avg_size = sum([w['size'] for w in words]) / len(words)
    top_pos = words[0]['top'] # Y-position of the line
    
    # CHECK: Is it Big?
    is_big = avg_size > threshold
    
    # CHECK: Is it a Valid Header? (The new filters)
    is_valid = is_valid_header(line_text, top_pos, page_height, current_topic["title"])

    if is_big and is_valid:
        # Save previous
        if len(current_topic["content"]) > 50: 
            structured_list.append(current_topic.copy())
        
        # New Topic
        current_topic["title"] = cleaned_text
        current_topic["content"] = ""
    else:
        # Even if it's big, if it's junk, treat it as content or ignore
        # (Here we treat as content, but you could ignore running heads completely)
        if not is_valid and is_big:
            pass # Skip running heads entirely (don't add to content)
        else:
            current_topic["content"] += cleaned_text + "\n"

# --- MAIN ---
if __name__ == "__main__":
    source_pdf = "data/pdf/sample_textbook_chapter_1.pdf"
    
    topics = extract_clean_topics(source_pdf)
    
    # Filter out empty topics
    final_topics = [t for t in topics if len(t['content']) > 100]

    output_file = "data/clean_structured_content.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_topics, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Extracted {len(final_topics)} clean topics.")
    
    print("\n🔍 Preview (Notice no 'Chapter 1' headers):")
    for t in final_topics[:5]:
        print(f"   📌 {t['title']}")