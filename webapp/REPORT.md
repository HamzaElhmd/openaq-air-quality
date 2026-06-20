# Steps Taken

## Setup

```bash
pip install streamlit
```

- In the python script, I set the title of the page first to 'OpenAq'.
- Added a Pages foldar.
- Add past_predictions.py and predictions_form.py to pages folder.
- Configure entrypoint page.
- Empty Pages for Now.
- Added button to 1_Past_Predictions.py
- Created JSON file for server configurations used by the client.
- Involve the use of environment variable to correctly set the path of config depending on Operating System.
- Need to know the endpoint for getting a prediction.
- Missing past predictions data (querying from the database).
- Implementing a shell script for defining the server configuration path.
- Added end date and start date widgets.
- Added select box with source of prediction.
- Added radio button to pick between csv file upload or form.

## Data Ingestion DAG – `save_statistics` and `send_alerts`

### What was done

Two new Airflow tasks were added to the `data_ingestion_dag`: `save_statistics` and `send_alerts`. Both run **in parallel** after the `validate_data` task finishes, using the `LocalExecutor` (not the `SequentialExecutor`).

### Task graph

```
read_data -> validate_data -> save_statistics
                           -> send_alerts
```

`save_statistics` and `send_alerts` fan out from `validate_data` and execute at the same time.

### `save_statistics` – what it does step by step

1. Pulls the validation results from XCom (the dictionary that `validate_data` returned).
2. Extracts the filename, criticality level, total/failed/passed expectation counts, and whether the overall validation passed.
3. Computes `success_rate` as `(passed / total) * 100`, rounded to two decimals.
4. Connects to the PostgreSQL `openaq_db` database using the `DATABASE_URL` environment variable and `psycopg2`.
5. Runs `CREATE TABLE IF NOT EXISTS data_quality_statistics (...)` so the table is created on first run if it does not already exist.
6. Inserts one row with these columns:
   - `dag_run_id` – the Airflow run ID, useful for correlating with Airflow logs.
   - `filename` – which CSV file was validated.
   - `criticality` – HIGH, MEDIUM, LOW, or NONE.
   - `total_expectations` – how many Great Expectations rules were evaluated.
   - `passed_expectations` / `failed_expectations` – counts of each.
   - `success_rate` – percentage of expectations that passed.
   - `validation_success` – boolean, true only if every expectation passed.
   - `run_timestamp` – auto-filled by PostgreSQL with the current time.
7. Commits and closes the connection.

The table is also declared in `db/init_db.sql` with indexes on `run_timestamp` and `criticality` so Grafana can query it efficiently for time-series dashboards.

### `send_alerts` – what it does step by step

1. Pulls the same validation results from XCom.
2. If `criticality` is `NONE` (everything passed), it logs a message and exits early – no alert is sent.
3. Re-reads the CSV file and re-runs validation through Great Expectations. This second run is needed because:
   - `validate_data` does not store its result in the GX validation results store.
   - We need the full per-expectation result objects to build a detailed error summary.
   - We need stored results for GX to generate Data Docs.
4. Creates a temporary runtime datasource, data asset, and batch definition (same pattern as `validate_data`).
5. Creates a `ValidationDefinition` and adds it to the GX context, then calls `.run()`. This stores the validation result in the GX validation results store.
6. Calls `gx_context.build_data_docs()` which reads all stored results and generates the Great Expectations Data Docs HTML site at `gx/uncommitted/data_docs/local_site/`.
7. Copies the entire Data Docs site to `/opt/airflow/data/reports/validation_report_<YYYYMMDD_HHMMSS>/` so each run gets its own timestamped snapshot. This is the report that will later be served via nginx.
8. Loops through every expectation result and collects the ones that failed. For each failure it records the expectation type (e.g. `expect_column_values_to_not_be_null`) and the column it applies to.
9. Cleans up the temporary GX resources (deletes the validation definition and the runtime datasource).
10. Builds a Microsoft Teams `MessageCard` JSON payload containing:
    - A color-coded header: red for HIGH, orange for MEDIUM, yellow for LOW.
    - The filename that was validated.
    - The criticality level.
    - The count of failed vs. total expectations.
    - The list of specific failed expectations (the error summary).
    - A clickable link to the Data Docs report (`/reports/<report_name>/index.html`), ready for nginx to serve.
11. If the `TEAMS_WEBHOOK_URL` environment variable is set, it POSTs the message to that URL (the Data Quality Alerts channel). Otherwise it logs the full message payload as a warning so nothing is lost silently.

### Criticality levels (determined by `validate_data`, unchanged)

- **HIGH**: A column-level expectation failed (missing column) OR more than 50% of expectations failed.
- **MEDIUM**: Between 10% and 50% of expectations failed.
- **LOW**: More than 0% but less than 10% of expectations failed.
- **NONE**: Everything passed.

### Files changed

- `airflow/dags/data_ingestion_dag.py` – added `save_statistics` and `send_alerts` implementations, changed task wiring to parallel.
- `db/init_db.sql` – added `data_quality_statistics` table and indexes.
- `airflow/requirements.txt` – added `psycopg2-binary` and `requests`.
