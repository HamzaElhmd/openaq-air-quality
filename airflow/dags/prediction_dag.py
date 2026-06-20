from airflow.sdk import dag, task
from datetime import datetime, timedelta
from airflow.exceptions import AirflowSkipException, AirflowFailException
import requests 
import pendulum
import os
import pandas as pd
from pathlib import Path
import shutil
import logging

@dag(
    dag_id="prediction_dag",
    description="Make scheduled predictions on ingested data",
    start_date=pendulum.today("UTC"),
    schedule=None,
    catchup=False,
    tags=["prediction"]
)

def pred_job():
    @task(do_xcom_push=True, multiple_outputs=True)
    def check_for_new_data() -> dict:
        logger = logging.getLogger("airflow.task")
        good_data = Path("/opt/airflow/data/good_data")

        try:
            filenames = []
            for f in good_data.iterdir():
                if f.is_file():
                    filenames.append(str(f))
                    logger.info(f"file name: {str(f)}")
        
            if not filenames:
                raise AirflowSkipException("No new data files found")
        except Exception as e:
            logger.error(f"Error checking for new data: {str(e)}")
            raise AirflowSkipException("Error checking for new data")

        return {"filenames": filenames}
        

    @task
    def make_predictions(**kwargs):
        logger = logging.getLogger("airflow.task")
        os.makedirs("/opt/airflow/data/archived_data", exist_ok=True)

        ti = kwargs['ti']
        files = ti.xcom_pull(task_ids='check_for_new_data', key='filenames')
    
        try:
            for file_path in files:
                logger.info(f"Processing file: {file_path}")
                df = pd.read_csv(file_path)
                
                # transform DataFrame rows into the structure that's expected by API
                payload = []
                for _, row in df.iterrows():
                    prediction_request = {
                        "location": {
                            "location_name": row.get("location_name", "Unknown"),
                            "latitude": float(row["latitude"]),
                            "longitude": float(row["longitude"]),
                            "actual_lag_hours": float(row.get("actual_lag_hours", 0))
                        },
                        "sensor_metrics": {
                            "value_avg": float(row["value_avg"]),
                            "min": float(row["min"]),
                            "max": float(row["max"]),
                            "q25": float(row["q25"]),
                            "median": float(row["median"]),
                            "q75": float(row["q75"]),
                            "aqi": float(row.get("aqi", 0)),
                            "parameter": row.get("parameter", "pm25")
                        },
                        "temporal": {
                            "hour": int(row.get("hour", 0)),
                            "day_of_week": int(row.get("day_of_week", 0)),
                            "month": int(row.get("month", 1)),
                            "year": int(row.get("year", 2026))
                        },
			            "source" : "scheduled predictions"
                    }
                    payload.append(prediction_request)

                api_url = "http://api:8000/api/predictMany"
                
                response = requests.post(api_url, json=payload, timeout=30)
                response.raise_for_status()
                
                res_data = response.json()
                predictions = res_data.get("predictions", [])
                
                logger.info(f"Received {len(predictions)} predictions for {len(df)} records")
                os.makedirs("/opt/airflow/data/archived_data", exist_ok=True)
                shutil.move(file_path, "/opt/airflow/data/archived_data")
                logger.info(f"Moved {file_path} to archived_data")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            raise AirflowFailException(f"Failed to call prediction API: {e}")
        
        except Exception as e:
            logger.error(f"Error making predictions: {str(e)}")
            raise AirflowFailException(f"Error making predictions: {e}")
        
    check_for_new_data() >> make_predictions()

pred_job()
