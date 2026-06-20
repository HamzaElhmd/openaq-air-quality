from pydantic import BaseModel, Field, validator, ConfigDict
from typing import Optional, List
from datetime import datetime
import pickle
import joblib
from pathlib import Path
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# feature schemas for prediction input
class TemporalFeatures(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")
    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2000, le=2100, description="Year")


class SensorMetrics(BaseModel):
    value_avg: float = Field(..., description="Average PM2.5 value")
    min: float = Field(..., description="Minimum PM2.5 value")
    max: float = Field(..., description="Maximum PM2.5 value")
    q25: float = Field(..., description="25th percentile")
    median: float = Field(..., description="Median PM2.5 value")
    q75: float = Field(..., description="75th percentile")
    aqi: float = Field(..., description="Current Air Quality Index")
    parameter: str = Field(..., description="Parameter name (e.g., 'pm25')")


class LocationInfo(BaseModel):
    location_name: str = Field(..., description="Sensor location name")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (informational)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude (informational)")
    actual_lag_hours: float = Field(..., ge=-180, le=180, description="Actual lag in hours between measurement and prediction time")

# Predict One 
class PredictOneRequest(BaseModel):
    location: LocationInfo
    sensor_metrics: SensorMetrics
    temporal: TemporalFeatures
    source: Optional[str] = Field(default=None, description="Source identifier for the prediction( webapp, scheduled predictions, etc.)")

class PredictOneResponse(BaseModel):
    prediction: float = Field(..., description="Predicted aiq_after_12h value")

class PredictionResult(BaseModel):
    index: int = Field(default = None, description="Row index from input")
    prediction: float = Field(..., description="Predicted aiq_after_12h value")

# Predict Many 
class PredictManyResponse(BaseModel):
    predictions: List[PredictionResult]
    total_predictions: int = Field(default = None, description="Total number of predictions made")
    
# Get Past Prediction
class PastPredictionRequest(BaseModel):
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    source: Optional[str] = Field(..., description="Source identifier (webapp, scheduled predictions, etc.)")
    
    @validator('start_date', 'end_date')
    def validate_date_format(cls, v):
        # Ensure dates are in YYYY-MM-DD format
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format (YYYY-MM-DD)")
        return v


class HistoricalPrediction(BaseModel):
    id: Optional[int] = Field(..., description="Prediction record ID")
    #feature fields
    localisation_feats : LocationInfo = Field(..., description="Input features for the prediction")
    sensor_feats : SensorMetrics = Field(..., description="Input features for the prediction")
    temporal_feats : TemporalFeatures = Field(..., description="Input features for the prediction")
    #source webapp, scheduled predictions, etc.
    source: str = Field(..., description="Source identifier (webapp, scheduled predictions, etc.)")
    #db query fields
    start_date: str = Field(..., description="Start date of prediction range in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date of prediction range in YYYY-MM-DD format")
    #prediction result and metadata
    predicted_value: Optional[float] = Field(..., description="Predicted PM2.5 value in µg/m³")
    created_at: Optional[datetime] = Field(..., description="Timestamp when the prediction was created")

class PastPredictionsResponse(BaseModel):
    predictions: List[HistoricalPrediction]
    count: int = Field(..., description="Number of predictions returned")


# Health DB Check
class DatabaseHealthCheck(BaseModel):
    status: str = Field(..., description="Overall status: ok or error")
    database: str = Field(..., description="Database connection status")
    db_response: Optional[int] = Field(default=None)
    db_version: Optional[str] = None
    timestamp: datetime

# Health Check Response
class HealthCheckResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    #    General health check response
    status: str = Field(..., description="Overall API status: ok or error")
    timestamp: datetime
    model_loaded: bool = Field(default=False, description="Is ML model available")
    version: Optional[str] = None


# Errors responses 
class ErrorDetail(BaseModel):
    error: str = Field(..., description="Error type or message")
    detail: Optional[str] = Field(default=None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ValidationErrorResponse(BaseModel):
    detail: List[dict] = Field(..., description="List of validation errors")

# Health Check for Docker Container Readiness

class ComponentStatus(BaseModel):
    """Status of individual service components"""
    name: str = Field(..., description="Component name (e.g., 'database', 'model')")
    ready: bool = Field(..., description="Is the component ready?")
    error: Optional[str] = Field(default=None, description="Error message if not ready")

class ReadinessProbeResponse(BaseModel):
    """Response for Docker health check / readiness probe"""
    status: str = Field(..., description="Overall status: 'ready' or 'not_ready'")
    ready: bool = Field(..., description="True if all components are ready")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: List[ComponentStatus] = Field(..., description="Status of each component")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ready",
                "ready": True,
                "timestamp": "2026-03-26T10:30:00.123456",
                "components": [
                    {"name": "database", "ready": True, "error": None},
                    {"name": "model", "ready": True, "error": None}
                ]
            }
        }
    )

class LivenessProbeResponse(BaseModel):
    """Response for liveness probe (is app running?)"""
    status: str = Field(default="alive", description="App is running")
    uptime_seconds: Optional[float] = Field(default=None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Singleton model manager to load and cache the model
class MLModelManager:
    _instance = None
    _model = None
    _model_version = None
    _model_path = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def load_model(cls, model_path: Optional[str] = None, version: Optional[str] = None):
        instance = cls()
        
        if model_path is None:
            logger.warning("No model file found")
            return None
        
        try:
            model_path = Path(model_path)
            
            if not model_path.exists():
                logger.error(f"Model file not found: {model_path}")
                return None
            
            try:
                instance._model = joblib.load(str(model_path))
                logger.info(f"Model loaded with joblib from {model_path}")
            except Exception:
                with open(model_path, 'rb') as f:
                    instance._model = pickle.load(f)
                logger.info(f"Model loaded with pickle from {model_path}")
            
            instance._model_path = str(model_path)
            instance._model_version = version or "loaded"
            return instance._model
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            instance._model = None
            return None
    
    @classmethod
    def get_model(cls):
        instance = cls()
        return instance._model
    
    @classmethod
    def is_ready(cls) -> bool:
        instance = cls()
        return instance._model is not None




# DB dependencies helper
def get_model() -> Optional[object]:
    return MLModelManager.get_model()


def model_required():
    model = MLModelManager.get_model()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="ML model not loaded. Please check server logs and restart.",
            headers={"Retry-After": "60"}
        )
    return model
