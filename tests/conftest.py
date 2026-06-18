import os
import pytest
import sys
from unittest.mock import MagicMock

# Mock fitz so we don't have to wait 20 minutes for PyMuPDF to compile from source
sys.modules['fitz'] = MagicMock()

# Add backend directory to sys.path so tests can import the pipeline modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

@pytest.fixture
def tmp_pdf_dir(tmp_path):
    """Returns a temporary directory for saving mock PDFs."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    yield str(pdf_dir)

@pytest.fixture
def mock_db_connection():
    """Provides a mocked PostgreSQL connection to prevent tests from hitting live DB."""
    conn = MagicMock()
    # Mock context manager for cursor
    cursor_mock = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor_mock
    return conn
