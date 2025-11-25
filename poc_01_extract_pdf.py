import time
from docling.document_converter import DocumentConverter

def extract_text_from_pdf():
    source_file = "data/pdf/sample_textbook_chapter_1.pdf"

    print(f"📄 Starting extraction for: {source_file}...")
    start_time = time.time()

    converter = DocumentConverter()
    result = converter.convert(source_file)

    # export to markdown
    markdown_output = result.document.export_to_markdown()

    end_time = time.time()
    print(f"✅ Success! Extraction took {end_time - start_time:.2f} seconds.")

    output_filename = "data/extracted_text.md"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(markdown_output)
    
    print(f"📝 Output saved to: {output_filename}")
    print("-" * 30)
    
    print("PREVIEW OF EXTRACTED TEXT:")
    print(markdown_output[:1000]) # Print first 1000 characters
    print("...")

if __name__ == "__main__":
    extract_text_from_pdf()