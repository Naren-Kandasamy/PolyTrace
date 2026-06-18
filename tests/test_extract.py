import pytest
import responses
from pipeline.extract import call_vlm_for_text, call_vlm_for_image, OLLAMA_URL
from unittest.mock import patch, mock_open

@responses.activate
def test_call_vlm_for_text_success():
    """Test that text extraction correctly parses a valid JSON response from Ollama."""
    responses.add(
        responses.POST,
        OLLAMA_URL,
        json={"response": '{"material_name": "LaNi5", "max_hydrogen_capacity_wt_percent": 1.4}'},
        status=200
    )
    
    result = call_vlm_for_text("Thermodynamic analysis of LaNi5.")
    assert result.get("material_name") == "LaNi5"
    assert result.get("max_hydrogen_capacity_wt_percent") == 1.4

@responses.activate
def test_call_vlm_for_text_failure():
    """Test that a failed connection to Ollama degrades gracefully."""
    responses.add(
        responses.POST,
        OLLAMA_URL,
        status=500
    )
    result = call_vlm_for_text("Some text.")
    assert result == {}

@patch("builtins.open", new_callable=mock_open, read_data=b"fake_image_data")
@responses.activate
def test_call_vlm_for_image_success(mock_file):
    """Test that image classification correctly parses the JSON response."""
    responses.add(
        responses.POST,
        OLLAMA_URL,
        json={"response": '{"figure_type": "PCT_CURVE"}'},
        status=200
    )
    
    result = call_vlm_for_image("fake/path.png")
    assert result.get("figure_type") == "PCT_CURVE"
    
@patch("builtins.open", new_callable=mock_open, read_data=b"fake_image_data")
@responses.activate
def test_call_vlm_for_image_timeout(mock_file):
    """Test that a timeout from the VLM returns an empty dict."""
    import requests
    responses.add(
        responses.POST,
        OLLAMA_URL,
        body=requests.exceptions.Timeout()
    )
    
    result = call_vlm_for_image("fake/path.png")
    assert result == {}
