import streamlit as st
from utils import init_connection

st.set_page_config(page_title="OpenAq")

init_connection()

st.write("# Welcome to OpenAq")
