import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os

def get_db_connection():
    """Establish connection to PostgreSQL Document Store"""
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "materials_ai"),
        user=os.getenv("DB_USER", "ncl"),
        password=os.getenv("DB_PASSWORD", "ncl_password"),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432")
    )

def insert_paper(conn, doi, title, authors, journal, year, url, pdf_path, is_open_access=False):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO papers (doi, title, authors, journal, year, url, pdf_path, is_open_access)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doi) DO NOTHING
            RETURNING id
        """, (doi, title, authors, journal, year, url, pdf_path, is_open_access))
        
        result = cur.fetchone()
        conn.commit()
        return result[0] if result else None

def insert_material_extraction(conn, paper_id, material_name, properties: dict):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO material_extractions (paper_id, material_name, properties)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (paper_id, material_name, json.dumps(properties)))
        
        result = cur.fetchone()
        conn.commit()
        return result[0]

def insert_figure(conn, paper_id, figure_type, image_path, vlm_metadata: dict):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO figures (paper_id, figure_type, image_path, vlm_metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (paper_id, figure_type, image_path, json.dumps(vlm_metadata)))
        
        result = cur.fetchone()
        conn.commit()
        return result[0]

def get_materials(conn, material_name=None, limit=100):
    query = """
        SELECT m.*, p.doi, p.title, p.url 
        FROM material_extractions m
        JOIN papers p ON m.paper_id = p.id
        WHERE 1=1
    """
    params = []
    
    if material_name:
        query += " AND m.material_name = %s"
        params.append(material_name)
        
    query += " LIMIT %s"
    params.append(limit)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchall()

def get_figures_by_type(conn, figure_type):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM figures WHERE figure_type = %s", (figure_type,))
        return cur.fetchall()
