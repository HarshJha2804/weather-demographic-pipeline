import json
from pathlib import Path

import pandas as pd
import requests

from google.cloud import bigquery
import pandas_gbq
import pyarrow
import google.auth


API_URL = "https://api.open-meteo.com/v1/forecast"

PROJECT_ID = "weather-demographic-bootcamp"
DATASET_ID = "global_weather_data"
TABLE_ID = "weather_pipeline_output"

DATA_DIR = Path("data")
INPUT_FILE = DATA_DIR / "population.csv"
WEATHER_FILE = DATA_DIR / "raw_weather.json"
OUTPUT_FILE = DATA_DIR / "combined_weather.csv"

WEATHER_FIELDS = (
    "temperature_2m,"
    "relative_humidity_2m,"
    "apparent_temperature,"
    "precipitation,"
    "wind_speed_10m"
)

NUMERIC_WEATHER_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
]


def collect_weather(cities):
    """Fetch current weather for cities and save the raw API response."""

    records = []
    batch_size = 20

    print(f"Found {len(cities)} valid cities.")

    for start in range(0, len(cities), batch_size):
        batch = cities.iloc[start:start + batch_size]

        params = {
            "latitude": ",".join(batch["Latitude"].astype(str)),
            "longitude": ",".join(batch["Longitude"].astype(str)),
            "current": WEATHER_FIELDS,
            "timezone": "auto",
        }

        print(f"Fetching cities {start + 1} to {start + len(batch)}...")

        response = requests.get(API_URL, params=params, timeout=60)
        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict):
            result = [result]

        if len(result) != len(batch):
            raise ValueError(
                f"Expected {len(batch)} results; received {len(result)}."
            )

        for (_, city), item in zip(batch.iterrows(), result):
            current = item.get("current", {})

            records.append({
                "City": str(city["City"]).strip(),
                "Country": str(city["Country"]).strip(),
                "Weather_Time": current.get("time"),
                "Timezone": item.get("timezone"),
                **current,
            })

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with WEATHER_FILE.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2, ensure_ascii=False)

    print(f"Raw weather saved to: {WEATHER_FILE}")

    return pd.DataFrame(records)


def upload_to_bigquery(dataframe):
    """Upload the cleaned Pandas DataFrame to BigQuery."""

    if dataframe.empty:
        raise ValueError("Cannot upload an empty DataFrame.")

    print("\nAuthenticating with Google Cloud...")

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # Confirm the BigQuery client can be initialized.
    client = bigquery.Client(
        project=PROJECT_ID,
        credentials=credentials,
    )

    # Confirm that the destination dataset exists and is accessible.
    client.get_dataset(f"{PROJECT_ID}.{DATASET_ID}")

    destination = f"{DATASET_ID}.{TABLE_ID}"

    print(f"Uploading {len(dataframe)} rows to {PROJECT_ID}.{destination}...")

    pandas_gbq.to_gbq(
        dataframe=dataframe,
        destination_table=destination,
        project_id=PROJECT_ID,
        credentials=credentials,
        if_exists="replace",
        progress_bar=False,
    )

    print("BigQuery upload completed successfully!")
    print(f"Destination: {PROJECT_ID}.{destination}")
    print(f"Rows uploaded: {len(dataframe)}")


def main():
    # 1. Load population data
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find {INPUT_FILE}")

    demographics = pd.read_csv(INPUT_FILE)

    required = {"City", "Country", "Latitude", "Longitude"}
    missing = required - set(demographics.columns)

    if missing:
        raise ValueError(f"Missing population columns: {sorted(missing)}")

    original_count = len(demographics)

    # 2. Clean required fields and coordinates
    demographics["City"] = (
        demographics["City"].astype("string").str.strip()
    )
    demographics["Country"] = (
        demographics["Country"].astype("string").str.strip()
    )

    demographics["Latitude"] = pd.to_numeric(
        demographics["Latitude"], errors="coerce"
    )
    demographics["Longitude"] = pd.to_numeric(
        demographics["Longitude"], errors="coerce"
    )

    demographics.dropna(
        subset=["City", "Country", "Latitude", "Longitude"],
        inplace=True,
    )

    demographics = demographics[
        demographics["City"].ne("")
        & demographics["Country"].ne("")
        & demographics["Latitude"].between(-90, 90)
        & demographics["Longitude"].between(-180, 180)
    ].copy()

    if demographics.empty:
        raise ValueError("No valid city records remain after cleaning.")

    if "Population" in demographics.columns:
        demographics["Population"] = pd.to_numeric(
            demographics["Population"], errors="coerce"
        ).astype("Int64")

        demographics.loc[
            demographics["Population"] < 0, "Population"
        ] = pd.NA

    # 3. Fetch current weather
    weather = collect_weather(demographics)

    # 4. Standardize matching keys
    for frame in (demographics, weather):
        frame["_city_key"] = (
            frame["City"].str.casefold().str.strip()
        )
        frame["_country_key"] = (
            frame["Country"].str.casefold().str.strip()
        )

    # 5. Clean weather measurement types
    for column in NUMERIC_WEATHER_FIELDS:
        if column in weather.columns:
            weather[column] = pd.to_numeric(
                weather[column], errors="coerce"
            ).astype("float64")

    weather_for_merge = weather.drop(
        columns=["City", "Country"],
        errors="ignore",
    )

    # 6. Merge population and weather using Pandas
    combined = demographics.merge(
        weather_for_merge,
        on=["_city_key", "_country_key"],
        how="left",
        validate="one_to_one",
    )

    combined.drop(
        columns=["_city_key", "_country_key"],
        inplace=True,
    )

    # 7. Remove duplicate city-country rows
    combined.drop_duplicates(
        subset=["City", "Country"],
        keep="first",
        inplace=True,
    )

    # 8. Categorize temperature
    if "temperature_2m" in combined.columns:
        combined["Temperature_Category"] = pd.cut(
            combined["temperature_2m"],
            bins=[float("-inf"), 10, 25, float("inf")],
            labels=["Cold", "Mild", "Hot"],
            right=False,
        ).astype("category")

    # 9. Report missing values
    print("\nMissing values by column:")
    print(combined.isna().sum().to_string())

    # 10. Save the cleaned and transformed dataset
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_FILE, index=False)

    matched = combined["Weather_Time"].notna().sum()

    print("\n--- Final Pipeline Summary ---")
    print(f"Population rows originally loaded: {original_count}")
    print(f"Valid population rows: {len(demographics)}")
    print(f"Weather records fetched: {len(weather)}")
    print(f"Final merged records: {len(combined)}")
    print(f"Records matched with weather: {matched}")
    print(f"\nFinal data types:\n{combined.dtypes.to_string()}")
    print(f"\nFinal dataset saved to: {OUTPUT_FILE}")

    # 11. Upload the SAME cleaned DataFrame to BigQuery
    upload_to_bigquery(combined)


if __name__ == "__main__":
    main()