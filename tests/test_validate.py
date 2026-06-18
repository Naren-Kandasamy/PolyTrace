import pytest
from pipeline.validate import validate_material_json, validate_figure_json

def test_validate_material_json_success():
    """Test that valid metal hydride data passes Pydantic boundaries."""
    valid_data = {
        "material_name": "LaNi5",
        "substitutions": ["Al"],
        "max_hydrogen_capacity_wt_percent": 1.5,
        "absorption_temperature_c": {"min": 20.0, "max": 40.0}
    }
    result = validate_material_json(valid_data)
    assert result["material_name"] == "LaNi5"
    assert result["max_hydrogen_capacity_wt_percent"] == 1.5

def test_validate_material_json_hallucination_capacity():
    """Test that a hallucinated capacity over 20 wt% fails validation."""
    invalid_data = {
        "material_name": "MagicAlloy",
        "max_hydrogen_capacity_wt_percent": 25.0
    }
    result = validate_material_json(invalid_data)
    assert result == {} # Returns empty dict on failure

def test_validate_material_json_hallucination_temperature():
    """Test that a physical impossibility (min temp > max temp) fails validation."""
    invalid_data = {
        "material_name": "MgH2",
        "absorption_temperature_c": {"min": 100.0, "max": 50.0}
    }
    result = validate_material_json(invalid_data)
    assert result == {}

def test_validate_figure_json_success():
    """Test that a valid figure classification passes validation."""
    valid_data = {
        "figure_type": "PCT_CURVE",
        "x_axis_label": "Capacity",
        "y_axis_label": "Pressure"
    }
    result = validate_figure_json(valid_data)
    assert result["figure_type"] == "PCT_CURVE"

def test_validate_figure_json_invalid_type():
    """Test that an unknown figure type fails validation."""
    invalid_data = {
        "figure_type": "BAR_CHART", # Not in the allowed regex pattern
        "x_axis_label": "Capacity",
        "y_axis_label": "Pressure"
    }
    result = validate_figure_json(invalid_data)
    assert result == {}
