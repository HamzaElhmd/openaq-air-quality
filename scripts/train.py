#%% Import libraries
import pandas as pd 
import xgboost as xgb
from sklearn.preprocessing import OneHotEncoder, RobustScaler
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import matplotlib.pyplot as plt
import numpy as np
import joblib

#%% Import data
df = pd.read_csv("data/france_ml_data_clean.csv")
x = df.drop("aqi_after_12h", axis=1)
y = df["aqi_after_12h"]

#%% Drop unnessary columns
cols_drop = ["sensor_id", "date", "datetime_utc", "datetime_local", "std", "expected_count", "observed_count", "percent_complete", "location_id", "units"]
x = x.drop(cols_drop, axis=1)

#%% Divide numeric and categorical columns
num_cols = x.select_dtypes(include=['int64', 'float64']).columns.tolist()
cat_cols = x.select_dtypes(include=['object', 'category']).columns.tolist()

#%% Transformer and Pipeline
ct = ColumnTransformer([('num', RobustScaler(), num_cols), ('cat', OneHotEncoder(sparse_output=False, handle_unknown='ignore'), cat_cols)])
pipeline = Pipeline([('preprocessor', ct), ('model', xgb.XGBRegressor(device="gpu", random_state=36))])

#%% Train model
pipeline.fit(x, y)

#%% Model evaluation
y_pred = pipeline.predict(x)
mae = mean_absolute_error(y, y_pred)
rmse = np.sqrt(mean_squared_error(y, y_pred))
r2 = r2_score(y, y_pred)

print("Training Metrics")
print(f"MAE: {mae}")
print(f"RMSE: {rmse}")
print(f"R2: {r2}")

#%% Save model
joblib.dump(pipeline, "model/model.pkl") 
