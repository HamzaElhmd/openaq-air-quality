from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, BigInteger, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class DataQuality(Base):
    __tablename__ = "data_quality"
    stats_id = Column(BigInteger, primary_key=True)
    batch_date = Column(Date, nullable=False)
    file_name = Column(String(255), nullable=False, index=True)
    total_rows = Column(Integer, nullable=False)
    invalid_rows = Column(Integer, nullable=False)
    null_values = Column(Integer, nullable=False)
    invalid_ranges = Column(Integer, nullable=False)
    invalid_categories = Column(Integer, nullable=False)
    invalid_types = Column(Integer, nullable=False)
    duplicates = Column(Integer, nullable=False)
    format_errors = Column(Integer, nullable=False)
    other_errors = Column(Integer, nullable=False)
    error_rate = Column(Numeric(5, 2))
    validation_status = Column(String(20), nullable=False, index=True)
    validation_timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    __table_args__ = (Index('idx_statistics_batch_date', 'batch_date'),)
    
    def __repr__(self):
        return f"<DataQuality(file='{self.file_name}', status='{self.validation_status}')>"

class ProcessedFiles(Base):
    __tablename__ = "processed_files"
    file_id = Column(BigInteger, primary_key=True)
    file_name = Column(String(255), nullable=False, unique=True, index=True)
    processed_timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    def __repr__(self):
        return f"<ProcessedFile(id={self.file_id}, name='{self.file_name}')>"

class Predictions(Base):
    __tablename__ = "predictions"
    prediction_id = Column(BigInteger, primary_key=True)
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(50), index=True)
    
    # Location features
    location_name = Column(String(255), index=True)
    latitude = Column(Numeric(12, 9))
    longitude = Column(Numeric(12, 9))
    actual_lag_hours = Column(Numeric(12, 4))
    
    # Sensor metrics features
    parameter_name = Column(String(50))
    value_avg = Column(Numeric(12, 4))
    min = Column(Numeric(12, 4))
    max = Column(Numeric(12, 4))
    q25 = Column(Numeric(12, 4))
    median = Column(Numeric(12, 4))
    q75 = Column(Numeric(12, 4))
    aqi = Column(Numeric(12, 4))
    
    # Temporal features
    hour = Column(Integer)
    day_of_week = Column(Integer)
    month = Column(Integer)
    year = Column(Integer)
    
    # Prediction result and metadata
    predicted_value = Column(Numeric(12, 4), nullable=False)
    source = Column(String(50))  # e.g., webapp, scheduled_predictions, etc.
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    __table_args__ = (Index('idx_predictions_timestamp', 'created_at'),)

    def __repr__(self):
        return f"<Prediction(id={self.prediction_id}, model='{self.model_name}', value={self.predicted_value})>"