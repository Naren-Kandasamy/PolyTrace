import fitz  # PyMuPDF
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP_IMG_DIR = os.path.join(BASE_DIR, ".tmp", "images")

def extract_text_by_section(pdf_path: str) -> dict:
    """Extract text chunked by section heading using PyMuPDF."""
    doc = fitz.open(pdf_path)
    sections = {}
    current_section = "preamble"
    
    for page in doc:
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = " ".join([s.get("text", "") for s in spans])
                    # Detect section headings by font size
                    font_size = spans[0].get("size", 0) if spans else 0
                    if font_size > 11 and len(text) < 80:
                        current_section = text.strip().lower()
                        if current_section not in sections:
                            sections[current_section] = ""
                    else:
                        sections.setdefault(current_section, "")
                        sections[current_section] += text + " "
    return sections

def extract_images_from_pdf(pdf_path: str, paper_id: str) -> list:
    """
    Scans the PDF and extracts embedded images (figures, plots).
    Saves them temporarily to .tmp/images/ and returns a list of paths.
    """
    os.makedirs(TMP_IMG_DIR, exist_ok=True)
    doc = fitz.open(pdf_path)
    extracted_image_paths = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Heuristic: ignore small images (logos, icons) which are usually < 400px
            if base_image["width"] < 400 or base_image["height"] < 400:
                continue
                
            image_filename = f"paper_{paper_id}_page{page_num}_img{img_index}.{image_ext}"
            image_path = os.path.join(TMP_IMG_DIR, image_filename)
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
                
            extracted_image_paths.append(image_path)
            
    return extracted_image_paths

def cleanup_images(image_paths: list):
    """Stateless cleanup: delete temporary images after VLM processing."""
    for path in image_paths:
        if os.path.exists(path):
            os.remove(path)

def extract_tables(pdf_path: str) -> list:
    """Extract all tables as DataFrames."""
    import pandas as pd
    import pdfplumber
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if table and len(table) > 1:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    tables.append(df)
    return tables

if __name__ == "__main__":
    print("Multimodal Visual Preprocessing ready.")
    print("Use extract_text_by_section() for text, extract_images_from_pdf() for images, and extract_tables() for tables.")

