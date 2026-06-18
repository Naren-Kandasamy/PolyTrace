import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from pipeline.extract import run_extraction_pipeline

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
    print("=== NCL PolyTrace (Hydrogen Storage) - Gold Standard Run ===")
    conn = setup_database()
    
    gold_dir = os.path.join(BASE_DIR, "pdfs", "gold_standard")
    
    if not os.path.exists(gold_dir):
        print(f"[!] Directory not found: {gold_dir}")
        return
        
    pdf_files = [f for f in os.listdir(gold_dir) if f.endswith(".pdf")]
    print(f"[*] Found {len(pdf_files)} PDFs in Gold Standard directory.")
    
    # Process each PDF
    for i, pdf_file in enumerate(pdf_files):
        pdf_path = os.path.join(gold_dir, pdf_file)
        
        # 1. Insert dummy paper record to satisfy foreign key constraints
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papers (title, pdf_path, is_open_access) 
                VALUES (%s, %s, TRUE) 
                RETURNING id
            """, (pdf_file, pdf_path))
            paper_id = cur.fetchone()[0]
            conn.commit()
            
        # 2. Run pipeline
        run_extraction_pipeline(paper_id, pdf_path, conn)

    print("\n[+] Gold Standard batch processing complete!")
    conn.close()

if __name__ == "__main__":
    main()
