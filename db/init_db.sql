CREATE DATABASE airflow_db;
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO CURRENT_USER;

\c airflow_db;

-- data quality statistics from validation DAG
CREATE TABLE data_quality (
    stats_id BIGSERIAL PRIMARY KEY,
    batch_date DATE NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    total_rows INT NOT NULL,
    invalid_rows INT NOT NULL,
    null_values INT NOT NULL,
    invalid_ranges INT NOT NULL,
    invalid_categories INT NOT NULL,
    invalid_types INT NOT NULL,
    duplicates INT NOT NULL,
    format_errors INT NOT NULL,
    other_errors INT NOT NULL,
    error_rate NUMERIC(5, 2),  -- percentage of invalid rows
    validation_status VARCHAR(20) NOT NULL,  -- passed, failed, warning
    validation_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_statistics_batch_date ON data_quality (batch_date DESC);
CREATE INDEX idx_statistics_file ON data_quality (file_name);
CREATE INDEX idx_statistics_status ON data_quality (validation_status);

-- track which files have been processed by prediction DAG
CREATE TABLE processed_files (
    file_id BIGSERIAL PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL UNIQUE,
    processed_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_processed_files_name ON processed_files (file_name);

\c openaq_db;

-- store predictions from the model API
CREATE TABLE predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    
    -- Location features
    location_name VARCHAR(255),
    latitude NUMERIC(12, 9),
    longitude NUMERIC(12, 9),
    actual_lag_hours NUMERIC(12, 4),
    
    -- Sensor metrics features
    parameter_name VARCHAR(50),
    value_avg NUMERIC(12, 4),
    min NUMERIC(12, 4),
    max NUMERIC(12, 4),
    q25 NUMERIC(12, 4),
    median NUMERIC(12, 4),
    q75 NUMERIC(12, 4),
    aqi NUMERIC(12, 4),
    
    -- Temporal features
    hour INTEGER,
    day_of_week INTEGER,
    month INTEGER,
    year INTEGER,
    
    -- Prediction result and metadata
    predicted_value NUMERIC(12, 4) NOT NULL,
    source VARCHAR(50),  -- e.g., webapp, scheduled_predictions, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_predictions_model ON predictions (model_name);
CREATE INDEX idx_predictions_version ON predictions (model_version);
CREATE INDEX idx_predictions_location ON predictions (location_name);
CREATE INDEX idx_predictions_timestamp ON predictions (created_at DESC);