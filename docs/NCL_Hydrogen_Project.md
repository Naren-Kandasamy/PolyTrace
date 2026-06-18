# NCL Internship — Generalized Materials AI Platform
**Project Name:** PolyTrace (Pivoted) → Materials AI Platform  
**Supervisor:** Dr. Kavita Joshi, CSIR-NCL Pune  
**Duration:** Summer 2026 (8 weeks)  
**Stack:** Python, RAG, Open-Source LLMs/VLMs, PostgreSQL (JSONB), FastAPI, React  
**Constraint:** 100% open-source — no proprietary APIs (no OpenAI, no Google Cloud)

---

## 1. Problem Statement

Build a **generalized, multimodal AI extraction platform** for materials science literature. Phase 1 focuses on **Hydrogen Storage** materials (metal hydrides, MHPCTpro etc.).

For each paper, extract based on dynamic user-supplied prompts:

**Text data:**
- Material composition and synthesis protocol
- Experimental conditions (temperature, pressure, reaction time)
- Performance metrics (max H₂ capacity wt%, desorption temperature)
- Author metadata and project objectives

**Image/plot data:**
- Classify plot types (PCT curves, XRD patterns, DSC curves etc.)
- Read axes labels and units
- Extract high-level metrics (maximums, minimums, trends)

Then:
- Store in a flexible document-style database (no rigid schema — prompt-driven key-value pairs)
- Serve via a React dashboard hosted on the NCL network
- Long-term: human-in-the-loop corrections feed back into model retraining

**Constraint:** Experimental data only. No computational/theoretical values.

---

## 2. Hydrogen Storage — Domain Primer

**What is hydrogen storage?** Storing hydrogen gas in a solid material (metal hydride) so it can be safely carried and released on demand. The metal absorbs H₂ under pressure and releases it when heated.

**Key materials:**
- **MgH₂** — magnesium hydride, most studied, high capacity (~7.6 wt%) but high desorption temp (~300°C)
- **LaNi₅** — lanthanum nickel alloy, fast kinetics, low capacity (~1.4 wt%)
- **TiFe** — cheap, moderate capacity (~1.8 wt%)
- **Metal hydride composites** — base material + catalyst dopants (e.g. MgH₂ + 5% Ni)

**Key properties papers report:**
- **H₂wt%** — weight percent of hydrogen stored (max capacity)
- **Desorption temperature (°C)** — temperature needed to release hydrogen
- **PCT curve** — Pressure-Composition-Temperature curve, the signature plot for any hydride
- **XRD pattern** — X-ray diffraction, used to confirm crystal structure
- **Activation energy** — energy barrier for hydrogen absorption/desorption
- **Synthesis protocol** — how the material was made (ball milling, arc melting, etc.)

**Why PCT curves matter:** The PCT curve is the single most important characterization plot for a hydrogen storage material — it shows how much hydrogen is absorbed at different pressures and temperatures. Extracting the plateau pressure and maximum capacity from this curve is a core task of this project.

---

## 3. Pipeline Architecture

```
INPUT
  Keyword search ("metal hydrides PCT", "MgH2 hydrogen storage")
  Unpaywall API → filter Free vs Paid from DOI list
  ChemRxiv API / Semantic Scholar → download open-access PDFs
        |
        v
PARSING
  PyMuPDF → extract raw text, chunk by section headings
  pdfplumber → extract tables → Pandas DataFrames
  PyMuPDF → crop figure images from pages
  langdetect → skip non-English papers
        |
        v
MULTIMODAL EXTRACTION
  Text path:   sentence-transformers → FAISS → retrieve relevant chunks
               Llama-3-8B / Gemma-2-9B → dynamic prompt → JSON output
  Vision path: Qwen2-VL / Llama-3.2-Vision → classify + read plot axes
  Validation layer → physical bounds + consistency checks
        |
        v
DATABASE
  PostgreSQL (JSONB) — flexible document storage
  One document per paper, extracted_data is a dynamic key-value store
  Citation linking via DOI
        |
        v
ADAPTIVE UI
  FastAPI backend → REST endpoints
  React dashboard → query, filter, visualize
  (R&D) Human-in-the-loop corrections → model retraining pipeline
```

---

## 4. Database Strategy — Why JSONB Not Rigid SQL

The old PolyTrace schema had hardcoded columns (`mn`, `mw`, `tensile_strength`). That breaks the moment a different material type is added — hydrogen storage has completely different properties than polymers.

**New approach: PostgreSQL with JSONB**

JSONB gives you:
- Flexible schema — each paper can have different extracted fields
- Still queryable — PostgreSQL can index and query inside JSONB fields
- Still relational — papers table stays rigid (DOI, title etc.), only `extracted_data` is flexible

```sql
-- Papers: rigid metadata for citation and deduplication
CREATE TABLE papers (
    id              SERIAL PRIMARY KEY,
    doi             TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    authors         TEXT,
    journal         TEXT,
    year            INTEGER,
    url             TEXT,                   -- journal page link
    pdf_path        TEXT,                   -- local file path (internal only)
    domain          TEXT DEFAULT 'hydrogen_storage',
    is_open_access  BOOLEAN DEFAULT FALSE,
    added_at        TIMESTAMP DEFAULT NOW()
);

-- Extractions: one row per extraction run per paper
CREATE TABLE extractions (
    id                  SERIAL PRIMARY KEY,
    paper_id            INTEGER REFERENCES papers(id),
    extraction_prompt   TEXT NOT NULL,      -- the user-supplied prompt used
    extracted_data      JSONB NOT NULL,     -- flexible key-value output
    figures_detected    TEXT[],             -- array of detected plot types
    model_used          TEXT,               -- e.g. "llama3-8b", "qwen2-vl"
    validation_flags    TEXT[],             -- any warnings raised
    is_valid            BOOLEAN DEFAULT TRUE,
    extracted_at        TIMESTAMP DEFAULT NOW()
);

-- Index for fast JSONB queries
CREATE INDEX idx_extracted_data ON extractions USING GIN (extracted_data);
```

**Example document stored in extracted_data:**
```json
{
  "material": "MgH2 + 5% Ni",
  "max_capacity_wt_percent": 6.5,
  "desorption_temp_c": 300,
  "absorption_pressure_bar": 10.0,
  "synthesis_protocol": "Ball milling under Argon for 10 hours at 300 rpm.",
  "catalyst": "Ni (5 wt%)",
  "activation_cycles": 3,
  "crystal_structure": "FCC",
  "plot_types_found": ["PCT Curve", "XRD Pattern"],
  "plateau_pressure_bar": 8.5
}
```

**Querying JSONB in PostgreSQL:**
```sql
-- Find all papers with H2 capacity > 5 wt%
SELECT p.doi, p.title, e.extracted_data->>'max_capacity_wt_percent'
FROM extractions e
JOIN papers p ON p.id = e.paper_id
WHERE (e.extracted_data->>'max_capacity_wt_percent')::float > 5.0;

-- Find all papers mentioning MgH2
SELECT p.title FROM extractions e
JOIN papers p ON p.id = e.paper_id
WHERE e.extracted_data->>'material' ILIKE '%MgH2%';
```

---

## 5. Key Code Snippets

### 5.1 Paper Fetching — ChemRxiv + Unpaywall Filter

```python
import requests

CHEMRXIV_API = "https://chemrxiv.org/engage/chemrxiv/public-api/v1"
UNPAYWALL_EMAIL = "naren@ncl.ac.in"   # required by Unpaywall

def fetch_chemrxiv(keyword: str, limit: int = 50) -> list[dict]:
    """Fetch papers from ChemRxiv by keyword."""
    params = {"term": keyword, "limit": limit, "skip": 0}
    resp = requests.get(f"{CHEMRXIV_API}/items", params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("itemHits", [])
    return [{
        "doi":   item["item"].get("doi"),
        "title": item["item"].get("title"),
        "pdf":   item["item"].get("asset", {}).get("original", {}).get("url"),
        "year":  item["item"].get("publishedDate", "")[:4],
    } for item in items if item["item"].get("doi")]


def check_open_access(doi: str) -> dict:
    """Check if a paper is open access via Unpaywall."""
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
        return {
            "is_oa": data.get("is_oa", False),
            "pdf_url": data.get("best_oa_location", {}).get("url_for_pdf"),
        }
    except Exception:
        return {"is_oa": False, "pdf_url": None}


def filter_papers(dois: list[str]) -> dict:
    """Split a list of DOIs into free and paid buckets."""
    free, paid = [], []
    for doi in dois:
        result = check_open_access(doi)
        if result["is_oa"] and result["pdf_url"]:
            free.append({"doi": doi, "pdf_url": result["pdf_url"]})
        else:
            paid.append(doi)
    print(f"Free: {len(free)} | Paid (manual): {len(paid)}")
    return {"free": free, "paid": paid}


def download_pdf(pdf_url: str, output_path: str) -> bool:
    """Download a PDF to disk."""
    try:
        resp = requests.get(pdf_url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False
```

### 5.2 PDF Parsing — Text + Figure Extraction

```python
import fitz   # PyMuPDF
import pdfplumber
from pathlib import Path

def extract_text_by_section(pdf_path: str) -> dict:
    """Extract text chunked by section headings."""
    doc = fitz.open(pdf_path)
    sections = {}
    current = "preamble"

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                spans = line["spans"]
                if not spans:
                    continue
                text = " ".join(s["text"] for s in spans).strip()
                size = spans[0]["size"]
                if size > 11 and len(text) < 80 and text:
                    current = text.lower()
                    sections[current] = ""
                else:
                    sections.setdefault(current, "")
                    sections[current] += text + " "
    return sections


def extract_figures(pdf_path: str, output_dir: str) -> list[str]:
    """Crop and save all figures from a PDF as images."""
    doc = fitz.open(pdf_path)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    saved = []

    for page_num, page in enumerate(doc):
        # Get image list
        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            ext = base_image["ext"]
            out_path = f"{output_dir}/page{page_num}_fig{img_idx}.{ext}"
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            saved.append(out_path)

    return saved


def extract_tables(pdf_path: str) -> list:
    """Extract all tables as DataFrames."""
    import pandas as pd
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if table and len(table) > 1:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    tables.append(df)
    return tables
```

### 5.3 Text Extraction — Dynamic Prompt + LLM

```python
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch, json

# Load Llama3-8B quantized (runs on ~5GB VRAM)
pipe = pipeline(
    "text-generation",
    model="meta-llama/Meta-Llama-3-8B-Instruct",
    model_kwargs={"torch_dtype": torch.float16, "load_in_4bit": True},
    device_map="auto"
)

SYSTEM_PROMPT = """You are a materials science data extractor.
Given text from a scientific paper, extract the information requested.
Return ONLY a valid JSON object. Use null for fields not found.
Do not include any preamble or explanation."""

def extract_text_data(context: str, user_prompt: str) -> dict:
    """
    Dynamic extraction — user supplies their own prompt.
    e.g. user_prompt = "Extract the material name, max H2 capacity, and synthesis method"
    """
    full_prompt = f"""{SYSTEM_PROMPT}

User request: {user_prompt}

Paper text:
{context[:3000]}

JSON output:"""

    output = pipe(full_prompt, max_new_tokens=512, temperature=0.1,
                  do_sample=False)[0]["generated_text"]

    # Parse JSON from output
    start = output.rfind("{")
    end = output.rfind("}") + 1
    if start == -1:
        return {}
    try:
        return json.loads(output[start:end])
    except json.JSONDecodeError:
        return {}
```

### 5.4 Vision Extraction — Plot Classification + Axis Reading

```python
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from PIL import Image
import torch, json

# Load Qwen2-VL (vision-language model)
model_id = "Qwen/Qwen2-VL-7B-Instruct"
processor = AutoProcessor.from_pretrained(model_id)
vlm = Qwen2VLForConditionalGeneration.from_pretrained(
    model_id, torch_dtype=torch.float16, device_map="auto"
)

VISION_PROMPT = """Analyze this scientific figure from a materials science paper.
Return ONLY a JSON object with these fields:
{
  "plot_type": "one of: PCT Curve, XRD Pattern, DSC Curve, SEM Image, TEM Image, Bar Chart, Other",
  "x_axis_label": "<string or null>",
  "y_axis_label": "<string or null>",
  "x_axis_units": "<string or null>",
  "y_axis_units": "<string or null>",
  "max_value": <number or null>,
  "key_observation": "<one sentence summary or null>"
}"""

def extract_figure_data(image_path: str) -> dict:
    """Extract structured info from a figure using Qwen2-VL."""
    image = Image.open(image_path).convert("RGB")

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": VISION_PROMPT}
        ]
    }]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[image], return_tensors="pt").to(vlm.device)

    with torch.no_grad():
        output_ids = vlm.generate(**inputs, max_new_tokens=256)

    output = processor.decode(output_ids[0], skip_special_tokens=True)
    start = output.rfind("{")
    end = output.rfind("}") + 1
    try:
        return json.loads(output[start:end])
    except json.JSONDecodeError:
        return {}
```

### 5.5 Validation Layer

```python
# Physical bounds for hydrogen storage properties
BOUNDS = {
    "max_capacity_wt_percent": (0.1, 7.6),     # theoretical max for known hydrides
    "desorption_temp_c":       (-50, 600),
    "absorption_pressure_bar": (0.001, 1000),
    "plateau_pressure_bar":    (0.001, 1000),
    "activation_cycles":       (1, 100),
}

def validate(extracted: dict) -> dict:
    """Flag physically impossible values."""
    flags = []
    for field, (lo, hi) in BOUNDS.items():
        val = extracted.get(field)
        if val is not None:
            try:
                val = float(val)
                if not (lo <= val <= hi):
                    flags.append(f"{field}={val} out of expected range [{lo}, {hi}]")
            except (TypeError, ValueError):
                flags.append(f"{field} is not a number: {val}")

    extracted["_validation_flags"] = flags
    extracted["_is_valid"] = len(flags) == 0
    return extracted
```

### 5.6 Database Insert

```python
import psycopg2, json
from datetime import datetime

def get_conn():
    return psycopg2.connect(
        host="localhost", dbname="materials_ai",
        user="ncl", password="ncl_password"
    )

def insert_paper(doi, title, authors, journal, year, url, is_oa=False):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papers (doi, title, authors, journal, year, url, is_open_access)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doi) DO NOTHING
                RETURNING id
            """, (doi, title, authors, journal, year, url, is_oa))
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None

def insert_extraction(paper_id, prompt, extracted_data, figures, model):
    flags = extracted_data.pop("_validation_flags", [])
    is_valid = extracted_data.pop("_is_valid", True)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO extractions
                    (paper_id, extraction_prompt, extracted_data, figures_detected, model_used, validation_flags, is_valid)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (paper_id, prompt, json.dumps(extracted_data),
                  figures, model, flags, is_valid))
            conn.commit()
            return cur.fetchone()[0]
```

### 5.7 FastAPI Backend

```python
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2, json

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/papers")
def list_papers(domain: str = None, is_oa: bool = None, limit: int = 100):
    with get_conn() as conn:
        with conn.cursor() as cur:
            q = "SELECT id, doi, title, journal, year, is_open_access FROM papers WHERE 1=1"
            params = []
            if domain:
                q += " AND domain=%s"; params.append(domain)
            if is_oa is not None:
                q += " AND is_open_access=%s"; params.append(is_oa)
            q += f" LIMIT {limit}"
            cur.execute(q, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

@app.get("/extractions")
def list_extractions(
    material: str = Query(None),
    min_capacity: float = Query(None),
    limit: int = 50
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            q = """SELECT e.id, p.doi, p.title, e.extracted_data, e.figures_detected
                   FROM extractions e JOIN papers p ON p.id = e.paper_id
                   WHERE e.is_valid = TRUE"""
            params = []
            if material:
                q += " AND e.extracted_data->>'material' ILIKE %s"
                params.append(f"%{material}%")
            if min_capacity:
                q += " AND (e.extracted_data->>'max_capacity_wt_percent')::float >= %s"
                params.append(min_capacity)
            q += f" LIMIT {limit}"
            cur.execute(q, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

@app.get("/stats")
def stats():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM papers")
            papers = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM extractions WHERE is_valid=TRUE")
            extractions = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM papers WHERE is_open_access=TRUE")
            open_access = cur.fetchone()[0]
            return {"papers": papers, "extractions": extractions, "open_access": open_access}

@app.post("/extract")
def run_extraction(doi: str, prompt: str):
    """Trigger on-demand extraction for a paper with a custom prompt."""
    # Stub — in practice fetches the PDF, runs pipeline, inserts result
    return {"status": "queued", "doi": doi, "prompt": prompt}
```

---

## 6. Paper Sources

### Open Access (start here, no institutional access needed)

| Source | API | Coverage |
|---|---|---|
| ChemRxiv | `chemrxiv.org/engage/chemrxiv/public-api/v1/items` | Chemistry preprints, excellent for materials |
| Semantic Scholar | `api.semanticscholar.org/graph/v1/paper/search` | Broad, needs API key for bulk |
| Unpaywall | `api.unpaywall.org/v2/{doi}?email=...` | Finds legal open PDF for any DOI |
| Europe PMC | `europepmc.org/RestfulWebService` | Some materials coverage |

### Search Keywords for Hydrogen Storage

```
"metal hydride" "hydrogen storage" experimental
"MgH2" synthesis characterization PCT
"LaNi5" hydrogen absorption desorption
"hydrogen storage" "wt%" "PCT curve"
"TiFe" OR "MgH2" OR "LaNi5" "hydrogen" experimental
```

### Paywalled Sources (need institutional access from NCL)

- Elsevier — Journal of Alloys and Compounds (major hydrogen storage journal)
- Elsevier — International Journal of Hydrogen Energy
- ACS — Journal of Physical Chemistry C
- Wiley — Advanced Energy Materials

---

## 7. Tech Stack (100% Open Source)

| Layer | Tool | Why |
|---|---|---|
| PDF text parsing | PyMuPDF (fitz) | Best text + figure extraction from PDFs |
| PDF table parsing | pdfplumber | Structured table → DataFrame |
| Language detection | langdetect | Skip non-English papers |
| Embedding | sentence-transformers (all-MiniLM-L6-v2) | Fast, local, no API needed |
| Vector store | FAISS | Efficient chunk retrieval for RAG |
| Text LLM | Llama-3-8B / Gemma-2-9B | Open weights, strong scientific text parsing |
| Vision LLM | Qwen2-VL-7B / Llama-3.2-Vision | Open weights, best available for chart understanding |
| Model runtime | Ollama / vLLM | Local API server, zero cost, works offline |
| Quantization | bitsandbytes | 4-bit compression so models run on ~5-8GB VRAM |
| Database | PostgreSQL (JSONB) | Flexible schema, queryable JSON, production-grade |
| Backend | FastAPI | Async, fast, auto docs |
| Frontend | React + Plotly | Proper state, interactive charts |
| Paper fetching | requests + ChemRxiv API + Unpaywall | Official APIs, no IP ban risk |
| Testing | pytest + responses | Pipeline unit testing |

### Install

```bash
pip install pymupdf pdfplumber sentence-transformers faiss-cpu \
            transformers bitsandbytes accelerate torch \
            plotly pandas requests psycopg2-binary \
            fastapi uvicorn langdetect pillow
```

---

## 8. Weekly Plan

| Week | Goal | Deliverable |
|---|---|---|
| 1 | Setup + paper fetching | ChemRxiv + Unpaywall pipeline, free vs paid split working |
| 2 | PDF parsing + chunking | Clean text + table extraction on 20 seed papers |
| 3 | RAG + text LLM extraction | Dynamic prompt extraction → JSON on seed papers |
| 4 | Validation + DB | PostgreSQL live, insertion working, JSONB queries tested |
| 5 | Full text pipeline | 100+ papers processed, accuracy benchmarked on gold-standard set |
| 6 | Vision VLM integration | Qwen2-VL classifying plot types + reading axes from figures |
| 7 | FastAPI + React dashboard | Query, filter, view extractions in browser |
| 8 | Scale + handover | 300+ papers, documentation, final report |

---

## 9. Weekly Report Template

```
## Week N Report — [Date]
**Papers fetched:** X  |  **Papers parsed:** X  |  **Extractions in DB:** X

### What I did
-

### Results / findings
-

### Accuracy check (10 manual verifications against gold-standard papers)
| Field | Correct | Wrong | Missing |
|---|---|---|---|
| Material name | | | |
| Max capacity (wt%) | | | |
| Desorption temp | | | |
| Synthesis protocol | | | |

### Issues / blockers
-

### Plan for next week
-
```

---

## 10. App Architecture — FastAPI + React

```
ncl-materials-ai/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── pipeline/
│   │   ├── fetch.py         # ChemRxiv + Unpaywall fetching
│   │   ├── parse.py         # PDF text + figure extraction
│   │   ├── extract_text.py  # LLM text extraction
│   │   ├── extract_vision.py # VLM figure extraction
│   │   └── validate.py      # Bounds checking
│   └── db/
│       ├── schema.sql
│       └── crud.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PaperTable.jsx       # searchable paper list
│   │   │   ├── ExtractionViewer.jsx # view JSON extraction output
│   │   │   ├── PromptInput.jsx      # custom prompt entry
│   │   │   └── FigureGallery.jsx    # view detected figures + VLM output
│   │   └── App.jsx
│   └── package.json
└── NCL_Hydrogen_Project.md
```

---

## 11. Open Questions

- [ ] Gold-standard seed papers — waiting on Dr. Joshi to provide 3-5 verified papers
- [ ] NCL institutional access — which Elsevier/ACS journals are accessible?
- [ ] Deployment target — which server at NCL will host the app? GPU available?
- [ ] Model preference — does NCL prefer Llama-3 or Qwen2 for internal hosting?
- [ ] Active learning scope — is human-in-the-loop retraining in scope for this internship or R&D only?
- [ ] Reference paper — ChemRxiv 10002052 (mentioned by Dr. Joshi) — need to read and align architecture with it

---

*Last updated: June 12, 2026 — Pivot from PolyTrace (PE/PP) to Hydrogen Storage*
