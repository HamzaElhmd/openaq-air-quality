# OpenAQ ML Production Project

End-to-end ML production system for air quality prediction using OpenAQ data from France. The system ingests CSV data, validates it with Great Expectations, runs XGBoost predictions via a FastAPI service, and displays results through a Streamlit web application.

## Architecture

The project is fully containerized with Docker Compose and consists of the following services:

- **PostgreSQL** (`db`) — Stores predictions (`openaq_db`) and Airflow metadata (`airflow_db`)
- **FastAPI** (`api/`) — ML model serving API (single and batch predictions)
- **Streamlit** (`webapp/`) — Web interface for submitting predictions and viewing history
- **Apache Airflow** (`airflow/`) — Orchestrates two DAGs:
  - `data_ingestion_dag` — Reads, validates (Great Expectations), splits, and alerts on data quality
  - `prediction_dag` — Sends validated data to the API for batch predictions
- **pgAdmin** — Database administration UI
- **Great Expectations** (`airflow/gx/`) — Data quality validation suite

### Service Ports

| Service          | URL                          |
|------------------|------------------------------|
| Streamlit UI     | http://localhost:8501        |
| FastAPI (Docs)   | http://localhost:8000/docs   |
| Airflow UI       | http://localhost:8080        |
| pgAdmin          | http://localhost:5050        |
| PostgreSQL       | localhost:5432               |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2+)
- Git
- At least **4 GB RAM** and **2 CPUs** allocated to Docker
- A trained model file at `model/model.pkl` (XGBoost pipeline serialized with `joblib`)

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd openaq-ml-production-project
```

### 2. Configure environment variables

The project ships with a default `.env` file. Review it and adjust values if needed:

```bash
# Key variables in .env:
POSTGRES_USER=openaq_user
POSTGRES_PASSWORD=123456789       # Change in production
POSTGRES_DB=openaq_db
POSTGRES_AIRFLOW_DB=airflow_db
API_PORT=8000
STREAMLIT_SERVER_PORT=8501
AIRFLOW_PORT=8080
AIRFLOW_USER=admin
AIRFLOW_PASSWORD=admin            # Change in production
TEAMS_WEBHOOK_URL=...             # Optional: Microsoft Teams alerts
```

### 3. Set the Airflow UID (Linux only)

```bash
echo "AIRFLOW_UID=$(id -u)" >> .env
```

### 4. Place the trained model

Ensure the serialized model pipeline exists at:

```
model/model.pkl
```

### 5. Prepare the data

CSV files for ingestion should be placed in:

```
data/errored_data/
```

The project includes sample data files in this directory.

## Running the Project

### Start all services

```bash
docker compose up -d
```

On the first run, the `airflow-init` service will set up the database, create the admin user, and configure permissions. Wait for it to complete before using Airflow.

### Verify services are running

```bash
docker compose ps
```

### Check API health

```bash
curl http://localhost:8000/health/ready
```

### Stop all services

```bash
docker compose down
```

To also remove persisted data volumes:

```bash
docker compose down -v
```

## Usage

### Streamlit Web App

Open http://localhost:8501 to access the web interface:

- **Prediction Form** — Submit air quality features (location, sensor metrics, temporal data) for a single prediction
- **Past Predictions** — Browse and filter historical predictions by date range and source

### FastAPI Endpoints

Access the interactive API docs at http://localhost:8000/docs.

Key endpoints:

- `POST /api/predictOne` — Single prediction with location, sensor, and temporal features
- `POST /api/predictMany` — Batch predictions from a list of feature sets
- `GET /api/past_predictions` — Retrieve past predictions filtered by date range and source
- `GET /health/ready` — Readiness probe (checks database + model status)
- `GET /health/db` — Database connectivity check

### Airflow DAGs

Access the Airflow UI at http://localhost:8080 (default credentials: `admin`/`admin`).

1. **`data_ingestion_dag`** (manual trigger) — Picks a random CSV from `data/errored_data/`, validates it with Great Expectations, saves quality statistics to PostgreSQL, sends Teams alerts for medium/high-criticality issues, splits data into `good_data/` and `bad_data/`, and cleans up the source file.

2. **`prediction_dag`** (manual trigger) — Reads validated files from `data/good_data/`, sends them to the FastAPI `/api/predictMany` endpoint, and archives processed files to `data/archived_data/`.

### pgAdmin

Access pgAdmin at http://localhost:5050 (default credentials: `admin@admin.com` / `admin123`).

## Project Structure

```
.
├── airflow/
│   ├── dags/                  # Airflow DAG definitions
│   │   ├── data_ingestion_dag.py
│   │   └── prediction_dag.py
│   ├── gx/                    # Great Expectations configuration
│   ├── config/                # Airflow configuration
│   ├── Dockerfile
│   └── requirements.txt
├── api/
│   ├── main.py                # FastAPI application
│   ├── schemas.py             # Pydantic request/response models
│   ├── models.py              # SQLAlchemy ORM models
│   ├── db.py                  # Database connection
│   ├── settings.py            # Environment settings
│   ├── Dockerfile
│   └── requirements.txt
├── webapp/
│   ├── Welcome.py             # Streamlit entry point
│   ├── pages/
│   │   ├── 1_Past_Predictions.py
│   │   └── 2_Prediction_Form.py
│   ├── config/
│   ├── Dockerfile
│   └── requirements.txt
├── db/
│   └── init_db.sql            # Database initialization script
├── data/
│   └── errored_data/          # Input CSV files for ingestion
├── model/
│   └── model.pkl              # Trained XGBoost model pipeline
├── scripts/
│   └── setup_gx.py            # Great Expectations suite setup
├── docker-compose.yml
├── .env                       # Environment configuration
└── README.md
```

## Data Quality Validation

The Great Expectations suite (`openaq_validation_suite`) checks:

- **Completeness** — Required columns are non-null
- **Validity** — Latitude/longitude within expected ranges for France
- **Consistency** — Units match expected values (`µg/m³`)
- **Schema** — Required columns exist (e.g., `parameter`)
- **Data types** — Numeric columns match expected formats
- **Duplicates** — Compound column uniqueness checks
- **Outliers** — Sensor values within reasonable physical ranges

Criticality levels are assigned based on failure severity:
- **HIGH** — Schema failures or >50% invalid expectations
- **MEDIUM** — >10% invalid expectations
- **LOW** — >0% invalid expectations

## License

MIT License — see [LICENSE](LICENSE) for details.
