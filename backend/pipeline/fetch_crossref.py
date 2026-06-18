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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(BASE_DIR, "pdfs")

# We use a dummy but plausible email to satisfy Unpaywall's API requirements
UNPAYWALL_EMAIL = "polytrace.research@gmail.com"

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

def search_and_fetch():
    print("Connecting to PostgreSQL Document Store...")
    os.makedirs(PDF_DIR, exist_ok=True)
    conn = get_db_connection()

    queries = [
        "hydrogen storage MHPCTpro experimental",
        "metal hydride capacity desorption",
        "magnesium hydride ball milling PCT curve"
    ]

    for q in queries:
        print(f"\\n[*] Searching Crossref for: '{q}'")
        crossref_url = "https://api.crossref.org/works"
        params = {
            "query": q,
            "select": "DOI,title,author,container-title,published-print,URL",
            "rows": 10 # Search top 10 per query
        }
        res = requests.get(crossref_url, params=params)
        items = res.json().get("message", {}).get("items", [])

        for item in items:
            doi = item.get("DOI")
            title_list = item.get("title", [])
            if not doi or not title_list:
                continue
                
            title = title_list[0]
            
            # Check if already processed
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM papers WHERE doi=%s", (doi,))
                if cur.fetchone():
                    print(f"  [-] Skipping already processed: {title[:50]}...")
                    continue
                
            print(f"  [?] Checking Unpaywall for OA status: {title[:50]}...")
            unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
            u_res = requests.get(unpaywall_url)
            
            if u_res.status_code == 200:
                data = u_res.json()
                if data.get("is_oa") and data.get("best_oa_location"):
                    pdf_url = data.get("best_oa_location").get("url_for_pdf")
                    if pdf_url:
                        authors = ", ".join([a.get("family", "") for a in item.get("author", [])])
                        journal = item.get("container-title", [""])[0] if item.get("container-title") else ""
                        published = item.get("published-print", {}).get("date-parts", [[0]])[0][0]
                        year = published if published else 0
                        paper_url = item.get("URL", "")
                        
                        safe_title = "".join(c if c.isalnum() else "_" for c in title)[:40]
                        if not safe_title: safe_title = f"paper_{int(time.time())}"
                        safe_doi = "".join(c if c.isalnum() else "_" for c in doi) if doi else str(int(time.time()))
                        pdf_path = os.path.join(PDF_DIR, f"{safe_title}_{safe_doi}.pdf")

                        print(f"      [+] Open Access PDF found! Downloading...")
                        if download_pdf(pdf_url, pdf_path):
                            if not is_english_paper(pdf_path):
                                print(f"      [-] Not an English paper. Deleting.")
                                os.remove(pdf_path)
                                continue

                            try:
                                insert_paper(conn, doi, title, authors, journal, year, paper_url, pdf_path, is_open_access=True)
                                print(f"      [✓] Saved to Database.")
                            except psycopg2.IntegrityError:
                                conn.rollback()
                                print(f"      [!] Integrity Error. Skipping.")
                    else:
                        print(f"      [-] Open Access but no direct PDF link.")
                else:
                    print(f"      [-] Not Open Access.")
            
            time.sleep(1) # Be nice to Unpaywall

    conn.close()
    print("\\n[✓] Crossref/Unpaywall Fetch pipeline complete.")

if __name__ == "__main__":
    search_and_fetch()
