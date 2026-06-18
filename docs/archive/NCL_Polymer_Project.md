> [!WARNING]
> **DEPRECATED (June 2026):** This project has pivoted to Hydrogen Storage and a generalized, multimodal architecture. Please see `Pivot_Hydrogen_Storage.md` and `NCL_Hydrogen_Project.md` for current details.

# NCL Internship — Polymer MWD Extraction Project (DEPRECATED)
**Supervisor:** Dr. Kavita Joshi, CSIR-NCL Pune  
**Duration:** Summer 2026  
**Stack:** Python, RAG, LLMs, PostgreSQL/SQLite, Matplotlib/Plotly

---

## 1. Problem Statement

Extract structured data from published experimental literature on three polymer variants:

| Polymer | Variant |
|---|---|
| Polyethylene (PE) | High Density (HDPE), Low Density (LDPE) |
| Polypropylene (PP) | Single variant (PP is naturally low density — no HD/LD split) |

For each paper, extract:
- **Molecular Weight Distribution** — Mn, Mw, dispersity Đ (= Mw/Mn)
- **Processing method** — how the polymer was synthesized/processed
- **Mechanical properties** — tensile strength, elongation at break, Young's modulus etc.
- **Chemical composition** — catalyst type, additives, comonomer content
- **Operational parameters** — temperature, pressure, reaction time, solvent

Then:
- Design a relational database to store all extracted data with citations
- Reconstruct MWD curves from Mn/Mw/Đ using log-normal distribution
- Visualize and compare across polymer types

**Constraint:** Experimental data only. No computational/theoretical values.

---

## 2. Chemistry Primer (what these terms mean)

**Polyethylene (PE):** Polymer made of repeating ethylene (CH₂–CH₂) units.
- **HDPE** — tightly packed, crystalline, stiff, high strength (milk jugs, pipes)
- **LDPE** — branched chains, flexible, lower density (plastic bags, film)

**Polypropylene (PP):** Polymer made of propylene (CH₂–CHCH₃) units. Naturally a lower density plastic — unlike PE, there is no meaningful HD/LD distinction. PP is instead classified by **tacticity**:
- **Isotactic PP** — most common, chains arranged regularly, semi-crystalline, stiff
- **Atactic PP** — irregular arrangement, amorphous, soft
- **Syndiotactic PP** — alternating arrangement, less common

**Molecular Weight Distribution (MWD):**
- Polymers aren't uniform — chains have different lengths
- **Mn** = number-average molecular weight (sensitive to short chains)
- **Mw** = weight-average molecular weight (sensitive to long chains)
- **Đ (dispersity)** = Mw/Mn. Narrow (Đ~1) = uniform chains. Broad (Đ>2) = wide range of chain lengths
- Measured experimentally by **GPC (Gel Permeation Chromatography)**

**Why MWD matters:** It directly determines mechanical properties — a narrow MWD gives better tensile strength, a broad MWD gives better processability.

---

## 3. Pipeline Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      INPUT LAYER                         │
│   PDFs from NCL library + open-access (Semantic Scholar) │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    PARSING LAYER                         │
│  PyMuPDF  →  extract raw text + tables per section      │
│  pdfplumber  →  structured table extraction             │
│  Section splitter  →  tag chunks by section type        │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  EMBEDDING + RETRIEVAL                   │
│  sentence-transformers  →  embed chunks                 │
│  FAISS / ChromaDB  →  vector store                      │
│  Query: "Extract Mn, Mw, dispersity for [polymer]"      │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    EXTRACTION LAYER                      │
│  Llama3-8B / Gemma2-9B (quantized, 4-bit)              │
│  Structured prompt → JSON output                        │
│  Validation layer → bounds checking                     │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    DATABASE LAYER                        │
│  SQLite (dev) / PostgreSQL (prod)                       │
│  Relational schema with citation linking                │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 VISUALIZATION LAYER                      │
│  MWD curve reconstruction (log-normal)                  │
│  EDA plots — compare across polymer types               │
│  Plotly interactive dashboard (optional)                │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Database Schema

```sql
-- Papers table
CREATE TABLE papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doi         TEXT UNIQUE,
    title       TEXT NOT NULL,
    authors     TEXT,
    journal     TEXT,
    year        INTEGER,
    url         TEXT,       -- direct link to paper on journal site
    pdf_path    TEXT,       -- local path, purely for processing, not citation
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Polymer samples table (one paper can have many samples)
CREATE TABLE polymer_samples (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id            INTEGER REFERENCES papers(id),
    polymer_type        TEXT CHECK(polymer_type IN ('HDPE','LDPE','PP')),

    -- Molecular weight distribution
    mn                  REAL,       -- number-average MW (g/mol)
    mw                  REAL,       -- weight-average MW (g/mol)
    dispersity          REAL,       -- Đ = Mw/Mn
    mw_method           TEXT,       -- e.g. "GPC", "SEC"

    -- Processing
    processing_method   TEXT,       -- e.g. "Ziegler-Natta", "metallocene"
    catalyst            TEXT,
    solvent             TEXT,
    temperature_c       REAL,       -- reaction temperature (°C)
    pressure_bar        REAL,
    reaction_time_min   REAL,

    -- Chemical composition
    comonomer           TEXT,
    comonomer_content   REAL,       -- mol%
    additives           TEXT,

    -- Mechanical properties
    tensile_strength    REAL,       -- MPa
    elongation_break    REAL,       -- %
    youngs_modulus      REAL,       -- MPa
    impact_strength     REAL,       -- kJ/m²
    crystallinity       REAL,       -- %

    -- Meta
    sample_label        TEXT,       -- label used in paper (e.g. "Sample A")
    notes               TEXT,
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- For storing reconstructed MWD curve points
CREATE TABLE mwd_curves (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id       INTEGER REFERENCES polymer_samples(id),
    log_mw          REAL,   -- log10(molecular weight)
    intensity       REAL    -- dW/d(logM) normalized
);
```

---

## 5. Key Code Snippets

### 5.1 PDF Text + Table Extraction

```python
import fitz  # PyMuPDF
import pdfplumber

def extract_text_by_section(pdf_path: str) -> dict:
    """Extract text chunked by section heading."""
    doc = fitz.open(pdf_path)
    sections = {}
    current_section = "preamble"
    
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    text = " ".join([s["text"] for s in line["spans"]])
                    # Detect section headings by font size
                    font_size = line["spans"][0]["size"] if line["spans"] else 0
                    if font_size > 11 and len(text) < 80:
                        current_section = text.strip().lower()
                        sections[current_section] = ""
                    else:
                        sections.setdefault(current_section, "")
                        sections[current_section] += text + " "
    return sections


def extract_tables(pdf_path: str) -> list:
    """Extract all tables from PDF as list of DataFrames."""
    import pandas as pd
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    tables.append(df)
    return tables
```

### 5.2 Chunking + Embedding

```python
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

def build_vector_store(chunks: list[str]) -> tuple:
    """Embed chunks and build FAISS index."""
    embeddings = model.encode(chunks, show_progress_bar=True)
    embeddings = np.array(embeddings).astype("float32")
    
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index, embeddings

def retrieve(query: str, index, chunks: list[str], k: int = 5) -> list[str]:
    """Retrieve top-k most relevant chunks for a query."""
    q_emb = model.encode([query]).astype("float32")
    distances, indices = index.search(q_emb, k)
    return [chunks[i] for i in indices[0]]
```

### 5.3 LLM Extraction with Structured Output

```python
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch
import json

# Load quantized model (runs on ~5GB VRAM)
model_id = "meta-llama/Meta-Llama-3-8B-Instruct"

pipe = pipeline(
    "text-generation",
    model=model_id,
    model_kwargs={"torch_dtype": torch.float16, "load_in_4bit": True},
    device_map="auto"
)

EXTRACTION_PROMPT = """You are a polymer chemistry data extractor.
Given the following text from a scientific paper, extract the molecular weight data.
Return ONLY a valid JSON object with these fields (use null if not found):
{{
  "polymer_type": "HDPE|LDPE|HDPP|LDPP|null",
  "mn": <number in g/mol or null>,
  "mw": <number in g/mol or null>,
  "dispersity": <number or null>,
  "mw_method": "<string or null>",
  "processing_method": "<string or null>",
  "temperature_c": <number or null>,
  "pressure_bar": <number or null>,
  "tensile_strength_mpa": <number or null>,
  "sample_label": "<string or null>"
}}

Text:
{context}

JSON:"""

def extract_polymer_data(context: str) -> dict:
    prompt = EXTRACTION_PROMPT.format(context=context)
    output = pipe(prompt, max_new_tokens=512, temperature=0.1)[0]["generated_text"]
    
    # Parse JSON from output
    json_start = output.rfind("{")
    json_end = output.rfind("}") + 1
    try:
        return json.loads(output[json_start:json_end])
    except json.JSONDecodeError:
        return {}
```

### 5.4 Validation Layer

```python
# Physical bounds for polymer properties
BOUNDS = {
    "mn":               (1_000,    10_000_000),   # g/mol
    "mw":               (1_000,    10_000_000),   # g/mol
    "dispersity":       (1.0,      50.0),
    "temperature_c":    (-50,      300),
    "tensile_strength": (1,        1000),          # MPa
    "elongation_break": (0.1,      2000),          # %
}

def validate(entry: dict) -> dict:
    """Flag out-of-bounds values rather than silently dropping them."""
    flags = []
    for field, (lo, hi) in BOUNDS.items():
        val = entry.get(field)
        if val is not None and not (lo <= val <= hi):
            flags.append(f"{field}={val} out of range [{lo}, {hi}]")
    
    # Đ consistency check
    mn, mw = entry.get("mn"), entry.get("mw")
    if mn and mw:
        computed_d = mw / mn
        reported_d = entry.get("dispersity")
        if reported_d and abs(computed_d - reported_d) > 0.1:
            flags.append(f"Dispersity mismatch: computed={computed_d:.2f}, reported={reported_d}")
    
    entry["validation_flags"] = flags
    entry["is_valid"] = len(flags) == 0
    return entry
```

### 5.5 MWD Curve Reconstruction

```python
import numpy as np
import matplotlib.pyplot as plt

def reconstruct_mwd(mn: float, mw: float, label: str = "", ax=None):
    """
    Reconstruct MWD curve from Mn and Mw using log-normal distribution.
    This is the standard approach — same as how GPC curves are modelled.
    """
    dispersity = mw / mn
    
    # Log-normal parameters
    sigma = np.sqrt(np.log(dispersity))
    mu = np.log(mn) + sigma ** 2  # so that mean of distribution = Mn
    
    # MW range: 3 decades around Mn
    mw_range = np.logspace(
        np.log10(mn) - 1.5,
        np.log10(mn) + 1.5 * dispersity,
        1000
    )
    
    # dW/d(logM) — weight distribution
    mwd = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(
        -(np.log(mw_range) - mu) ** 2 / (2 * sigma ** 2)
    )
    mwd /= mwd.max()  # normalize to 1
    
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))
    
    ax.semilogx(mw_range, mwd, label=label or f"Mn={mn:.0f}, Mw={mw:.0f}, Đ={dispersity:.2f}")
    ax.set_xlabel("Molecular Weight (g/mol)")
    ax.set_ylabel("Normalized Intensity dW/d(logM)")
    ax.set_title("Molecular Weight Distribution")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return ax


def compare_polymers(samples: list[dict]):
    """Overlay MWD curves for multiple polymer samples."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    axes = axes.flatten()
    
    polymer_types = ["HDPE", "LDPE", "PP"]
    colors = plt.cm.tab10.colors
    
    for i, ptype in enumerate(polymer_types):
        ax = axes[i]
        ax.set_title(ptype)
        subset = [s for s in samples if s.get("polymer_type") == ptype]
        
        for j, sample in enumerate(subset):
            if sample.get("mn") and sample.get("mw"):
                reconstruct_mwd(
                    sample["mn"], sample["mw"],
                    label=sample.get("sample_label", f"Sample {j+1}"),
                    ax=ax
                )
        ax.set_xlabel("Molecular Weight (g/mol)")
        ax.set_ylabel("dW/d(logM)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7)
    
    plt.tight_layout()
    plt.savefig("mwd_comparison.png", dpi=150)
    plt.show()
```

### 5.6 Database Insert

```python
import sqlite3
from datetime import datetime

def insert_paper(conn, doi, title, authors, journal, year, url, pdf_path):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO papers (doi, title, authors, journal, year, url, pdf_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (doi, title, authors, journal, year, url, pdf_path))
    conn.commit()
    return cur.lastrowid

def insert_sample(conn, paper_id, data: dict):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO polymer_samples (
            paper_id, polymer_type, mn, mw, dispersity, mw_method,
            processing_method, catalyst, temperature_c, pressure_bar,
            tensile_strength, elongation_break, sample_label, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paper_id,
        data.get("polymer_type"),
        data.get("mn"),
        data.get("mw"),
        data.get("dispersity"),
        data.get("mw_method"),
        data.get("processing_method"),
        data.get("catalyst"),
        data.get("temperature_c"),
        data.get("pressure_bar"),
        data.get("tensile_strength_mpa"),
        data.get("elongation_break"),
        data.get("sample_label"),
        str(data.get("validation_flags", []))
    ))
    conn.commit()
    return cur.lastrowid
```

---

## 6. Paper Sources

### Open Access (start here)
| Source | How to use | Coverage |
|---|---|---|
| Semantic Scholar API | `api.semanticscholar.org` — search by keyword, filter by has_pdf | Good, free |
| Unpaywall API | `api.unpaywall.org/v2/{doi}` — finds legal open PDF | Patchy |
| Core.ac.uk | `core.ac.uk/api` — aggregates open-access | Decent |
| PubChem | Has some polymer data but not MWD focus | Limited |

### Institutional Access (best coverage)
NCL has CSIR library subscriptions — ask Dr. Joshi for access to:
- **Elsevier** (Polymer, European Polymer Journal)
- **ACS** (Macromolecules, ACS Applied Polymer Materials)
- **Wiley** (Journal of Polymer Science)
- **RSC** (Polymer Chemistry)

### Search queries to use
```
("HDPE" OR "high density polyethylene") AND ("molecular weight" OR "GPC") AND "experimental"
("LDPE" OR "low density polyethylene") AND ("Mn" OR "Mw" OR "dispersity")
("polypropylene" OR "PP") AND "molecular weight distribution" AND "tensile"
```

---

## 7. Tech Stack

| Layer | Tool | Why |
|---|---|---|
| PDF parsing | PyMuPDF (fitz), pdfplumber | Best combo for text + tables |
| Embedding | sentence-transformers (all-MiniLM-L6-v2) | Fast, good quality, free |
| Vector store | FAISS | Simple, local, no server needed |
| LLM | Llama3-8B or Gemma2-9B (4-bit quantized) | Proven on this exact task by Dr. Joshi's group |
| Database | SQLite (dev), PostgreSQL (prod) | SQLite needs zero setup |
| Visualization | Matplotlib + Plotly | Matplotlib for static, Plotly for interactive |
| Validation | Custom bounds checker | Simple but critical |
| Paper fetching | Semantic Scholar API + requests | Free, no auth needed |

### Install

```bash
pip install pymupdf pdfplumber sentence-transformers faiss-cpu \
            transformers bitsandbytes accelerate torch \
            matplotlib plotly pandas requests sqlite3
```

---

## 8. Weekly Plan

| Week | Goal | Deliverable |
|---|---|---|
| 1 | Setup + paper collection pipeline | Script to fetch + download PDFs from Semantic Scholar |
| 2 | PDF parsing + chunking | Clean text + table extraction from 20 test papers |
| 3 | RAG pipeline + LLM extraction | Working extraction on test set, JSON output |
| 4 | Validation layer + DB design | Schema live, insertion working, flags on bad data |
| 5 | Full pipeline end-to-end | 100+ papers processed into DB |
| 6 | MWD reconstruction + EDA | Curves plotted, comparison across 3 polymer types |
| 7 | Scale + clean up | 300+ papers, clean codebase, accuracy benchmarked |
| 8 | Final report + handover | Documentation, final DB, summary report |

---

## 9. Weekly Report Template

```
## Week N Report — [Date]
**Papers processed this week:** X (total: Y)
**New entries in DB:** X polymer samples

### What I did
- 

### Results / findings
- 

### Issues / blockers
- 

### Plan for next week
- 

### Accuracy check (sample of 10 manual verifications)
| Field | Correct | Wrong | Missing |
|---|---|---|---|
| Mn | | | |
| Mw | | | |
| Dispersity | | | |
| Processing | | | |
```

---

## 10. App Architecture — FastAPI + React

The project ships as two separate services: a Python backend (pipeline + API) and a React frontend (dashboard).

### Project Structure

```
ncl-polymer/
├── backend/
│   ├── main.py              # FastAPI app + API routes
│   ├── pipeline/
│   │   ├── fetch.py         # Paper fetching (Semantic Scholar etc.)
│   │   ├── parse.py         # PDF parsing (PyMuPDF + pdfplumber)
│   │   ├── extract.py       # RAG + LLM extraction
│   │   └── validate.py      # Bounds checking + flag generation
│   ├── db/
│   │   ├── schema.sql       # Table definitions
│   │   └── crud.py          # Insert / query helpers
│   └── models/
│       └── mwd.py           # Log-normal MWD reconstruction
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PolymerTable.jsx    # Searchable / filterable data table
│   │   │   ├── MWDPlot.jsx         # Plotly MWD curve viewer
│   │   │   └── SearchFilter.jsx    # Filter by polymer type, Mn range etc.
│   │   └── App.jsx
│   └── package.json
└── NCL_Polymer_Project.md
```

### Backend — FastAPI

```python
# backend/main.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from db.crud import get_samples, get_mwd_curve
from models.mwd import reconstruct_mwd
import sqlite3

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "polymer.db"

@app.get("/samples")
def list_samples(
    polymer_type: str = Query(None),
    mn_min: float = Query(None),
    mn_max: float = Query(None),
    limit: int = 100
):
    """Return filtered polymer samples from DB."""
    conn = sqlite3.connect(DB_PATH)
    samples = get_samples(conn, polymer_type, mn_min, mn_max, limit)
    conn.close()
    return {"samples": samples}

@app.get("/mwd/{sample_id}")
def get_mwd(sample_id: int):
    """Return reconstructed MWD curve points for a sample."""
    conn = sqlite3.connect(DB_PATH)
    sample = get_mwd_curve(conn, sample_id)
    conn.close()
    if not sample:
        return {"error": "Sample not found"}
    mw, intensity = reconstruct_mwd(sample["mn"], sample["mw"])
    return {
        "sample_id": sample_id,
        "polymer_type": sample["polymer_type"],
        "mn": sample["mn"],
        "mw": sample["mw"],
        "dispersity": sample["dispersity"],
        "mw": mw.tolist(),
        "intensity": intensity.tolist()
    }

@app.get("/stats")
def get_stats():
    """Summary stats for the dashboard header."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM papers")
    paper_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM polymer_samples")
    sample_count = cur.fetchone()[0]
    cur.execute("SELECT polymer_type, COUNT(*) FROM polymer_samples GROUP BY polymer_type")
    by_type = dict(cur.fetchall())
    conn.close()
    return {"papers": paper_count, "samples": sample_count, "by_type": by_type}
```

### Frontend — Key Components

```jsx
// frontend/src/components/MWDPlot.jsx
import Plot from "react-plotly.js";
import { useEffect, useState } from "react";

export default function MWDPlot({ sampleIds }) {
  const [traces, setTraces] = useState([]);

  useEffect(() => {
    const fetchCurves = async () => {
      const results = await Promise.all(
        sampleIds.map(id => fetch(`/mwd/${id}`).then(r => r.json()))
      );
      setTraces(results.map(r => ({
        x: r.mw,
        y: r.intensity,
        type: "scatter",
        mode: "lines",
        name: `${r.polymer_type} — Đ=${r.dispersity?.toFixed(2)}`,
      })));
    };
    if (sampleIds.length > 0) fetchCurves();
  }, [sampleIds]);

  return (
    <Plot
      data={traces}
      layout={{
        title: "Molecular Weight Distribution",
        xaxis: { title: "Molecular Weight (g/mol)", type: "log" },
        yaxis: { title: "Normalized Intensity dW/d(logM)" },
        legend: { orientation: "h" },
      }}
      style={{ width: "100%", height: "500px" }}
    />
  );
}
```

```jsx
// frontend/src/components/PolymerTable.jsx
import { useState } from "react";

export default function PolymerTable({ samples, onSelect }) {
  const [selected, setSelected] = useState([]);

  const toggle = (id) => {
    const next = selected.includes(id)
      ? selected.filter(s => s !== id)
      : [...selected, id];
    setSelected(next);
    onSelect(next);
  };

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          {["", "Type", "Mn", "Mw", "Đ", "Processing", "Tensile (MPa)", "Paper"].map(h => (
            <th key={h} style={{ borderBottom: "2px solid #ccc", padding: "8px", textAlign: "left" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {samples.map(s => (
          <tr key={s.id} style={{ background: selected.includes(s.id) ? "#e8f4fd" : "white" }}>
            <td><input type="checkbox" checked={selected.includes(s.id)} onChange={() => toggle(s.id)} /></td>
            <td style={{ padding: "6px" }}>{s.polymer_type}</td>
            <td>{s.mn?.toLocaleString()}</td>
            <td>{s.mw?.toLocaleString()}</td>
            <td>{s.dispersity?.toFixed(2)}</td>
            <td>{s.processing_method || "—"}</td>
            <td>{s.tensile_strength || "—"}</td>
            <td><a href={`https://doi.org/${s.doi}`} target="_blank" rel="noreferrer">DOI</a></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Running Locally

```bash
# Backend
cd backend
pip install fastapi uvicorn sqlite3 pymupdf pdfplumber \
            sentence-transformers faiss-cpu transformers torch
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm start        # runs on localhost:3000
```

### Why This Stack Over Alternatives

| Option | Why not |
|---|---|
| Streamlit | Reruns entire script on every interaction — too slow for DB queries + plots |
| Gradio | Better than Streamlit but still limited state management |
| Jupyter | Not presentable as a shareable tool |
| Windows binary | Overkill, no benefit for a lab setting |
| **FastAPI + React** ✅ | Full control, fast, React handles state properly, Plotly native in React |

---

## 11. Questions Still Open

- [ ] Does Dr. Joshi have a seed set of papers to start with?
- [ ] What format does she want the final database in — SQLite file, Excel, or hosted?
- [ ] Should dispersity be extracted from text or always computed as Mw/Mn?
- [ ] Are there specific journals to prioritize?
- [ ] Is there a target number of papers / entries?
- [ ] Full automation of curve extraction from figures — stretch goal or required?

---

*Last updated: June 2026*
