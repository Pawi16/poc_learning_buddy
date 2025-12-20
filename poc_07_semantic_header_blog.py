import pdfplumber
import json
import re
from typing import List, Tuple
from langchain_ollama import ChatOllama

# --- 1. SETUP ---
# Using temperature=0 for strict logical reasoning
llm = ChatOllama(model="llama3", temperature=0)

# --- 2. STEP 1: EXTRACT & GROUP METADATA (The Java Logic) ---
def get_pdf_metadata(pdf_path):
    print(f"🔍 Scanning PDF structure: {pdf_path}...")
    
    all_lines = []
    
    # 1. Read Raw Lines
    with pdfplumber.open(pdf_path) as pdf:
        # Scan first 15 pages (or remove limit for full doc)
        for page in pdf.pages[:15]: 
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue
            
            # Reconstruct lines based on Y-position
            current_line_words = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line_words[-1]['top']) < 5:
                    current_line_words.append(word)
                else:
                    all_lines.append(process_line(current_line_words, page.height))
                    current_line_words = [word]
            all_lines.append(process_line(current_line_words, page.height))

    # 2. Group Consecutive Lines (The "Blog" Logic)
    # If we have 50 lines of size 12, we group them into 1 metadata entry.
    metadata_list = []
    unique_fonts = set()
    
    if not all_lines: return [], [], []

    # Initialize with first line
    current_height = all_lines[0]['size']
    current_line_count = 1
    current_total_chars = len(all_lines[0]['text'])
    unique_fonts.add(current_height)

    for i in range(1, len(all_lines)):
        line = all_lines[i]
        h = line['size']
        unique_fonts.add(h)
        
        if h != current_height:
            # Font changed! Record the previous block.
            metadata_list.append(f"Metadata(fontHeight={current_height}, lineCount={current_line_count}, totalCharacters={current_total_chars})")
            
            # Reset for new block
            current_height = h
            current_line_count = 1
            current_total_chars = len(line['text'])
        else:
            # Same font, keep counting
            current_line_count += 1
            current_total_chars += len(line['text'])

    # Add the last block
    metadata_list.append(f"Metadata(fontHeight={current_height}, lineCount={current_line_count}, totalCharacters={current_total_chars})")
    
    return metadata_list, sorted(list(unique_fonts), reverse=True), all_lines

def process_line(words, page_height):
    sizes = [w['size'] for w in words]
    # Round to integer to make grouping easier (like the blog likely did)
    size = int(round(max(sizes))) 
    text = " ".join([w['text'] for w in words])
    return {"size": size, "text": text, "top": words[0]['top'], "height": page_height}

# --- 3. STEP 2: THE EXACT PROMPT ---
def get_headers_from_llm(metadata_strings, unique_fonts):
    print("\n🧠 Sending Pattern to LLM...")
    
    # We join the metadata strings (Limit to ~3000 chars of metadata to fit context)
    # The blog implies passing the whole document pattern, but for LLMs we often truncate
    pattern_context = "\n".join(metadata_strings[:200]) 
    
    prompt = f"""
    OBJECTIVE -
    You are a AI assistant that is an expert at reading documents.
    You will be provided the metadata information about all the lines that are contained in a document.
    The objective is to figure out the section headers from the metadata.

    Section Headers:
    Section headers are basically topic headers that form the starting point of different sections.

    ***********************************************************

    You will be provided with a list of metadata in the following structure:

    Metadata(fontHeight=6, lineCount=3, totalCharacters=24)
    Metadata(fontHeight=5, lineCount=1, totalCharacters=1)

    and a list of decreasing unique font heights:
    {unique_fonts}

    ***********************************************************

    RULES :
    Generally, section headers/ titles have the following properties -
    1. They are bigger in size than the surrounding text.
    2. They are few in number compared to the total text that the document contains.
    3. The total characters of such lines are significantly lower as compared to the surrounding lines.
    4. They are generally evenly spread across the document.

    ***********************************************************

    OUTPUT RESPONSE :
    I want you to utilize the metadata of the fonts and the list of all available font sizes, to give me the possible section titles.
    I want the response as a list of Comma separated font sizes. i.e.
    Ex - [20, 18]

    1. Do not contain any explanation or code.
    2. Response should be comma separated list of font sizes that are possible sections.

    Here is the list of font metadata for the document: 
    {pattern_context}
    """
    
    response = llm.invoke(prompt)
    print(f"   -> Raw LLM Response: {response.content}")
    
    # Parse the response (extract numbers)
    try:
        # Regex to find numbers inside brackets or just comma separated
        matches = re.findall(r'\d+', response.content)
        sizes = [int(m) for m in matches]
        # Filter out weird numbers (e.g. if it extracted '2025' from date)
        # Keep only sizes that actually exist in the document
        valid_sizes = [s for s in sizes if s in unique_fonts]
        print(f"   -> Parsed Valid Header Sizes: {valid_sizes}")
        return valid_sizes
    except:
        print("   ❌ Failed to parse LLM response. Defaulting to largest font.")
        return [unique_fonts[0]] if unique_fonts else [14]

# --- 4. STEP 3: SPLIT DOCUMENT ---
def split_by_exact_sizes(all_lines, header_sizes):
    print("\n✂️  Splitting based on blog logic...")
    topics = []
    current_topic = {"title": "Introduction", "content": ""}
    
    # Blog logic implies exact match or greater
    target_sizes = set(header_sizes)

    for line in all_lines:
        size = line['size']
        text = line['text']
        
        # Check if this line's size is in the "Header List"
        if size in target_sizes:
            # Simple junk filter (Page numbers)
            if re.match(r'^\d+$', text.strip()): continue 
            
            if len(current_topic['content']) > 50:
                topics.append(current_topic)
            
            current_topic = {
                "title": text,
                "content": ""
            }
        else:
            current_topic['content'] += text + "\n"
            
    if current_topic['content']:
        topics.append(current_topic)
    return topics

# --- MAIN ---
if __name__ == "__main__":
    pdf_path = "data/pdf/sample_textbook_chapter_1.pdf"
    
    # 1. Get Metadata Stream
    meta_strings, font_list, lines = get_pdf_metadata(pdf_path)
    
    # 2. Ask LLM (The Blog Method)
    header_sizes = get_headers_from_llm(meta_strings, font_list)
    
    # 3. Split
    final_topics = split_by_exact_sizes(lines, header_sizes)
    
    # 4. Save
    with open("data/blog_method_output.json", "w", encoding="utf-8") as f:
        json.dump(final_topics, f, indent=2, ensure_ascii=False)
        
    print(f"\n✅ Extracted {len(final_topics)} topics using Blog Method.")
    for t in final_topics[:5]:
        print(f"   📌 {t['title']} (Size detected as header)")