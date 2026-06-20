import logging
from datetime import datetime, timedelta
import os, random, json, shutil
import pandas as pd
import requests as req
import great_expectations as gx
import pendulum
from airflow.sdk import dag, task, get_current_context
from airflow.exceptions import AirflowFailException
from airflow.providers.postgres.hooks.postgres import PostgresHook
from typing import Dict, Any

BASE_DIR = "/opt/airflow/data"
GX_PROJECT_ROOT = "/opt/airflow/gx"
DATA_DOCS_PATH = "/opt/airflow/data_docs"

def generate_data_docs(validation_data: Dict[str, Any]) -> str:
    gx_context = gx.get_context(context_root_dir=GX_PROJECT_ROOT)
    gx_context.build_data_docs()
    
    source = os.path.join(GX_PROJECT_ROOT, "uncommitted", "data_docs", "local_site", "index.html")
    filename = f"report_{validation_data['filename'].replace('.csv', '')}.html"
    dest = os.path.join(DATA_DOCS_PATH, filename)
    
    os.makedirs(DATA_DOCS_PATH, exist_ok=True)
    shutil.copy2(source, dest)
    
    return filename

@dag(
    dag_id='data_ingestion_dag',
    description='Ingest data from a file to another DAG',
    tags=['dsp', 'data_ingestion'],
    schedule=None,
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    max_active_runs=1,
    catchup=False
)
def data_ingestion_dag():
    @task(do_xcom_push=True, multiple_outputs=True)
    def read_data() -> dict:
        logger = logging.getLogger("airflow.task")
        data_dir = os.path.join(BASE_DIR, 'errored_data')
        files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]

        chosen_file = random.choice(files)
        filepath = os.path.join(data_dir, chosen_file)
        
        # Read file (deletion moved to cleanup task at end of DAG)
        try:
            df = pd.read_csv(filepath)
            logger.info(f"Read file: {filepath}")
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            raise AirflowFailException(f"Failed to read {filepath}: {e}")

        return {
            "filename": chosen_file,
            "filepath": filepath
        }

    @task(do_xcom_push=True, multiple_outputs=True)
    def validate_data() -> dict:
        logger = logging.getLogger("airflow.task")

        airflow_context = get_current_context()
        ti = airflow_context["ti"]
        file_info = ti.xcom_pull(task_ids="read_data", key="return_value")

        filepath = file_info["filepath"]
        df = pd.read_csv(filepath)

        logger.info(f"Validating file: {filepath}")
        logger.info(f"DataFrame shape: {df.shape}")


        gx_context = gx.get_context(context_root_dir=GX_PROJECT_ROOT)

        # List available suites for debugging
        available_suites = [s.name for s in gx_context.suites.all()]
        logger.info(f"Available suites: {available_suites}")

        suite = gx_context.suites.get("openaq_validation_suite")
        logger.info(f"Loaded suite with {len(suite.expectations)} expectations")

        datasource = gx_context.data_sources.add_pandas(name="runtime_datasource")
        data_asset = datasource.add_dataframe_asset(name="runtime_asset")
        batch_def = data_asset.add_batch_definition_whole_dataframe(name="runtime_batch")
        batch = batch_def.get_batch(batch_parameters={"dataframe": df})

        validator = gx_context.get_validator(batch=batch, expectation_suite=suite)
        result = validator.validate(result_format="COMPLETE")
        # cleanup
        gx_context.delete_datasource("runtime_datasource")

        stats = result.statistics
        total_expectations = stats.get("evaluated_expectations", 0)
        failed_expectations = stats.get("unsuccessful_expectations", 0)
        success_rate = stats.get("success_percent", 100) / 100

        total_data_rows = len(df)
        bad_row_indices: set = set()
        for r in result.results:
            unexpected = r.result.get("unexpected_index_list", []) or []
            bad_row_indices.update(unexpected)
        bad_row_count = len(bad_row_indices)
        invalid_percent = (bad_row_count / total_data_rows * 100) if total_data_rows > 0 else 0
        criticality = None

        # check for schema failures (column-related expectations) + determine criticality
        schema_failed = any(
            not r.success and r.expectation_config.type == "expect_column_to_exist"
            for r in result.results
        )
        if schema_failed or invalid_percent > 50:
            criticality = "HIGH"
        elif invalid_percent > 10:
            criticality = "MEDIUM"
        elif invalid_percent > 0:
            criticality = "LOW"
        
        # Log results
        logger.info(f"Validation success: {result.success}")
        logger.info(f"Total expectations: {total_expectations} | Failed expectations: {failed_expectations}")
        logger.info(f"Bad rows: {bad_row_count} / {total_data_rows} ({invalid_percent:.1f}%)")
        logger.info(f"Criticality: {criticality}")

        return {
            "filename": file_info["filename"],
            "filepath": filepath,
            "total_rows": total_expectations,
            "failed_rows": failed_expectations,
            "bad_rows_count": bad_row_count,
            "total_data_rows": total_data_rows,
            "invalid_percent": invalid_percent,
            "criticality": criticality,
            "success": result.success,
            "success_rate": success_rate,
            "validation_result_json": result.to_json_dict()
        }

    @task
    def save_statistics():
        logger = logging.getLogger("airflow.task")

        airflow_context = get_current_context()
        ti = airflow_context["ti"]
        validation_info = ti.xcom_pull(task_ids="validate_data")

        filepath = validation_info["filepath"]
        filename = os.path.basename(filepath)
        criticality = validation_info["criticality"]
        if not criticality:
            criticality = "NONE"
        total = validation_info["total_rows"]
        failed = validation_info["failed_rows"]
        passed = total - failed
        success = validation_info["success"]
        success_rate = round((passed / total) * 100, 2) if total > 0 else 0.0

        hook = PostgresHook(postgres_conn_id="airflow_postgres")
        conn = hook.get_conn()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_statistics (
                id BIGSERIAL PRIMARY KEY,
                run_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                dag_run_id VARCHAR(255),
                filename VARCHAR(255) NOT NULL,
                criticality VARCHAR(10) NOT NULL,
                total_expectations INT NOT NULL,
                passed_expectations INT NOT NULL,
                failed_expectations INT NOT NULL,
                success_rate NUMERIC(5, 2) NOT NULL,
                validation_success BOOLEAN NOT NULL
            );
        """)

        dag_run_id = ti.run_id if hasattr(ti, "run_id") else None

        cur.execute("""
            INSERT INTO data_quality_statistics
                (dag_run_id, filename, criticality, total_expectations,
                 passed_expectations, failed_expectations, success_rate, validation_success)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (dag_run_id, filename, criticality, total, passed, failed, success_rate, success))

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Saved quality stats for {filename}: criticality={criticality}, rate={success_rate}%")

    @task
    def send_alerts():
        logger = logging.getLogger("airflow.task")

        airflow_context = get_current_context()
        ti = airflow_context["ti"]
        validation_info = ti.xcom_pull(task_ids="validate_data")

        filepath = validation_info["filepath"]
        filename = os.path.basename(filepath)
        criticality = validation_info["criticality"]
        total_expectations = validation_info["total_rows"]
        failed_expectations = validation_info["failed_rows"]

        if not criticality or criticality == "LOW":
            logger.info("All validations passed or LOW criticality – no alert needed.")
            return

        df = pd.read_csv(filepath)
        gx_context = gx.get_context(context_root_dir=GX_PROJECT_ROOT)
        suite = gx_context.suites.get("openaq_validation_suite")

        datasource = gx_context.data_sources.add_pandas(name="alert_datasource")
        data_asset = datasource.add_dataframe_asset(name="alert_asset")
        batch_def = data_asset.add_batch_definition_whole_dataframe(name="alert_batch")

        validation_definition = gx_context.validation_definitions.add(
            gx.ValidationDefinition(
                name="alert_validation_def",
                data=batch_def,
                suite=suite,
            )
        )

        result = validation_definition.run(batch_parameters={"dataframe": df})
        gx_context.build_data_docs()

        report_name = f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        data_docs_dir = os.path.join(GX_PROJECT_ROOT, "uncommitted", "data_docs", "local_site")
        os.makedirs(DATA_DOCS_PATH, exist_ok=True)
        report_path = os.path.join(DATA_DOCS_PATH, report_name)
        shutil.copytree(data_docs_dir, report_path)
        logger.info(f"Data Docs report saved to {report_path}")

        error_lines = []
        for exp_result in result.results:
            if not exp_result.success:
                exp_type = exp_result.expectation_config.type
                kwargs = exp_result.expectation_config.kwargs
                col = kwargs.get("column", kwargs.get("column_list", "dataset"))
                error_lines.append(f"\u2022 {exp_type} on '{col}'")
        error_summary = "\n".join(error_lines) if error_lines else "No details."

        gx_context.validation_definitions.delete("alert_validation_def")
        gx_context.delete_datasource("alert_datasource")

        color_map = {"HIGH": "FF0000", "MEDIUM": "FFA500", "LOW": "FFFF00"}
        emoji_map = {"HIGH": "\U0001f534", "MEDIUM": "\U0001f7e0", "LOW": "\U0001f7e1"}

        message = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color_map.get(criticality, "808080"),
            "summary": f"Data Quality Alert \u2013 {criticality}",
            "sections": [{
                "activityTitle": f"{emoji_map.get(criticality, '')} Data Quality Alert \u2013 {criticality} Criticality",
                "facts": [
                    {"name": "File", "value": filename},
                    {"name": "Criticality", "value": criticality},
                    {"name": "Failed / Total", "value": f"{failed_expectations} / {total_expectations}"},
                    {"name": "Errors", "value": error_summary},
                    {"name": "Report", "value": f"[{report_name}](/reports/{report_name}/index.html)"},
                ],
                "markdown": True,
            }],
        }

        webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
        if webhook_url:
            resp = req.post(webhook_url, json=message, timeout=30)
            resp.raise_for_status()
            logger.info("Teams notification sent to Data Quality Alerts channel.")
        else:
            logger.warning("TEAMS_WEBHOOK_URL not set \u2013 alert logged only.")
            logger.info(json.dumps(message, indent=2))

    @task
    def split_and_save_data():
        logger = logging.getLogger("airflow.task")

        airflow_context = get_current_context()
        ti = airflow_context["ti"]
        validation_info = ti.xcom_pull(task_ids="validate_data")

        filepath = validation_info["filepath"]
        filename = os.path.basename(filepath)
        success = validation_info["success"]

        good_dir = os.path.join(BASE_DIR, "good_data")
        bad_dir = os.path.join(BASE_DIR, "bad_data")
        os.makedirs(good_dir, exist_ok=True)
        os.makedirs(bad_dir, exist_ok=True)

        if success:
            shutil.copy2(filepath, os.path.join(good_dir, filename))
            logger.info(f"All rows valid – copied {filename} to good_data")
            return

        validation_result_json = validation_info["validation_result_json"]
        bad_indices = set()

        # 1. Do schema check
        for exp_result in validation_result_json["results"]:
            exp_type = exp_result["expectation_config"]["type"]
            if exp_type == "expect_column_to_exist" and not exp_result["success"]:
                logger.warning("Schema failure – entire file moved to bad_data")
                shutil.copy2(filepath, os.path.join(bad_dir, filename))
                return

        df = pd.read_csv(filepath)

        # 2. Collect bad row indices from all other expectations
        for exp_result in validation_result_json["results"]:
            result_key = exp_result.get("result", {})
            unexpected_indices = result_key.get("unexpected_index_list", [])
            if unexpected_indices:
                bad_indices.update(unexpected_indices)

        bad_df = df[df.index.isin(bad_indices)]
        good_df = df[~df.index.isin(bad_indices)]

        if len(bad_df) == 0:
            shutil.copy2(filepath, os.path.join(good_dir, filename))
            logger.info(f"All {len(good_df)} rows valid – copied to good_data")
        elif len(good_df) == 0:
            shutil.copy2(filepath, os.path.join(bad_dir, filename))
            logger.info(f"All {len(bad_df)} rows invalid – copied to bad_data")
        else:
            good_df.to_csv(os.path.join(good_dir, filename), index=False)
            bad_df.to_csv(os.path.join(bad_dir, filename), index=False)

    @task
    def cleanup_processed_file():
        logger = logging.getLogger("airflow.task")
        
        airflow_context = get_current_context()
        ti = airflow_context["ti"]
        validation_info = ti.xcom_pull(task_ids="validate_data")
        
        filepath = validation_info["filepath"]
        
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Deleted file after validation: {filepath}")
            else:
                logger.warning(f"File not found for deletion: {filepath}")
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            raise AirflowFailException(f"Failed to delete {filepath}: {e}")

    # save_statistics and send_alerts run in parallel after validate_data (LocalExecutor)
    data = read_data()
    validation = validate_data()
    stats = save_statistics()
    alerts = send_alerts()

    split = split_and_save_data()
    cleanup = cleanup_processed_file()
    
    data >> validation >> [stats, alerts, split] >> cleanup



data_ingestion_dag()
