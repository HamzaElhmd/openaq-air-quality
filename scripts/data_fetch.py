import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import time
from typing import List, Dict
import numpy as np

#%% Configuration
API_KEY = "3308619d87137f13edbb49da64c1d3218387819f5849e344375c499a06d4adbb"
BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY}

FRANCE_COUNTRY_ID = 22

AQI_BREAKPOINTS = {
    'pm25': [(0.0, 12.0, 0, 50), (12.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), 
             (55.5, 150.4, 151, 200), (150.5, 250.4, 201, 300), (250.5, 500.4, 301, 500)],
    'pm10': [(0, 54, 0, 50), (55, 154, 51, 100), (155, 254, 101, 150), 
             (255, 354, 151, 200), (355, 424, 201, 300), (425, 604, 301, 500)],
    'o3': [(0.000, 0.054, 0, 50), (0.055, 0.070, 51, 100), (0.071, 0.085, 101, 150), 
           (0.086, 0.105, 151, 200), (0.106, 0.200, 201, 300)],
    'no2': [(0, 53, 0, 50), (54, 100, 51, 100), (101, 360, 101, 150), 
            (361, 649, 151, 200), (650, 1249, 201, 300), (1250, 2049, 301, 500)],
    'so2': [(0, 35, 0, 50), (36, 75, 51, 100), (76, 185, 101, 150), 
            (186, 304, 151, 200), (305, 604, 201, 300), (605, 1004, 301, 500)],
    'co': [(0.0, 4.4, 0, 50), (4.5, 9.4, 51, 100), (9.5, 12.4, 101, 150), 
           (12.5, 15.4, 151, 200), (15.5, 30.4, 201, 300), (30.5, 50.4, 301, 500)]
}

def calculate_aqi(value, parameter):
    """Calculate AQI from pollutant concentration using EPA breakpoints"""
    if pd.isna(value) or value is None:
        return None
    
    param_lower = parameter.lower().replace('.', '').replace(' ', '')
    
    param_mapping = {
        'pm2.5': 'pm25',
        'pm25': 'pm25',
        'pm10': 'pm10',
        'o3': 'o3',
        'no2': 'no2',
        'so2': 'so2',
        'co': 'co'
    }
    
    param_key = param_mapping.get(param_lower)
    if not param_key or param_key not in AQI_BREAKPOINTS:
        return None
    
    breakpoints = AQI_BREAKPOINTS[param_key]
    
    for low_c, high_c, low_a, high_a in breakpoints:
        if low_c <= value <= high_c:
            aqi = ((high_a - low_a) / (high_c - low_c)) * (value - low_c) + low_a
            return round(aqi)
    
    if value > breakpoints[-1][1]:
        return 500
    
    return None

def get_france_locations() -> List[Dict]:
    """Fetch all locations (monitoring stations) in France"""
    all_locations = []
    page = 1
    limit = 100
    
    print("Fetching locations in France...")
    
    while True:
        params = {
            "countries_id": FRANCE_COUNTRY_ID,
            "limit": limit,
            "page": page
        }
        
        try:
            response = requests.get(
                f"{BASE_URL}/locations", 
                headers=HEADERS, 
                params=params, 
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                break
            
            all_locations.extend(results)
            meta = data.get("meta", {})
            found = meta.get("found", 0)
            
            print(f"  Page {page}: {len(results)} locations (Total: {len(all_locations)}/{found})")
            
            if len(all_locations) >= found:
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
    
    return all_locations

# ==========================================
# STEP 2: EXTRACT ALL SENSORS FROM LOCATIONS
# ==========================================
def extract_sensors(locations: List[Dict]) -> List[Dict]:
    """Extract sensor information from locations"""
    sensors = []
    
    for location in locations:
        location_id = location.get("id")
        location_name = location.get("name", "Unknown")
        locality = location.get("locality", "Unknown")
        coordinates = location.get("coordinates", {})
        
        for sensor in location.get("sensors", []):
            sensor_info = {
                "sensor_id": sensor.get("id"),
                "sensor_name": sensor.get("name"),
                "parameter_id": sensor.get("parameter", {}).get("id"),
                "parameter_name": sensor.get("parameter", {}).get("name"),
                "parameter_units": sensor.get("parameter", {}).get("units"),
                "location_id": location_id,
                "location_name": location_name,
                "locality": locality,
                "latitude": coordinates.get("latitude"),
                "longitude": coordinates.get("longitude"),
                "datetime_first": sensor.get("datetimeFirst", {}).get("utc"),
                "datetime_last": sensor.get("datetimeLast", {}).get("utc"),
            }
            sensors.append(sensor_info)
    
    print(f"\nTotal sensors found: {len(sensors)}")
    return sensors

# ==========================================
# STEP 3: GET HOURLY MEASUREMENTS (FIXED API RESPONSE PARSING)
# ==========================================
def get_sensor_hourly_averages(sensor_id: int) -> List[Dict]:
    """
    Fetch hourly averaged values with CORRECT API response parsing
    Based on OpenAQ API v3 documentation [^1^]
    """
    measurements = []
    page = 1
    limit = 1000
    
    while True:
        params = {
            "limit": limit,
            "page": page
        }
        
        try:
            response = requests.get(
                f"{BASE_URL}/sensors/{sensor_id}/hours",
                headers=HEADERS,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                break
            
            for hour in results:
                period = hour.get("period", {})
                datetime_from = period.get("datetimeFrom", {})
                datetime_to = period.get("datetimeTo", {})
                
                datetime_utc = datetime_to.get("utc") if datetime_to else None
                datetime_local = datetime_to.get("local") if datetime_to else None
                
                date_str = None
                if datetime_utc and isinstance(datetime_utc, str) and len(datetime_utc) >= 10:
                    try:
                        date_str = datetime_utc[:10]  # Extract YYYY-MM-DD
                    except:
                        date_str = None
                
                ml_record = {
                    "sensor_id": sensor_id,
                    "date": date_str,
                    "datetime_utc": datetime_utc,
                    "datetime_local": datetime_local,
                    "value_avg": hour.get("value"),
                    "parameter": hour.get("parameter", {}).get("name"),
                    "units": hour.get("parameter", {}).get("units"),
                    # Statistical features from summary
                    "min": hour.get("summary", {}).get("min"),
                    "max": hour.get("summary", {}).get("max"),
                    "q25": hour.get("summary", {}).get("q25"),
                    "median": hour.get("summary", {}).get("median"),
                    "q75": hour.get("summary", {}).get("q75"),
                    "std": hour.get("summary", {}).get("sd"),
                    # Coverage info
                    "expected_count": hour.get("coverage", {}).get("expectedCount"),
                    "observed_count": hour.get("coverage", {}).get("observedCount"),
                    "percent_complete": hour.get("coverage", {}).get("percentComplete"),
                }
                measurements.append(ml_record)
            
            meta = data.get("meta", {})
            found = meta.get("found", 0)
            
            if len(measurements) >= found or len(results) < limit:
                break
            
            page += 1
            time.sleep(0.2)
            
        except Exception as e:
            print(f"  Error fetching hourly data for sensor {sensor_id}: {e}")
            break
    
    return measurements

def create_ml_dataset(sensors: List[Dict]) -> pd.DataFrame:
    """
    Create a machine learning dataset from sensor data with AQI and 12h forecast target
    """
    all_data = []
    
    # Process ALL sensors (no limit)
    sensors_to_process = sensors
    
    print(f"\nFetching data for {len(sensors_to_process)} sensors...")
    print("This may take a while depending on the amount of data...")
    
    for i, sensor in enumerate(sensors_to_process):
        sensor_id = sensor["sensor_id"]
        param = sensor["parameter_name"]
        
        if i % 10 == 0:
            print(f"  [{i+1}/{len(sensors_to_process)}] Processing sensor {sensor_id} ({param})...")
        
        data = get_sensor_hourly_averages(sensor_id)
        
        # Add sensor metadata to each record
        for record in data:
            record.update({
                "location_id": sensor["location_id"],
                "location_name": sensor["location_name"],
                "locality": sensor["locality"],
                "latitude": sensor["latitude"],
                "longitude": sensor["longitude"],
            })
        
        all_data.extend(data)
        
        if (i + 1) % 10 == 0:
            print(f"    Progress: {i+1} sensors processed, {len(all_data)} total records")
    
    df = pd.DataFrame(all_data)
    print(f"\nInitial dataset created: {len(df)} records from {len(sensors_to_process)} sensors")
    
    return df

def add_aqi_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add AQI calculations and create the target variable aqi_after_12h
    """
    print("\nCalculating AQI values...")
    
    # Calculate current AQI for each row
    df['aqi'] = df.apply(lambda row: calculate_aqi(row['value_avg'], row['parameter']), axis=1)
    
    # Convert datetime_utc to pandas datetime for time-based operations
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], errors='coerce')
    
    # Check how many valid datetimes we have
    valid_datetimes = df['datetime_utc'].notna().sum()
    print(f"Records with valid datetime: {valid_datetimes} / {len(df)}")
    print(f"Records with valid AQI: {df['aqi'].notna().sum()} / {len(df)}")
    
    # Sort by sensor and datetime to ensure proper time ordering
    df = df.sort_values(['sensor_id', 'datetime_utc']).reset_index(drop=True)
    
    print("Computing AQI 12 hours ahead (aqi_after_12h)...")
    
    # Create the target variable: AQI 12 hours ahead for the same sensor
    df['target_time'] = df['datetime_utc'] + timedelta(hours=12)
    
    # For each sensor, find the AQI value at target_time
    aqi_targets = []
    
    for sensor_id in df['sensor_id'].unique():
        sensor_df = df[df['sensor_id'] == sensor_id].copy()
        
        if len(sensor_df) == 0:
            continue
            
        # Create a lookup dataframe with datetime as index
        sensor_df_indexed = sensor_df.set_index('datetime_utc')['aqi']
        
        # For each row, find AQI 12 hours later
        for idx, row in sensor_df.iterrows():
            target_time = row['target_time']
            
            if pd.isna(target_time):
                aqi_targets.append({
                    'index': idx,
                    'aqi_after_12h': None,
                    'actual_lag_hours': None
                })
                continue
            
            # Find the closest record at or after target time
            future_data = sensor_df_indexed.index[sensor_df_indexed.index >= target_time]
            
            if len(future_data) > 0:
                closest_time = future_data[0]
                time_diff_hours = (closest_time - row['datetime_utc']).total_seconds() / 3600
                
                # Only use if within 2 hours of target (allow some flexibility)
                if abs(time_diff_hours - 12) <= 2:
                    aqi_future = sensor_df_indexed.loc[closest_time]
                    aqi_targets.append({
                        'index': idx,
                        'aqi_after_12h': aqi_future,
                        'actual_lag_hours': round(time_diff_hours, 2)
                    })
                else:
                    aqi_targets.append({
                        'index': idx,
                        'aqi_after_12h': None,
                        'actual_lag_hours': None
                    })
            else:
                aqi_targets.append({
                    'index': idx,
                    'aqi_after_12h': None,
                    'actual_lag_hours': None
                })
    
    # Merge targets back to main dataframe
    if aqi_targets:
        targets_df = pd.DataFrame(aqi_targets).set_index('index')
        df['aqi_after_12h'] = targets_df['aqi_after_12h']
        df['actual_lag_hours'] = targets_df['actual_lag_hours']
    
    # Drop temporary column
    df = df.drop('target_time', axis=1, errors='ignore')
    
    return df

def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the dataset:
    1. Remove rows without datetime
    2. Remove rows without AQI
    3. Remove rows without aqi_after_12h (target variable missing)
    4. Remove duplicates
    5. Handle missing values in features
    """
    print("\n" + "="*60)
    print("CLEANING DATASET")
    print("="*60)
    
    initial_count = len(df)
    print(f"Initial records: {initial_count}")
    
    # 1. Remove rows without datetime_utc
    df_clean = df.dropna(subset=['datetime_utc']).copy()
    print(f"After removing rows without datetime: {len(df_clean)} (-{initial_count - len(df_clean)})")
    
    # 2. Remove rows without current AQI
    df_clean = df_clean.dropna(subset=['aqi']).copy()
    print(f"After removing rows without AQI: {len(df_clean)}")
    
    # 3. Remove rows without target variable (aqi_after_12h)
    df_clean = df_clean.dropna(subset=['aqi_after_12h']).copy()
    print(f"After removing rows without aqi_after_12h: {len(df_clean)}")
    
    # 4. Remove duplicates if any
    df_clean = df_clean.drop_duplicates(subset=['sensor_id', 'datetime_utc'])
    print(f"After removing duplicates: {len(df_clean)}")
    
    # 5. Remove rows with essential missing data
    essential_cols = ['value_avg', 'parameter']
    df_clean = df_clean.dropna(subset=essential_cols)
    print(f"After removing rows with missing essential data: {len(df_clean)}")
    
    # 6. Convert data types
    numeric_cols = ['value_avg', 'min', 'max', 'q25', 'median', 'q75', 'std', 
                   'expected_count', 'observed_count', 'percent_complete', 'latitude', 'longitude']
    
    for col in numeric_cols:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    # 7. Add time-based features for ML
    df_clean['hour'] = df_clean['datetime_utc'].dt.hour
    df_clean['day_of_week'] = df_clean['datetime_utc'].dt.dayofweek
    df_clean['month'] = df_clean['datetime_utc'].dt.month
    df_clean['year'] = df_clean['datetime_utc'].dt.year
    
    print(f"\nFinal cleaned dataset: {len(df_clean)} records")
    print(f"Date range: {df_clean['datetime_utc'].min()} to {df_clean['datetime_utc'].max()}")
    
    return df_clean

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    # 1. Get all locations in France
    locations = get_france_locations()
    
    # Save locations metadata
    with open("france_locations.json", "w") as f:
        json.dump(locations, f, indent=2)
    print(f"Saved {len(locations)} locations to france_locations.json")
    
    # 2. Extract sensors
    sensors = extract_sensors(locations)
    
    # Save sensors list
    sensors_df = pd.DataFrame(sensors)
    sensors_df.to_csv("france_sensors.csv", index=False)
    print(f"Saved {len(sensors)} sensors to france_sensors.csv")
    
    # Display sensor summary by parameter
    print("\nSensor count by parameter:")
    print(sensors_df["parameter_name"].value_counts())
    
    # 3. Create ML dataset - ALL sensors, no limit
    print("\n" + "="*60)
    print("Creating ML dataset with HOURLY averages (for 12h forecasting)...")
    print("="*60)
    
    ml_data = create_ml_dataset(sensors)
    
    # 4. Add AQI features and target variable
    ml_data = add_aqi_features(ml_data)
    
    # 5. Clean dataset (remove rows without target, etc.)
    ml_data_clean = clean_dataset(ml_data)
    
    # Save both versions
    ml_data.to_csv("france_ml_data_raw.csv", index=False)
    print("\nSaved raw data (with nulls) to france_ml_data_raw.csv")
    
    ml_data_clean.to_csv("france_ml_data.csv", index=False)
    print("Saved cleaned data to france_ml_data.csv")
    
    # 6. Summary statistics
    print("\n" + "="*60)
    print("FINAL DATASET SUMMARY")
    print("="*60)
    print(f"Total sensors: {len(sensors)}")
    print(f"Parameters available: {sensors_df['parameter_name'].unique().tolist()}")
    print(f"Total hourly records: {len(ml_data)}")
    print(f"Clean records (valid for ML): {len(ml_data_clean)}")
    print(f"Records removed: {len(ml_data) - len(ml_data_clean)}")
    
    if len(ml_data_clean) > 0:
        print(f"\nAQI statistics:")
        print(f"  Current AQI - Mean: {ml_data_clean['aqi'].mean():.1f}, Std: {ml_data_clean['aqi'].std():.1f}")
        print(f"  Target AQI (12h) - Mean: {ml_data_clean['aqi_after_12h'].mean():.1f}, Std: {ml_data_clean['aqi_after_12h'].std():.1f}")
        
        print(f"\nSample of ML data (first 5 rows):")
        print(ml_data_clean[['sensor_id', 'date', 'datetime_utc', 'parameter', 'value_avg', 'aqi', 'aqi_after_12h', 'actual_lag_hours']].head())
        
        print(f"\nSample of ML data (last 5 rows):")
        print(ml_data_clean[['sensor_id', 'date', 'datetime_utc', 'parameter', 'value_avg', 'aqi', 'aqi_after_12h', 'actual_lag_hours']].tail())
    
    return sensors_df, ml_data_clean

if __name__ == "__main__":
    sensors_df, ml_data = main()