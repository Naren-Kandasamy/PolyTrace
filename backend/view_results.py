import os
import json
import psycopg2

DB_NAME = os.getenv("DB_NAME", "materials_ai")
DB_USER = os.getenv("DB_USER", "ncl")
DB_PASSWORD = os.getenv("DB_PASSWORD", "ncl_password")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")

def main():
    try:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.title, m.material_name, m.properties 
                FROM material_extractions m
                JOIN papers p ON p.id = m.paper_id
            """)
            results = cur.fetchall()
            
        print(f"\n=== POLYTRACE DATABASE CONTENTS ({len(results)} Extracted Materials) ===\n")
        for row in results:
            title, name, props = row
            print(f"📄 Paper: {title}")
            print(json.dumps(props, indent=2))
            print("-" * 60)
            
        conn.close()
    except Exception as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    main()
