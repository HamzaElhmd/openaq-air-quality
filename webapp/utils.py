import os
import json
import streamlit as st


def init_connection():
    """Ensure connection_string is set in session_state.
    Safe to call multiple times — skips if already initialised.
    """
    if st.session_state.get("connection_string"):
        return

    server_config_path = os.environ.get("SERVER_CONFIG_PATH", "config/server.json")
    server_config = None

    try:
        if os.path.exists(server_config_path):
            with open(server_config_path, "r", encoding="utf-8") as f:
                server_config = json.load(f)
                st.session_state["server_config"] = server_config
    except Exception:
        pass

    if server_config:
        host = server_config.get("host", "api")
        port = server_config.get("port", 8000)
    else:
        host = os.environ.get("API_HOST", "api")
        port = os.environ.get("API_PORT", "8000")

    st.session_state["connection_string"] = f"http://{host}:{port}"
