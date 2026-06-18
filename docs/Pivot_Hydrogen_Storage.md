# Pivot Strategy: Hydrogen Storage & Generalized AI Platform
**Date:** June 12, 2026
**Status:** ACTIVE PIVOT

## 1. The Pivot
Based on the Week 1 review with Dr. Kavita Joshi, the focus of the project is shifting immediately from PE/PP Polymers to **Hydrogen Storage** materials (e.g., MHPCTpro). Furthermore, the architecture is expanding from a rigid, hardcoded script into a generalized, multimodal AI platform for materials science.

## 2. Architectural Changes Required

### 2.1 Database & Schema
*   **Old:** Rigid SQLite relational tables (`polymer_samples` with hardcoded columns for `mn`, `mw`, etc.).
*   **New:** Flexible Document Store (PostgreSQL with JSONB or MongoDB). The schema must accept dynamic, prompt-driven key-value pairs to handle varied materials science data.

### 2.2 Sourcing & Fetching
*   **Old:** Semantic Scholar only.
*   **New:** Multi-source integration (ChemRxiv, Semantic Scholar).
*   **New:** Programmatic filtering of 10,000+ paper lists using **Unpaywall / Crossref APIs** to separate "Free" from "Paid" papers before attempting downloads. Web scraping Google Scholar/ResearchGate is strictly avoided to prevent IP bans.

### 2.3 Extraction Capabilities
*   **Old:** Text-only PDF extraction via PyMuPDF + standard LLMs.
*   **New:** Multimodal extraction. 
    *   **Text:** Dynamic prompt-driven extraction of synthesis protocols, problems, and authors.
    *   **Images:** Integration of Open-Source Vision-Language Models (e.g., Llama 3.2-Vision, Qwen-VL) to classify plots (e.g., PCT curves, XRD patterns), read axes, and extract high-level maximums/minimums.

### 2.4 Open-Source Requirement
*   **Strict Constraint:** The entire pipeline must exclusively use open-source models (Llama 3, Gemma 2, Qwen-VL) and frameworks (Transformers, vLLM/Ollama). No proprietary APIs (OpenAI, Google) for extraction.

## 3. Scoping & Timeline (1-3 Months MVP)
To ensure delivery alongside college commitments:
*   **Phase 1 (Immediate):** Source Feasibility (ChemRxiv/Unpaywall) and Text Extraction (Dynamic JSON schema).
*   **Phase 2:** Vision-Language Model integration for high-level figure classification.
*   **Stretch Goals (R&D):** Full pixel-by-pixel curve tracing and automated active learning/model retraining (as referenced in ChemRxiv 10002052).
