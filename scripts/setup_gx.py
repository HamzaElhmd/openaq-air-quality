import great_expectations as gx
import os
import shutil
import glob
import pandas as pd

project_root = "."
datasource_name = "openaq_csv_source"
asset_name = "openaq_raw_files"
suite_name = "openaq_validation_suite"


csv_pattern = "../data/raw_data/*.csv"
script_dir = os.path.dirname(os.path.abspath(__file__))
absolute_pattern = os.path.join(script_dir, csv_pattern)
csv_files = glob.glob(absolute_pattern)
csv_path = csv_files[0]


# NOTE: This path is a PLACEHOLDER only.
# The actual file path is always provided at runtime via batch_parameters.
# This script generates static GX configs; runtime validation uses dynamic paths.
PLACEHOLDER_PATH = "/data/placeholder.csv"
print(os.getcwd())

def setup_gx():
    context = gx.get_context(mode="file", project_root_dir=project_root)
    print(context.list_datasources())
    existing_dsn = [ds["name"] for ds in context.list_datasources()]
    if datasource_name in existing_dsn:
        # data_source = context.data_sources.get(datasource_name)
        print("Here")
        context.delete_datasource(datasource_name)
    data_source = context.data_sources.add_pandas(name=datasource_name)
    # data_source = context.data_sources.add_pandas(name=datasource_name)
    asset = data_source.add_csv_asset(
        name=asset_name,
        filepath_or_buffer=PLACEHOLDER_PATH
    )

    batch_def = asset.add_batch_definition_whole_dataframe(name="single_file_batch")

    suite = context.suites.add(gx.ExpectationSuite(name=suite_name))
    
    # 1. Completeness
    completeness_cols = ["sensor_id", "location_id", "location_name", "latitude", "longitude","value_avg", "min", "max", "q25", "median", "q75", "std","expected_count", "observed_count", "percent_complete"]
    for col in completeness_cols:
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToNotBeNull(column=col)
        )
    
   # 2. VALIDITY: Single range covering both mainland France AND overseas territories
    # Mainland: ~43-52°N, ~-5 to 8°E | Réunion: ~-21°S, ~55°E
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="latitude",
            min_value=-25,
            max_value=55
        )
    )

    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="longitude",
            min_value=-65,
            max_value=60
        )
    )
    
    # 3. Consistency
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="units",
            value_set=["µg/m³"]
        )
    )

    # 4. Schema
    suite.add_expectation(
        gx.expectations.ExpectColumnToExist(
            column="parameter"
        )
    )

    # 5. Data type
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToMatchRegex(
            column="expected_count",
            regex=r"^\d+$"
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToMatchRegex(
            column="observed_count",
            regex=r"^\d+$"
        )
    )

    # 6. Duplicates
    suite.add_expectation(
        gx.expectations.ExpectCompoundColumnsToBeUnique(
            column_list=["sensor_id", "date", "datetime_utc", "datetime_local", "value_avg","parameter", "units", "min", "max", "q25", "median", "q75", "std","expected_count", "observed_count", "percent_complete", "location_id","location_name", "latitude", "longitude", "aqi", "aqi_after_12h","actual_lag_hours", "hour", "day_of_week", "month", "year"]
        )
    )

    # 7. Outliers
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="value_avg",
            min_value=0,
            max_value=3700
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="min",
            min_value=0,
            max_value=3700
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="max",
            min_value=0,
            max_value=3700
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="q25",
            min_value=0,
            max_value=3700
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="median",
            min_value=0,
            max_value=3700
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="q75",
            min_value=0,
            max_value=3700
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="std",
            min_value=0,
            max_value=500
        )
    )

    val_def = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="validate_openaq_file",
            data=batch_def,
            suite=suite,
        )
    )

    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name="openaq_checkpoint",
            validation_definitions=[val_def],
            actions=[
                gx.checkpoint.UpdateDataDocsAction(name="update_data_docs")
            ],
        )
    )
    return context, checkpoint, val_def, batch_def

def run_validation(context, file_path=None):
    print(f"RUNNING VALIDATION")
    print(f"-------------------------------------------------------------------------------")
    df = pd.read_csv(file_path)
    print(f"File path: {file_path} | Rows: {len(df)}")
    
    suite = context.suites.get(suite_name)
    batch_parameters = {"dataframe": df}
    
    # use checkpoint with dataframe batch parameters
    # create new validation definition with dynamic batch parameters
    datasource = context.data_sources.add_pandas(name="runtime_datasource")
    data_asset = datasource.add_dataframe_asset(name="runtime_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe(name="runtime_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})
    
    # validate
    validator = context.get_validator(batch=batch, expectation_suite=suite)
    result = validator.validate(result_format="COMPLETE")
    
    # cleanup
    context.delete_datasource("runtime_datasource")
    
    # Print results
    print(f"-------------------------------------------------------------------------------")
    print(f"Success: {result.success}")
    stats = result.statistics
    print(f"   Evaluated: {stats['evaluated_expectations']}")
    print(f"   Successful: {stats['successful_expectations']}")
    print(f"   Failed: {stats['unsuccessful_expectations']}")
    
    if not result.success:
        failed = [r for r in result.results if not r.success]
        print(f"-------------------------------------------------------------------------------")
        print(f"Failed expectations: {len(failed)}")
        for f in failed[:3]:
            print(f"   - {f.expectation_config.type}")
    
    return result

if __name__ == "__main__":
    context, checkpoint, val_def, batch_def = setup_gx()
    result = run_validation(context, file_path=csv_path)