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
VISION_MODEL = "moondream" # For Multimodal plots
TEXT_MODEL = "llama3.2:1b"            # For standard text blocks

def call_vlm_for_text(text_chunk: str) -> dict:
    """Send text to the local LLM to extract JSON properties."""
    prompt = f"""
    You are a materials science expert. Extract the following properties from the text into strict JSON format.
    Schema:
    {{
      "material_name": "string",
      "base_alloy": "string",
      "substitutions": ["string"],
      "absorption_temperature_c": {{"min": 0.0, "max": 0.0}},
      "desorption_temperature_c": {{"min": 0.0, "max": 0.0}},
      "max_hydrogen_capacity_wt_percent": 0.0,
      "target_application": "string"
    }}
    
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
    You are a scientific image classifier. Analyze this plot/image and return strict JSON.
    Schema:
    {
      "figure_type": "PCT_CURVE" | "XRD_PATTERN" | "SEM_IMAGE" | "UNKNOWN",
      "x_axis_label": "string",
      "y_axis_label": "string",
      "temperature_series_c": [0.0]
    }
    Return ONLY valid JSON. If it is not a scientific plot, return figure_type: "UNKNOWN".
    """
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "format": "json"
        }, timeout=180)
        
        if response.status_code == 200:
            return json.loads(response.json().get("response", "{}"))
        else:
            raise RuntimeError(f"Ollama API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"  [!] VLM Image Extraction Error: {e}")
        raise e
        
    return {}

def run_extraction_pipeline(paper_id: int, pdf_path: str, conn):
    """Orchestrates parsing and VLM extraction for a single paper."""
    print(f"\n[*] Processing Paper ID: {paper_id}")
    
    # 1. Visual Preprocessing (parse.py)
    print("  [+] Extracting text chunks...")
    sections = extract_text_by_section(pdf_path)
    
    print("  [+] Extracting images from PDF...")
    image_paths = extract_images_from_pdf(pdf_path, str(paper_id))
    print("  [+] Extracting tables...")
    tables = extract_tables(pdf_path)
    
    # 2. Text Extraction (RAG)
    print("  [+] Retrieving relevant chunks via FAISS RAG...")
    rag_query = "experimental results, maximum hydrogen storage capacity wt%, desorption temperature, material synthesis"
    core_text = retrieve_relevant_chunks(sections, rag_query, top_k=4)
    
    # Append formatted tables to text context
    if tables:
        core_text += "\n\n### Extracted Tables Data:\n"
        for i, df in enumerate(tables):
            core_text += f"\nTable {i+1}:\n" + df.to_markdown(index=False) + "\n"

    if core_text.strip():
        print("  [?] Running LLM Text Extraction...")
        raw_properties = call_vlm_for_text(core_text)
        
        # Pydantic Boundary Validation
        properties = validate_material_json(raw_properties)
        
        if properties:
            mat_name = properties.get('material_name', 'Unknown')
            print(f"      [✓] Validated & Extracted Material: {mat_name}")
            insert_material_extraction(conn, paper_id, mat_name, properties)
    
    # 3. Image Classification
    for img_path in image_paths:
        print(f"  [?] Running VLM Image Classification on {os.path.basename(img_path)}...")
        raw_vlm_meta = call_vlm_for_image(img_path)
        
        # Pydantic Boundary Validation
        vlm_meta = validate_figure_json(raw_vlm_meta)
        
        if vlm_meta:
            fig_type = vlm_meta.get('figure_type', 'UNKNOWN')
            if fig_type != 'UNKNOWN':
                print(f"      [✓] Validated {fig_type} plot!")
                insert_figure(conn, paper_id, fig_type, img_path, vlm_meta)
    
    # 4. Stateless Cleanup (Clean up all .tmp images to save disk space)
    cleanup_images(image_paths)

if __name__ == "__main__":
    print("Multimodal Extraction Pipeline Scaffolding Ready.")
