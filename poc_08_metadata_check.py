import pdfplumber
import json
from collections import defaultdict

def generate_font_report(pdf_path):
    print(f"🔬 Scanning PDF Typography: {pdf_path}...")
    
    # Store stats: { Size: {count, total_len, examples} }
    stats = defaultdict(lambda: {'count': 0, 'total_len': 0, 'examples': []})

    with pdfplumber.open(pdf_path) as pdf:
        # Scan ALL pages (or limit to [:20] for speed)
        for i, page in enumerate(pdf.pages):
            words = page.extract_words(extra_attrs=["size", "top"])
            if not words: continue
            
            # Group words into lines
            current_line = [words[0]]
            for word in words[1:]:
                # If vertical distance < 5, it's the same line
                if abs(word['top'] - current_line[-1]['top']) < 5:
                    current_line.append(word)
                else:
                    record_line_stats(current_line, stats)
                    current_line = [word]
            record_line_stats(current_line, stats)
            
            if i % 5 == 0: print(f"   ...scanned page {i+1}")

    # --- GENERATE REPORT ---
    print("\n📝 Generating Report...")
    sorted_sizes = sorted(stats.keys(), reverse=True) # Biggest fonts first
    
    report_lines = []
    report_lines.append("="*60)
    report_lines.append(f"FONT ANALYSIS REPORT: {pdf_path}")
    report_lines.append("="*60 + "\n")
    
    # Guess the Body Text (Most frequent font)
    most_frequent_size = max(stats, key=lambda k: stats[k]['count'])
    report_lines.append(f"📌 LIKELY BODY TEXT SIZE: {most_frequent_size}pt\n")
    report_lines.append("-" * 60)
    
    json_data = []

    for size in sorted_sizes:
        data = stats[size]
        avg_len = int(data['total_len'] / data['count'])
        
        # Formatting the readable report
        tag = " [BODY]" if size == most_frequent_size else ""
        if size > most_frequent_size: tag = " [HEADER?]"
        if size < most_frequent_size: tag = " [SMALL]"
        
        report_lines.append(f"SIZE {size:<5} {tag}")
        report_lines.append(f"  - Occurrences: {data['count']}")
        report_lines.append(f"  - Avg Length:  {avg_len} chars")
        report_lines.append(f"  - Samples:     ")
        for ex in data['examples'][:3]: # Show top 3 examples
            report_lines.append(f"      * \"{ex}\"")
        report_lines.append("-" * 30)
        
        # Prepare JSON data
        json_data.append({
            "size": size,
            "count": data['count'],
            "avg_length": avg_len,
            "samples": data['examples'][:5]
        })

    # SAVE TO FILE (Human Readable)
    report_file = "data/font_analysis_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    # SAVE TO JSON (Machine Readable)
    json_file = "data/font_stats.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    print(f"✅ Report saved to: {report_file}")
    print(f"✅ Raw Data saved to: {json_file}")
    print("\n--- PREVIEW (Top 3 Sizes) ---")
    print("\n".join(report_lines[:25]))

def record_line_stats(words, stats):
    if not words: return
    # Use MAX size in the line (handles Bold headers where only 1 letter is big)
    size = round(max([w['size'] for w in words]), 1)
    text = " ".join([w['text'] for w in words])
    
    stats[size]['count'] += 1
    stats[size]['total_len'] += len(text)
    
    # Store unique examples (limit to 5 per size to save memory)
    if len(stats[size]['examples']) < 5:
        stats[size]['examples'].append(text)

# --- EXECUTION ---
if __name__ == "__main__":
    pdf_file = "data/pdf/Effective Java chapter 1.pdf"
    generate_font_report(pdf_file)