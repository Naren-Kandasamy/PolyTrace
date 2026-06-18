# Directive 01: Paper Fetching Pipeline

**Goal**: Establish a deterministic pipeline to query, fetch, and store open-access PDFs containing experimental hydrogen storage data (e.g. MHPCTpro, metal hydrides).

**Inputs**: 
- Target search queries for Hydrogen Storage.
- ChemRxiv API, Semantic Scholar API.
- Unpaywall API for Open-Access filtering of 10k+ lists.

**Outputs**:
- Local PDF files stored in `pdfs/`.
- PostgreSQL Document Store populated with metadata (DOI, title, authors, year, journal, URLs, and local PDF path).

**Execution Script**: `backend/pipeline/fetch.py` & `backend/pipeline/fetch_crossref.py`

**Edge Cases & Rules**:
- **Authentication**: Semantic Scholar's unauthenticated API heavily restricts traffic and often returns HTTP 429 errors. You must provide an API key in the `.env` file (`SEMANTIC_SCHOLAR_API_KEY=your_key_here`) for this script to run reliably.
- **Rate Limits**: The script includes an exponential backoff loop to gracefully handle rate limit hits, but an API key is still practically required.
- **Language Verification**: We only want English papers. Because many foreign journals mandate an English abstract on Page 1, language detection (e.g., using `langdetect`) must be performed on the **middle of the document** (e.g., Page 3) to ensure the actual body text is English.
- **Missing Data**: Papers without an explicit `openAccessPdf` link must be skipped.
- **Duplicate Prevention**: The database must enforce unique DOIs. Check the DB before downloading a PDF to save bandwidth.
- **PDF Download Failures**: Direct PDF URLs occasionally return 403s or require browser-like User-Agents. Handle exceptions gracefully without crashing the script.

**To Run**:
`python backend/pipeline/fetch.py`
