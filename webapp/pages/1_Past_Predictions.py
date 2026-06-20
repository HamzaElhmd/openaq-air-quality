import streamlit as st
import requests as rq
import traceback
import pandas as pd
from utils import init_connection

init_connection()

st.title("Past Predictions")

st.date_input("Start Date", "today", key="startDate")

st.date_input("End Date", "today", key="endDate")

st.selectbox("Source", ["webapp", "scheduled predictions", "all"], key="source")

if st.button("Past Predictions"):
    if not st.session_state.get("connection_string"):
        st.error("Server not configured. Please check the connection settings.")
    else:
        try:
            response = rq.get(st.session_state["connection_string"] + "/api/past_predictions", params={"start_date": st.session_state.startDate,
                                                                               "end_date": st.session_state.endDate,
                                                                               "source": st.session_state.source})
            if response.status_code == 200:
                resp = response.json()
                predictions = resp["predictions"]
                if predictions:
                    st.success(f"Found {len(predictions)} prediction(s).")
                    st.dataframe(pd.DataFrame(predictions))
                else:
                    st.warning("No predictions found for the given filters.")
            else:
                st.error("Unable to fetch prediction history. Please try again later.")
        except Exception:
            st.error("Could not connect to the server. Please try again later.")
