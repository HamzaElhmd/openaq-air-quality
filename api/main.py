import os
from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from sqlalchemy import text
import logging 
import asyncio
import pandas as pd 
from db import get_db, engine, DATABASE_URL
from sqlalchemy.orm import Session

from schemas import (
    PredictOneRequest,
    PredictOneResponse,
    PredictManyResponse,
    PredictionResult,
    ReadinessProbeResponse,
    ComponentStatus,
    PastPredictionsResponse,
    PastPredictionRequest,
    HistoricalPrediction,
    LocationInfo,
    SensorMetrics,
    TemporalFeatures,
    MLModelManager,
    get_model,
    model_required,
)

from models import Predictions

logger = logging.getLogger(__name__)

# loading the model at startup and making it available via dependency injection
async def lifespan(app: FastAPI):

    # Start model loading in background (don't block startup)
    async def load_model_background():
        logger.info("INFO: Starting background model loading...")
        
        model_manager = MLModelManager()
        model = model_manager.load_model(
            model_path="../model/model.pkl",
            version="v1.0.0"
        )
        
        logger.info(f"INFO: Model loading result: {model is not None}")
        
        if model is None:
            logger.warning("WARNING: No ML model loaded")
        else:
            logger.info("INFO: ML model loaded successfully")
    
    # Schedule background task at startup
    asyncio.create_task(load_model_background())
    logger.info("Lifespan startup complete, model loading in background")
    
    yield

    # Shutdown
    logger.info("INFO: Lifespan shutdown")
    


app = FastAPI(
    title="OpenAQ ML API",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ### Health check #### 
@app.get("/health/db")
def health_db(db=Depends(get_db)):
    # check if FastAPI can connect to PostgreSQL database.
    try:
        result = db.execute(text("SELECT 1 as connection_test, version() as db_version"))
        row = result.fetchone()
        
        return {
            "status": "Healthy",
            "database": "connected",
            "db_response": row.connection_test,
            "db_version": row.db_version,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "Unhealthy",
                "database": "disconnected",
                "error": str(e),
                "database_url": DATABASE_URL.replace("://", "://***:***@")
            }
        )
    
# Docker Readiness Probe (GET /health/ready) - checks if all components are ready
@app.get("/health/ready", response_model=ReadinessProbeResponse)
def health_ready(db: Session = Depends(get_db)):
    # Readiness check for Docker - verifies all components ready
    components = []
    all_ready = True
    
    # Check database
    try:
        db.execute(text("SELECT 1"))
        components.append(ComponentStatus(name="database", ready=True))
    except Exception as e:
        components.append(ComponentStatus(name="database", ready=False, error=str(e)))
        all_ready = False
    
    # Check model
    model_ready = MLModelManager.is_ready()
    components.append(ComponentStatus(
        name="model", 
        ready=model_ready,
        error=None if model_ready else "Model not loaded"
    ))
    
    response = ReadinessProbeResponse(
        status="ready" if all_ready else "not_ready",
        ready=all_ready,
        components=components
    )
    
    if not all_ready:
        raise HTTPException(
            status_code=503,
            detail=response.model_dump()
        )
    
    return response

# Past Predictions  (GET /api/past_predictions)

@app.get("/api/past_predictions", response_model=PastPredictionsResponse)
def past_predictions(
    payload: PastPredictionRequest = Depends(),
    db: Session = Depends(get_db),
)-> PastPredictionsResponse:
    try:
        # parse dates
        start_dt = datetime.fromisoformat(payload.start_date)
        end_dt = datetime.fromisoformat(payload.end_date)
        
        # build query with conditional source filtering
        query = db.query(Predictions).filter(
            Predictions.created_at >= start_dt,
            Predictions.created_at <= end_dt
        )
        
        # filter by source if it's not "all"
        if payload.source != "all":
            query = query.filter(Predictions.source == payload.source)
        
        predictions = query.order_by(Predictions.created_at.desc()).all()
        
        # convert to response format matching HistoricalPrediction schema
        prediction_list = []
        for pred in predictions:
            # reconstruct feature objects from stored data
            location_info = LocationInfo(
                location_name=pred.location_name or "",
                latitude=float(pred.latitude) if pred.latitude else 0.0,
                longitude=float(pred.longitude) if pred.longitude else 0.0,
                actual_lag_hours=float(pred.actual_lag_hours) if pred.actual_lag_hours else 0.0,
            )
            sensor_metrics = SensorMetrics(
                value_avg=float(pred.value_avg) if pred.value_avg else 0.0,
                min=float(pred.min) if pred.min else 0.0,
                max=float(pred.max) if pred.max else 0.0,
                q25=float(pred.q25) if pred.q25 else 0.0,
                median=float(pred.median) if pred.median else 0.0,
                q75=float(pred.q75) if pred.q75 else 0.0,
                aqi=float(pred.aqi) if pred.aqi else 0.0,
                parameter=pred.parameter_name or "",
            )
            temporal_features = TemporalFeatures(
                hour=pred.hour or 0,
                day_of_week=pred.day_of_week or 0,
                month=pred.month or 0,
                year=pred.year or 2026,
            )
            prediction_list.append(HistoricalPrediction(
                id=pred.prediction_id,
                localisation_feats=location_info,
                sensor_feats=sensor_metrics,
                temporal_feats=temporal_features,
                source=pred.source or "",
                start_date=payload.start_date,
                end_date=payload.end_date,
                predicted_value=float(pred.predicted_value),
                created_at=pred.created_at,
            ))
        
        return PastPredictionsResponse(
            predictions=prediction_list,
            count=len(prediction_list),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format. Use YYYY-MM-DD: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to retrieve past predictions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve predictions: {str(e)}"
        )

# Single Prediction  (POST /api/predictOne)
@app.post("/api/predictOne", response_model=PredictOneResponse,
          responses={
        200: {"description": "Single prediction successful"},
        400: {"description": "Invalid file format"},
        503: {"description": "Model not loaded"}})
def predict_one(payload: PredictOneRequest,
                 model: object = Depends(model_required),
                 db: Session = Depends(get_db)) -> PredictOneResponse:
    try:
        import pandas as pd
        
        # Build feature dict matching model training columns
        features_dict = {
            #location features
            'location_name': payload.location.location_name,
            'longitude' : payload.location.longitude,
            'latitude' : payload.location.latitude,
            'actual_lag_hours':payload.location.actual_lag_hours,
            # Numeric sensor metrics
            'value_avg': payload.sensor_metrics.value_avg,
            'min': payload.sensor_metrics.min,
            'max': payload.sensor_metrics.max,
            'q25': payload.sensor_metrics.q25,
            'median': payload.sensor_metrics.median,
            'q75': payload.sensor_metrics.q75,
            'aqi': payload.sensor_metrics.aqi,
            # Categorical parameter
            'parameter': payload.sensor_metrics.parameter,
            # Temporal features
            'hour': payload.temporal.hour,
            'day_of_week': payload.temporal.day_of_week,
            'month': payload.temporal.month,
            'year': payload.temporal.year,
        }
        
        # Convert to DataFrame for sklearn pipeline
        features_df = pd.DataFrame([features_dict])
        
        # Predict - pipeline handles scaling + encoding automatically
        prediction_value = model.predict(features_df)[0]
        
        # Save prediction to database with all features
        prediction_record = Predictions(
            model_name="XGBoost",
            model_version="v1.0.0",
            # Location features
            location_name=payload.location.location_name,
            latitude=float(payload.location.latitude),
            longitude=float(payload.location.longitude),
            actual_lag_hours=float(payload.location.actual_lag_hours),
            # Sensor metrics features
            parameter_name=payload.sensor_metrics.parameter,
            value_avg=float(payload.sensor_metrics.value_avg),
            min=float(payload.sensor_metrics.min),
            max=float(payload.sensor_metrics.max),
            q25=float(payload.sensor_metrics.q25),
            median=float(payload.sensor_metrics.median),
            q75=float(payload.sensor_metrics.q75),
            aqi=float(payload.sensor_metrics.aqi),
            # Temporal features
            hour=payload.temporal.hour,
            day_of_week=payload.temporal.day_of_week,
            month=payload.temporal.month,
            year=payload.temporal.year,
            # Prediction result and metadata
            predicted_value=float(prediction_value),
            source=str(payload.source)
        )
        db.add(prediction_record)
        db.commit()
        db.refresh(prediction_record)
        
        logger.info(f"Prediction saved: ID={prediction_record.prediction_id}, value={prediction_value}")
        
        return PredictOneResponse(
            prediction=float(prediction_value),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}"
        )
    
# Many Predictions  (POST /api/predictMany)
@app.post("/api/predictMany",response_model=PredictManyResponse,
    responses={
        200: {"description": "Batch predictions successful"},
        400: {"description": "Invalid file format"},
        503: {"description": "Model not loaded"},
    })
async def predict_many(payload: list[PredictOneRequest],
                        model: object = Depends(model_required),
                        db: Session = Depends(get_db)) -> PredictManyResponse:
    try:
        import pandas as pd
        
        # Convert list of requests to list of feature dicts
        features_list = []
        location_data = []
        
        for request in payload:
            features_dict = {
                # Location features
                'location_name': request.location.location_name,
                'longitude': request.location.longitude,
                'latitude': request.location.latitude,
                'actual_lag_hours': request.location.actual_lag_hours,
                # Numeric sensor metrics
                'value_avg': request.sensor_metrics.value_avg,
                'min': request.sensor_metrics.min,
                'max': request.sensor_metrics.max,
                'q25': request.sensor_metrics.q25,
                'median': request.sensor_metrics.median,
                'q75': request.sensor_metrics.q75,
                'aqi': request.sensor_metrics.aqi,
                # Categorical parameter
                'parameter': request.sensor_metrics.parameter,
                # Temporal features
                'hour': request.temporal.hour,
                'day_of_week': request.temporal.day_of_week,
                'month': request.temporal.month,
                'year': request.temporal.year,
            }
            features_list.append(features_dict)
            location_data.append({
                # Location features
                'location_name': request.location.location_name,
                'latitude': request.location.latitude,
                'longitude': request.location.longitude,
                'actual_lag_hours': request.location.actual_lag_hours,
                # Sensor metrics features
                'parameter': request.sensor_metrics.parameter,
                'value_avg': request.sensor_metrics.value_avg,
                'min': request.sensor_metrics.min,
                'max': request.sensor_metrics.max,
                'q25': request.sensor_metrics.q25,
                'median': request.sensor_metrics.median,
                'q75': request.sensor_metrics.q75,
                'aqi': request.sensor_metrics.aqi,
                # Temporal features
                'hour': request.temporal.hour,
                'day_of_week': request.temporal.day_of_week,
                'month': request.temporal.month,
                'year': request.temporal.year,
            })
        
        # Convert to DataFrame for sklearn pipeline
        features_df = pd.DataFrame(features_list)
        
        # Predict - pipeline handles scaling + encoding automatically
        predictions = model.predict(features_df)
        
        # Save predictions to database
        prediction_records = []
        for idx, (pred_value, loc_data) in enumerate(zip(predictions, location_data)):
            prediction_record = Predictions(
                model_name="XGBoost PM2.5 Predictor",
                model_version="v1.0.0",
                # Location features
                location_name=loc_data['location_name'],
                latitude=float(loc_data['latitude']),
                longitude=float(loc_data['longitude']),
                actual_lag_hours=float(loc_data['actual_lag_hours']),
                # Sensor metrics features
                parameter_name=loc_data['parameter'],
                value_avg=float(loc_data['value_avg']),
                min=float(loc_data['min']),
                max=float(loc_data['max']),
                q25=float(loc_data['q25']),
                median=float(loc_data['median']),
                q75=float(loc_data['q75']),
                aqi=float(loc_data['aqi']),
                # Temporal features
                hour=loc_data['hour'],
                day_of_week=loc_data['day_of_week'],
                month=loc_data['month'],
                year=loc_data['year'],
                # Prediction result and metadata
                predicted_value=float(pred_value),
                source=str(payload[idx].source),
            )
            prediction_records.append(prediction_record)
        
        # Bulk insert all predictions
        db.add_all(prediction_records)
        db.commit()
        
        logger.info(f"Batch predictions saved: {len(prediction_records)} records")
        
        # Build response with list of PredictionResult objects
        prediction_results = [
            PredictionResult(index=idx, prediction=float(pred))
            for idx, pred in enumerate(predictions)
        ]
        
        return PredictManyResponse(
            predictions=prediction_results,
            total_predictions=len(prediction_results),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Batch prediction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}"
        )


# Health Check for Database Connectivity (GET /health/db)
@app.get("/health/db")
def health_db(db=Depends(get_db)):
    try:
        result = db.execute(text("SELECT 1 as connection_test, version() as db_version"))
        row = result.fetchone()
        
        return {
            "status": "ok",
            "database": "connected",
            "db_response": row.connection_test,
            "db_version": row.db_version,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "disconnected",
                "error": str(e),
                "database_url": DATABASE_URL.replace("://", "://***:***@")
            }
        )
