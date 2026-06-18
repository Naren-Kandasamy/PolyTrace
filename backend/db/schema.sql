-- backend/db/schema.sql

-- Enable UUID extension if we want UUIDs, but SERIAL is fine for now
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table for storing paper metadata (Sourcing from ChemRxiv, Crossref, etc.)
CREATE TABLE IF NOT EXISTS papers (
    id              SERIAL PRIMARY KEY,
    doi             TEXT UNIQUE,
    title           TEXT NOT NULL,
    authors         TEXT,
    journal         TEXT,
    year            INTEGER,
    url             TEXT,             -- Direct link to paper on journal site
    pdf_path        TEXT,             -- Local path to downloaded PDF
    is_open_access  BOOLEAN DEFAULT FALSE,
    added_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Flexible Document Store for Extracted Data (Hydrogen Storage, Synthesis, etc.)
CREATE TABLE IF NOT EXISTS material_extractions (
    id              SERIAL PRIMARY KEY,
    paper_id        INTEGER REFERENCES papers(id) ON DELETE CASCADE,
    material_name   TEXT,             -- e.g., "MHPCTpro", "MgH2"
    
    -- JSONB column allows for dynamic, prompt-driven properties from the LLM.
    -- Payload example: {"capacity_wt_percent": 7.6, "desorption_temp_c": 300, "synthesis": "ball milling"}
    properties      JSONB DEFAULT '{}'::jsonb,
    
    extracted_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table for tracking parsed multimodal figures (PCT Curves, XRD Patterns) VLM extraction
CREATE TABLE IF NOT EXISTS figures (
    id              SERIAL PRIMARY KEY,
    paper_id        INTEGER REFERENCES papers(id) ON DELETE CASCADE,
    figure_type     VARCHAR(50),      -- e.g., 'PCT_CURVE', 'XRD_PATTERN', 'OTHER'
    image_path      TEXT NOT NULL,    -- Local path to the cropped image/plot
    
    -- VLM extracted metadata (axes labels, maximums/minimums, curve classifications)
    vlm_metadata    JSONB DEFAULT '{}'::jsonb,
    
    extracted_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
