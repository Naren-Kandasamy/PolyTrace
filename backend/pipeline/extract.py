import os
import sys
import json
import base64
import requests

# Ensure we can import from backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from pipeline.parse import extract_text_by_section, extract_images_from_pdf, cleanup_images, extract_tables
from pipeline.rag import retrieve_relevant_chunks
from pipeline.validate import validate_material_json, validate_figure_json
from db.crud import get_db_connection, insert_material_extraction, insert_figure

# We hardcode the local Ollama endpoint as per the Open-Source constraints
OLLAMA_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:3b" # For Multimodal plots (Smarter than Moondream)
TEXT_MODEL = "llama3.2:1b"            # For standard text blocks

def classify_paper_type(text_chunk: str) -> str:
    """Pass A: Classify if the paper is HIST_THOR or PCT."""
    prompt = f"""
    Analyze the text and determine the primary focus of the paper.
    If it focuses on measuring enthalpy, hydrogen storage tanks, or general capacity, return "HIST_THOR".
    If it focuses heavily on plotting Pressure-Composition-Temperature isotherms or equilibrium curves, return "PCT".
    Return ONLY the raw string "HIST_THOR" or "PCT". Do not include quotes or any other text.
    
    Text:
    {text_chunk[:1000]}
    """
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": TEXT_MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=180)
        if response.status_code == 200:
            res = response.json().get("response", "").strip().upper()
            return "PCT" if "PCT" in res else "HIST_THOR"
    except Exception as e:
        print(f"  [!] LLM Classification Error: {e}")
    return "UNKNOWN"

def call_vlm_for_text(text_chunk: str, paper_type: str) -> dict:
    """Pass B: Send text to the local LLM to extract JSON properties using a dynamic schema."""
    
    base_schema = """
      "material_name": "string",
      "paper_aim": "string (the primary goal of the research)",
      "paper_motive": "string (why they conducted this specific research)",
      "base_alloy": "string",
      "substitutions": ["string"],
      "absorption_temperature_c": {"min": 0.0, "max": 0.0},
      "target_application": "string"
    """
    
    if paper_type == "HIST_THOR":
        schema = f"""{{
        {base_schema},
        "max_hydrogen_capacity_wt_percent": 0.0,
        "enthalpy_of_formation_kj_mol": 0.0
        }}"""
    else: # PCT
        schema = f"""{{
        {base_schema},
        "desorption_temperature_c": {{"min": 0.0, "max": 0.0}}
        }}"""
        
    prompt = f"""
    You are a materials science expert. Extract the following properties from the text into strict JSON format.
    Schema:
    {schema}
    
    Text:
    {text_chunk[:2000]}  # Truncated to prevent context overflow
    
    Return ONLY valid JSON.
    """
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": TEXT_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }, timeout=180)
        
        if response.status_code == 200:
            return json.loads(response.json().get("response", "{}"))
        else:
            raise RuntimeError(f"Ollama API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"  [!] LLM Text Extraction Error: {e}")
        raise e
        
    return {}

def call_vlm_for_image(image_path: str) -> dict:
    """Send an image to the local Vision LLM to classify it and extract metadata."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
        
    prompt = """
    Analyze this scientific figure. If this image is NOT a data plot, or if it is just an equation, text, logo, or diagram, you MUST return "figure_type": "UNKNOWN".
    If and only if it is a specific plot, return the matching type.
    Schema:
    {
      "figure_type": "PCT_CURVE" | "XRD_PATTERN" | "SEM_IMAGE" | "UNKNOWN",
      "x_axis_label": "string",
      "y_axis_label": "string",
      "temperature_series_c": [0.0]
    }
    Return ONLY valid JSON. Default to UNKNOWN.
    """
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "format": "json"
        }, timeout=600)
        
        if response.status_code == 200:
            return json.loads(response.json().get("response", "{}"))
        else:
            raise RuntimeError(f"Ollama API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"  [!] VLM Image Extraction Error: {e}")
        raise e
        
    return {}

def prepare_paper_data(paper_id: int, pdf_path: str):
    """Phase 1: CPU-bound parsing of text, tables, and images."""
    print(f"  [+] Parsing PDF: {os.path.basename(pdf_path)}...")
    sections = extract_text_by_section(pdf_path)
    image_paths = extract_images_from_pdf(pdf_path, str(paper_id))
    tables = extract_tables(pdf_path)
    
    rag_query = "experimental results, maximum hydrogen storage capacity wt%, desorption temperature, material synthesis"
    core_text = retrieve_relevant_chunks(sections, rag_query, top_k=4)
    
    if tables:
        core_text += "\n\n### Extracted Tables Data:\n"
        # Only append top 2 tables to prevent massive prompt context bloat
        for i, df in enumerate(tables[:2]):
            core_text += f"\nTable {i+1}:\n" + df.to_markdown(index=False) + "\n"
            
    return core_text, image_paths

def run_text_extraction(paper_id: int, core_text: str, conn):
    """Phase 2: LLM Text Extraction (Two-Pass Router)."""
    if not core_text.strip():
        return
    print(f"  [?] Running Two-Pass LLM Extraction for Paper {paper_id}...")
    
    # Pass A: Classify
    paper_type = classify_paper_type(core_text)
    print(f"      [-] Classified Paper Type as: {paper_type}")
    
    # Pass B: Extract
    raw_properties = call_vlm_for_text(core_text, paper_type)
    raw_properties["paper_type"] = paper_type # Inject classification
    
    properties = validate_material_json(raw_properties)
    if properties:
        mat_name = properties.get('material_name', 'Unknown')
        print(f"      [✓] Validated & Extracted Material: {mat_name}")
        insert_material_extraction(conn, paper_id, mat_name, properties)

def run_vision_extraction(paper_id: int, image_paths: list, conn):
    """Phase 3: VLM Image Classification."""
    if not image_paths:
        return
    # SAFETY CAP: Only evaluate a maximum of 3 images per paper to prevent 10-minute hangs on scanned PDFs
    images_to_process = image_paths[:3]
    
    import time
    print(f"  [?] Running VLM Image Classification for Paper {paper_id} (Evaluating {len(images_to_process)} out of {len(image_paths)} total images)...")
    for img_path in images_to_process:
        img_start_time = time.time()
        raw_vlm_meta = call_vlm_for_image(img_path)
        img_end_time = time.time()
        
        img_duration = img_end_time - img_start_time
        print(f"      [*] Vision Inference Time: {img_duration:.2f} seconds")
        
        vlm_meta = validate_figure_json(raw_vlm_meta)
        if vlm_meta:
            fig_type = vlm_meta.get('figure_type', 'UNKNOWN')
            if fig_type != 'UNKNOWN':
                print(f"      [✓] Validated {fig_type} plot from {os.path.basename(img_path)}!")
                insert_figure(conn, paper_id, fig_type, img_path, vlm_meta)
    
    # Stateless Cleanup (Clean up all .tmp images to save disk space)
    cleanup_images(image_paths)

if __name__ == "__main__":
    print("Multimodal Extraction Pipeline Scaffolding Ready.")
