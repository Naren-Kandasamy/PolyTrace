import pytest
import responses
from unittest.mock import patch, MagicMock
from pipeline import fetch
import psycopg2

@pytest.fixture(autouse=True)
def override_paths(tmp_pdf_dir):
    """Automatically override the paths in the fetch module for all tests."""
    fetch.PDF_DIR = tmp_pdf_dir

@responses.activate
def test_search_semantic_scholar_success():
    """Test that the Semantic Scholar search correctly parses a valid API response."""
    responses.add(
        responses.GET,
        'https://api.semanticscholar.org/graph/v1/paper/search',
        json={'data': [{'title': 'Mock Paper', 'openAccessPdf': {'url': 'http://mock.pdf'}}]},
        status=200
    )
    result = fetch.search_semantic_scholar("Hydrogen storage test")
    assert len(result) == 1
    assert result[0]['title'] == 'Mock Paper'

@responses.activate
def test_search_semantic_scholar_rate_limit(capsys):
    """Test that the script handles HTTP 429 correctly without crashing."""
    responses.add(
        responses.GET,
        'https://api.semanticscholar.org/graph/v1/paper/search',
        status=429
    )
    
    # Patch time.sleep so we don't actually wait 5+ seconds during the test
    with patch('pipeline.fetch.time.sleep', return_value=None):
        result = fetch.search_semantic_scholar("test query", retries=2)
    
    # Assert it degrades gracefully and returns an empty list
    assert result == []
    
    # Check that the 429 warning was printed
    captured = capsys.readouterr()
    assert "Rate limited (429)" in captured.out

def test_is_english_paper_success():
    """Test language detection correctly identifies English text."""
    mock_page = MagicMock()
    mock_page.get_text.return_value = "This is a rigorous experimental study on the hydrogen storage capacity of MgH2."
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 10
    mock_doc.__getitem__.return_value = mock_page
    
    with patch('pipeline.fetch.fitz.open', return_value=mock_doc):
        assert fetch.is_english_paper("dummy.pdf") is True

def test_is_english_paper_failure():
    """Test language detection correctly rejects non-English text."""
    mock_page = MagicMock()
    # Spanish text
    mock_page.get_text.return_value = "Este es un estudio riguroso sobre la capacidad de almacenamiento de hidrogeno."
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 10
    mock_doc.__getitem__.return_value = mock_page
    
    with patch('pipeline.fetch.fitz.open', return_value=mock_doc):
        assert fetch.is_english_paper("dummy.pdf") is False

def test_database_insertion_and_duplicate(mock_db_connection):
    """Test valid insertions and that duplicate DOIs raise an IntegrityError."""
    from db import crud
    
    # 1. Test valid insertion logic using the new Postgres CRUD methods
    try:
        crud.insert_paper(
            conn=mock_db_connection,
            doi="10.123/test",
            title="Test Paper",
            authors="Smith",
            journal="Journal",
            year=2026,
            url="url",
            pdf_path="path.pdf",
            is_open_access=True
        )
    except Exception as e:
        pytest.fail(f"Valid insertion failed: {e}")
        
    # 2. Test duplicate insertion correctly throws psycopg2.IntegrityError
    cursor_mock = mock_db_connection.cursor.return_value.__enter__.return_value
    cursor_mock.execute.side_effect = psycopg2.IntegrityError("duplicate key value violates unique constraint")
    
    with pytest.raises(psycopg2.IntegrityError):
        crud.insert_paper(
            conn=mock_db_connection,
            doi="10.123/test",
            title="Different Title",
            authors="Doe",
            journal="Journal 2",
            year=2026,
            url="url2",
            pdf_path="path2.pdf",
            is_open_access=True
        )
