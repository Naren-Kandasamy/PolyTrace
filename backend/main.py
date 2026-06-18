from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os

app = FastAPI(title="PolyTrace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "materials_ai"),
        user=os.getenv("DB_USER", "ncl"),
        password=os.getenv("DB_PASSWORD", "ncl_password"),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432")
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "project": "PolyTrace (Hydrogen Storage)"}

@app.get("/stats")
def get_stats():
    """Summary stats for the dashboard header."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check papers count
        cur.execute("SELECT COUNT(*) FROM papers")
        paper_count = cur.fetchone()[0]
        
        # Check material extractions
        cur.execute("SELECT COUNT(*) FROM material_extractions")
        extraction_count = cur.fetchone()[0]
        
        # Check figures count
        cur.execute("SELECT COUNT(*) FROM figures")
        figure_count = cur.fetchone()[0]
        
        conn.close()
        return {
            "papers": paper_count, 
            "extractions": extraction_count, 
            "figures": figure_count
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/papers")
def list_papers(domain: str = None, is_oa: bool = None, limit: int = 100):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        q = "SELECT id, doi, title, journal, year, is_open_access FROM papers WHERE 1=1"
        params = []
        if domain:
            # We assume domain is part of a flexible query or we can omit it for now since we pivoted to hydrogen storage
            pass 
        if is_oa is not None:
            q += " AND is_open_access=%s"
            params.append(is_oa)
        q += f" LIMIT {limit}"
        cur.execute(q, params)
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return results
    except Exception as e:
        return {"error": str(e)}

from fastapi import Query

@app.get("/extractions")
def list_extractions(
    material: str = Query(None),
    min_capacity: float = Query(None),
    limit: int = 50
):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # material_extractions table joins with papers
        q = """SELECT e.id, p.doi, p.title, e.properties, e.material_name 
               FROM material_extractions e JOIN papers p ON p.id = e.paper_id
               WHERE 1=1"""
        params = []
        if material:
            q += " AND e.material_name ILIKE %s"
            params.append(f"%{material}%")
        if min_capacity:
            q += " AND (e.properties->>'max_hydrogen_capacity_wt_percent')::float >= %s"
            params.append(min_capacity)
        q += f" LIMIT {limit}"
        cur.execute(q, params)
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return results
    except Exception as e:
        return {"error": str(e)}

from pydantic import BaseModel
class ExtractRequest(BaseModel):
    doi: str
    prompt: str

@app.post("/extract")
def trigger_extraction(req: ExtractRequest):
    """Trigger on-demand extraction for a paper with a custom prompt."""
    # Stub - would fetch the PDF, run pipeline, and insert result.
    return {"status": "queued", "doi": req.doi, "prompt": req.prompt}

if __name__ == "__main__":
    import uvicorn
    # Execute with: uvicorn main:app --reload --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

