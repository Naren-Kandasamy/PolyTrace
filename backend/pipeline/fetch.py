import os
import requests
import time
import psycopg2
import fitz
from langdetect import detect, DetectorFactory

import sys
# Add backend to path to import crud
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.crud import get_db_connection, insert_paper

# Ensure consistent language detection
DetectorFactory.seed = 0

def is_english_paper(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return False
            
        # Check the middle page, or page 3, or the last page if too short
        page_num = min(2, len(doc) - 1)
        if len(doc) > 5:
            page_num = len(doc) // 2
            
        page_text = doc[page_num].get_text("text")
        
        # If middle page is empty, fallback to another page
        if not page_text.strip() and len(doc) > 1:
            page_text = doc[1].get_text("text")

        if not page_text.strip():
            return False

        lang = detect(page_text)
        return lang == 'en'
    except Exception as e:
        print(f"    [!] Language detection failed: {e}")
        return False

# Define relative paths based on script location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(BASE_DIR, "pdfs")

def search_semantic_scholar(query, limit=10, retries=3):
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,journal,openAccessPdf,url,externalIds",
        "openAccessPdf": "" # Enforce Open Access requirement
    }
    print(f"\\n[*] Searching Semantic Scholar for: '{query}'")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PolyTrace/1.0'}
    if api_key:
        headers['x-api-key'] = api_key
    else:
        print("    [!] Warning: No SEMANTIC_SCHOLAR_API_KEY found in environment. Rate limits will be strict.")
    
    for attempt in range(retries):
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return response.json().get("data", [])
        elif response.status_code == 429:
            wait_time = (attempt + 1) * 5
            print(f"[!] Rate limited (429). Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            print(f"[!] API Error: {response.status_code}")
            return []
            
    print("[!] Exceeded retries for query.")
    return []

def download_pdf(pdf_url, filename):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PolyTrace/1.0'}
    try:
        response = requests.get(pdf_url, headers=headers, timeout=15)
        if response.status_code == 200 and 'application/pdf' in response.headers.get('Content-Type', ''):
            with open(filename, 'wb') as f:
                f.write(response.content)
            return True
        else:
            print(f"    [!] Download failed: Status {response.status_code} or not a PDF.")
            return False
    except Exception as e:
        print(f"    [!] Failed to download {pdf_url}: {e}")
        return False

def format_authors(authors_list):
    if not authors_list: return ""
    return ", ".join([a.get("name", "") for a in authors_list])

def main():
    print("Connecting to PostgreSQL Document Store...")
    os.makedirs(PDF_DIR, exist_ok=True)
    conn = get_db_connection()

    # Pivot: Hydrogen Storage Search Queries
    queries = [
        "hydrogen storage MHPCTpro experimental",
        "metal hydride capacity desorption",
        "magnesium hydride ball milling PCT curve"
    ]

    for q in queries:
        papers = search_semantic_scholar(q, limit=5)
        for p in papers:
            oa_pdf = p.get("openAccessPdf")
            if not oa_pdf:
                continue
            
            pdf_url = oa_pdf.get("url")
            if not pdf_url:
                continue

            doi = p.get("externalIds", {}).get("DOI", "")
            title = p.get("title", "Untitled")
            
            # Check if paper already exists
            with conn.cursor() as cur:
                if doi:
                    cur.execute("SELECT id FROM papers WHERE doi=%s", (doi,))
                else:
                    cur.execute("SELECT id FROM papers WHERE title=%s", (title,))
                if cur.fetchone():
                    print(f"  [-] Skipping existing paper: {title[:50]}...")
                    continue

            authors = format_authors(p.get("authors", []))
            journal = p.get("journal", {}).get("name", "") if p.get("journal") else ""
            year = p.get("year", 0)
            paper_url = p.get("url", "")
            
            safe_title = "".join(c if c.isalnum() else "_" for c in title)[:40]
            if not safe_title: safe_title = f"paper_{int(time.time())}"
            safe_doi = "".join(c if c.isalnum() else "_" for c in doi) if doi else str(int(time.time()))
            pdf_path = os.path.join(PDF_DIR, f"{safe_title}_{safe_doi}.pdf")

            print(f"  [+] Downloading PDF: {title[:50]}...")
            if download_pdf(pdf_url, pdf_path):
                if not is_english_paper(pdf_path):
                    print(f"      [-] Not an English paper. Deleting.")
                    os.remove(pdf_path)
                    continue

                try:
                    insert_paper(conn, doi, title, authors, journal, year, paper_url, pdf_path, is_open_access=True)
                    print(f"      Saved to Database successfully.")
                except psycopg2.IntegrityError:
                    conn.rollback()
                    print(f"      [!] Integrity Error - likely duplicate DOI. Skipping.")
            
            # Rate limit courtesy
            time.sleep(2)

    conn.close()
    print("\\n[✓] Fetch pipeline complete.")

if __name__ == "__main__":
    main()
