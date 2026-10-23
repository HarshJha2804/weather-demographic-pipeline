from pathlib import Path

import pandas as pd
import streamlit as st

DATA_FILE = Path("data/combined_weather.csv")

st.set_page_config(
    page_title="Weather and Demographics",
    page_icon="🌦️",
    layout="wide",
)

st.title("🌦️ Weather and Demographics Dashboard")
st.write("Current weather observations alongside city population data.")

if not DATA_FILE.exists():
    st.warning(
        "Combined data not found. Run the pipeline first: "
        "python src/pipeline.py"
    )
    st.stop()

df = pd.read_csv(DATA_FILE)

st.subheader("Dataset overview")

col1, col2, col3 = st.columns(3)
col1.metric("City records", len(df))
col2.metric("Countries", df["Country"].nunique())
col3.metric(
    "Weather records",
    int(df["Weather_Time"].notna().sum()),
)

if "temperature_2m" in df.columns:
    st.subheader("Temperature by city")
    chart_data = df[["City", "temperature_2m"]].dropna()
    st.bar_chart(chart_data.set_index("City"))

if "Population" in df.columns and "temperature_2m" in df.columns:
    st.subheader("Population and temperature")
    st.scatter_chart(
        df[["Population", "temperature_2m"]].dropna(),
        x="Population",
        y="temperature_2m",
    )

st.subheader("Combined data")
st.dataframe(df, use_container_width=True)

st.download_button(
    "Download combined CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name="combined_weather.csv",
    mime="text/csv",
)