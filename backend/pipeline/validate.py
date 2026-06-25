from pydantic import BaseModel, Field, field_validator, ValidationError
from typing import List, Optional

# --- Text Extraction Schema & Bounds ---
class TemperatureRange(BaseModel):
    min: float
    max: float

    @field_validator('max')
    def max_must_be_greater_than_min(cls, v, info):
        if 'min' in info.data and v < info.data['min']:
            raise ValueError('Maximum temperature cannot be less than minimum temperature')
        return v

class MaterialProperties(BaseModel):
    material_name: Optional[str] = "Unknown"
    paper_aim: Optional[str] = None
    paper_motive: Optional[str] = None
    paper_type: Optional[str] = "UNKNOWN"
    base_alloy: Optional[str] = None
    substitutions: Optional[List[str]] = []
    absorption_temperature_c: Optional[TemperatureRange] = None
    desorption_temperature_c: Optional[TemperatureRange] = None
    enthalpy_of_formation_kj_mol: Optional[float] = None
    
    # Hydrogen storage capacity rarely exceeds 20 wt% (even theoretically for MgH2 it's ~7.6%)
    # If the LLM hallucinates 50%, we want to catch it.
    max_hydrogen_capacity_wt_percent: Optional[float] = Field(None, ge=0.0, le=20.0)
    target_application: Optional[str] = None

# --- Image Classification Schema & Bounds ---
class FigureMetadata(BaseModel):
    figure_type: str = "UNKNOWN"
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    temperature_series_c: Optional[List[float]] = []

def validate_material_json(raw_json: dict) -> dict:
    """
    Validates LLM-extracted material properties against physical boundaries.
    Returns the cleaned dictionary if valid, or logs error and returns {} if invalid.
    """
    try:
        validated_model = MaterialProperties(**raw_json)
        return validated_model.model_dump(exclude_none=True)
    except ValidationError as e:
        print(f"      [!] Pydantic Validation Error (Text): LLM Hallucinated invalid data bounds.")
        print(f"          Details: {e.errors()[0]['msg']}")
        return {}

def validate_figure_json(raw_json: dict) -> dict:
    """
    Validates VLM-extracted figure metadata against expected schemas.
    Returns the cleaned dictionary if valid, or logs error and returns {} if invalid.
    """
    try:
        validated_model = FigureMetadata(**raw_json)
        return validated_model.model_dump(exclude_none=True)
    except ValidationError as e:
        print(f"      [!] Pydantic Validation Error (Image): VLM Hallucinated invalid figure schema.")
        print(f"          Details: {e.errors()[0]['msg']}")
        return {}

if __name__ == "__main__":
    # Quick sanity check
    test_json = {"material_name": "MgH2", "max_hydrogen_capacity_wt_percent": 25.0} # Invalid (25 > 20)
    print("Testing Boundary Validation...")
    res = validate_material_json(test_json)
    if not res:
        print("[✓] Correctly caught the hallucination.")
