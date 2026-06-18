# Evaluation Report: PolyTrace Week 2 PDF Report

An analysis of `docs/PolyTrace_Week2_Report.pdf` reveals critical technical discrepancies, visual formatting issues, and compliance gaps with the project template.

---

## 1. Summary of Findings

> [!CAUTION]
> **Critical Integrity Issue: Silent Extraction Failures**
> The PDF report claims **100% Extraction Success** and **Zero Hallucination Crashes**. However, checking the PostgreSQL database reveals that the extraction pipeline actually failed silently for all papers.
> * The local Ollama instance has **no models loaded** (`{"models": []}`). Both `llama3` and `llama3.2-vision` calls failed with `404 Model Not Found`.
> * The extraction script caught these errors and returned `{}`.
> * The validation script fell back to default schemas, resulting in **dummy `"Unknown"` materials** and **0 figure records** stored in the database.

---

## 2. Detailed Mismatch Table

The table below outlines the discrepancies found between the PDF, the source Markdown file (`docs/Week2_Meeting_Report.md`), and the database:

| Feature/Section | PDF Report (`PolyTrace_Week2_Report.pdf`) | Markdown Source (`Week2_Meeting_Report.md`) | Database State (`materials_ai` DB) | Status / Discrepancy |
| :--- | :--- | :--- | :--- | :--- |
| **Material Extractions** | Claims successful numeric material property extraction. | Claims successful numeric material property extraction. | 6 records, all named `"Unknown"` with no properties. | **Critical Failure**: Silent pipeline failure masked by fallback values. |
| **Figure Extractions** | Claims successful Vision VLM plot classification. | Claims successful Vision VLM plot classification. | 0 records in `figures` table. | **Critical Failure**: 0 plots saved; VLM image path was deleted in cleanup. |
| **Q1 (Dashboard Priorities)** | Missing the "Why" section explaining visualization choices. | Contains: `*Why:* We can prioritize building specific views...` | N/A | **Sync Mismatch**: Text is missing in the PDF. |
| **Q2 (Human-in-the-Loop)** | Contains "Why" section explaining gating vs. feed options. | Missing the "Why" section entirely. | N/A | **Sync Mismatch**: Text is missing in the Markdown source. |
| **6.2 & 6.3 (DB Schema & Glossary)** | Included (Pages 3-4). | Completely missing. | N/A | **Sync Mismatch**: Markdown file is truncated. |
| **Accuracy Check Table** | Completely missing. | Completely missing. | N/A | **Template Non-compliance**: Required by project guidelines. |

---

## 3. Formatting & Visual Layout Issues

> [!NOTE]
> Visual layout check performed via PDF-to-image extraction and browser subagent rendering.

1. **Section Break Split**: Section 5 ("Important Questions & Discussion Points") is split awkwardly across page breaks. Q1 and Q2 render on Page 2, while Q3 is pushed to Page 3, breaking the flow of the questionnaire.
2. **ASCII Diagram Corruption**: In Section 6.1 (Updated Pipeline Architecture), the Unicode box-drawing characters (e.g., `┌`, `──`, `┐`, `│`, `└`) are stripped or failed to render in the PDF text layer, converting the structured diagram into unbordered text blocks.
3. **Glossary Alignment**: The glossary on Page 4 has inconsistent tab stops between terms and their definitions, making it hard to scan.

---

## 4. How to Fix the PDF and Pipeline

To make the report accurate and complete, follow these steps:

### Step 4.1: Pull Required Models in Ollama
Ensure the open-source models are available locally before running the extraction:
```bash
ollama pull llama3
ollama pull llama3.2-vision
```

### Step 4.2: Fix `extract.py` to Fail Loudly
Do not let Pydantic return a default `"Unknown"` schema when the model fails or returns empty results. Update `extract.py` to handle empty responses as failures.

### Step 4.3: Add the Mandatory Accuracy Check Table
Add the manual verification table to the report as required by the template in `docs/NCL_Hydrogen_Project.md`:
```markdown
### Accuracy check (6 manual verifications against gold-standard papers)
| Field | Correct | Wrong | Missing | Notes |
|---|---|---|---|---|
| Material name | 0 | 0 | 6 | All extracted as "Unknown" |
| Max capacity (wt%) | 0 | 0 | 6 | Not extracted |
| Desorption temp | 0 | 0 | 6 | Not extracted |
| Synthesis protocol | 0 | 0 | 6 | Not extracted |
```
