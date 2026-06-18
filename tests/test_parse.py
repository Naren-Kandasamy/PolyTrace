import sys
from unittest.mock import MagicMock, patch
import pandas as pd

# Mock pdfplumber to prevent requiring a real PDF file
sys.modules['pdfplumber'] = MagicMock()

from pipeline.parse import extract_text_by_section, extract_images_from_pdf, extract_tables

def test_extract_text_by_section():
    # Since fitz is mocked in conftest.py, we set up its return values
    import fitz
    
    mock_doc = MagicMock()
    mock_page = MagicMock()
    
    mock_block = {
        "type": 0,
        "lines": [
            {
                "spans": [{"text": "Introduction", "size": 14}]
            },
            {
                "spans": [{"text": "This is the body text.", "size": 10}]
            }
        ]
    }
    
    mock_page.get_text.return_value = {"blocks": [mock_block]}
    mock_doc.__iter__.return_value = [mock_page]
    fitz.open.return_value = mock_doc
    
    result = extract_text_by_section("dummy.pdf")
    
    assert "introduction" in result
    assert "This is the body text." in result["introduction"]

def test_extract_tables():
    import pdfplumber
    
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    
    # Simulate extract_tables returning one table (list of lists)
    mock_page.extract_tables.return_value = [
        [["Header1", "Header2"], ["Val1", "Val2"]]
    ]
    mock_pdf.pages = [mock_page]
    
    # Mock context manager for pdfplumber.open()
    pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    
    tables = extract_tables("dummy.pdf")
    
    assert len(tables) == 1
    assert isinstance(tables[0], pd.DataFrame)
    assert list(tables[0].columns) == ["Header1", "Header2"]
    assert tables[0].iloc[0]["Header1"] == "Val1"
