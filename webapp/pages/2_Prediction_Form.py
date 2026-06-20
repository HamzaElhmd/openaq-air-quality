import streamlit as st
from datetime import datetime
import pandas as pd
import requests as rq
import traceback
from utils import init_connection

init_connection()

st.title("Prediction Form")

input_method = st.radio(
    "How would you like to provide the data?",
    ("Manual Entry (Single Prediction)", "Upload CSV (Batch Prediction)"),
    horizontal=True
)

predictOneEndPoint = "/api/predictOne"
predictManyEndPoint = "/api/predictMany"

st.divider()

if input_method == "Manual Entry (Single Prediction)":
    with st.form("featuresForm", True):
        st.subheader("📍 Location")
        col1, col2 = st.columns(2)

        with col1:
            location_name = st.text_input("Location Name")
            actual_lag_hours = st.number_input("Actual Lag Hours", step=0.1, format="%.1f")

        with col2:
            latitude = st.number_input("Latitude", format="%.6f")
            longitude = st.number_input("Longitude", format="%.6f")

        st.divider()

        st.subheader("📊 Sensor Metrics")
        c1, c2, c3 = st.columns(3)

        with c1:
            value_avg = st.number_input("Avg Value", format="%.2f")
            min_val = st.number_input("Min", format="%.2f")
            max_val = st.number_input("Max", format="%.2f")

        with c2:
            q25 = st.number_input("Q25", format="%.2f")
            median = st.number_input("Median", format="%.2f")
            q75 = st.number_input("Q75", format="%.2f")

        with c3:
            aqi = st.number_input("AQI", format="%.2f")
            parameter = st.text_input("Parameter (e.g. pm25)")

        st.divider()

        st.subheader("🕐 Temporal")
        t1, t2, t3, t4 = st.columns(4)

        with t1:
            hour = st.number_input("Hour (0-23)", min_value=0, max_value=23, step=1)
        with t2:
            day_of_week = st.number_input("Day of Week (0-6)", min_value=0, max_value=6, step=1)
        with t3:
            month = st.number_input("Month (1-12)", min_value=1, max_value=12, step=1)
        with t4:
            year = st.number_input("Year", min_value=2000, max_value=2100, step=1, value=datetime.now().year)

        submitted = st.form_submit_button("Submit Data")

        if submitted:
            entry = {
                "location": {
                    "location_name": location_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "actual_lag_hours": actual_lag_hours,
                },
                "sensor_metrics": {
                    "value_avg": value_avg,
                    "min": min_val,
                    "max": max_val,
                    "q25": q25,
                    "median": median,
                    "q75": q75,
                    "aqi": aqi,
                    "parameter": parameter,
                },
                "temporal": {
                    "hour": hour,
                    "day_of_week": day_of_week,
                    "month": month,
                    "year": year,
                },
                "source": "webapp",
            }

            if not st.session_state.get("connection_string"):
                st.error("Server not configured. Please check the connection settings.")
                st.stop()
            try:
                response = rq.post(st.session_state["connection_string"] + predictOneEndPoint, 
                        json=entry)

                if response.status_code == 200:
                    st.success("Prediction submitted successfully!")
                    predictions_df = pd.DataFrame([response.json()])
                    st.dataframe(predictions_df)
                else:
                    st.error("Failed to submit prediction. Please try again later.")

            except Exception:
                st.error("Could not connect to the server. Please try again later.")

elif input_method == "Upload CSV (Batch Prediction)":
    st.info("Ensure your CSV contains columns: location_name, latitude, longitude, actual_lag_hours, value_avg, min, max, q25, median, q75, aqi, parameter, hour, day_of_week, month, year")

    uploaded_file = st.file_uploader("Choose a CSV file", type="csv", key="uploadButton")

    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)

        st.write("### Data Preview")
        st.dataframe(df.head())

        if st.button("Process CSV for Prediction"):
            if not st.session_state.get("connection_string"):
                st.error("Server not configured. Please check the connection settings.")
                st.stop()
            try:
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
                        "source": "webapp"
                    }
                    payload.append(prediction_request)

                response = rq.post(
                    st.session_state["connection_string"] + predictManyEndPoint,
                    json=payload
                )

                if response.status_code == 200:
                    st.success("Batch prediction completed successfully!")
                    predictions = response.json()["predictions"]
                    st.dataframe(pd.DataFrame(predictions))
                else:
                    st.error("Failed to process CSV. Please try again later.")
            except Exception:
                st.error("Could not connect to the server. Please try again later.")
