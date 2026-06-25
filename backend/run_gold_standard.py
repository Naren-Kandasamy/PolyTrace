import os
import sys
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from pipeline.extract import prepare_paper_data, run_text_extraction, run_vision_extraction

DB_NAME = os.getenv("DB_NAME", "materials_ai")
DB_USER = os.getenv("DB_USER", "ncl")
DB_PASSWORD = os.getenv("DB_PASSWORD", "ncl_password")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")

def setup_database():
    """Apply schema.sql to the database."""
    print("[*] Applying schema.sql to materials_ai...")
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
    with open(os.path.join(BASE_DIR, "backend", "db", "schema.sql"), "r") as f:
        schema = f.read()
    with conn.cursor() as cur:
        cur.execute(schema)
    conn.commit()
    return conn

def main():
    start_total_time = time.time()
    print("=== NCL PolyTrace (Hydrogen Storage) - Gold Standard Run ===")
    conn = setup_database()
    
    gold_dir = os.path.join(BASE_DIR, "pdfs", "gold_standard")
    
    if not os.path.exists(gold_dir):
        print(f"[!] Directory not found: {gold_dir}")
        return
        
    pdf_files = [f for f in os.listdir(gold_dir) if f.endswith(".pdf")]
    print(f"[*] Found {len(pdf_files)} PDFs in Gold Standard directory.")
    
    parsed_data = []
    
    # PHASE 1: CPU Parsing
    print("\n--- PHASE 1: CPU Parsing (Text, Tables, Images) ---")
    for i, pdf_file in enumerate(pdf_files):
        pdf_path = os.path.join(gold_dir, pdf_file)
        
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papers (title, pdf_path, is_open_access) 
                VALUES (%s, %s, TRUE) 
                RETURNING id
            """, (pdf_file, pdf_path))
            paper_id = cur.fetchone()[0]
            conn.commit()
            
        core_text, image_paths = prepare_paper_data(paper_id, pdf_path)
        parsed_data.append((paper_id, core_text, image_paths))
        
    # PHASE 2: LLM Text Extraction
    print("\n--- PHASE 2: Text Extraction (llama3.2:1b) ---")
    for paper_id, core_text, _ in parsed_data:
        run_text_extraction(paper_id, core_text, conn)

    # PHASE 3: VLM Image Extraction
    print("\n--- PHASE 3: Vision Extraction (qwen2.5vl:3b) ---")
    for paper_id, _, image_paths in parsed_data:
        run_vision_extraction(paper_id, image_paths, conn)

    end_total_time = time.time()
    total_minutes = (end_total_time - start_total_time) / 60.0
    print(f"\n[+] Gold Standard batch processing complete! (Total Pipeline Time: {total_minutes:.2f} minutes)")
    conn.close()

if __name__ == "__main__":
    main()
