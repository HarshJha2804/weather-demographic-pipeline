import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
DEMOGRAPHICS_FILE = DATA_DIR / "population.csv"
WEATHER_FILE = DATA_DIR / "raw_weather.json"
OUTPUT_FILE = DATA_DIR / "combined_weather.csv"


def main():
    # 1. Load demographic and weather data
    demographics = pd.read_csv(DEMOGRAPHICS_FILE)

    with WEATHER_FILE.open("r", encoding="utf-8") as file:
        weather_records = json.load(file)

    # 2. Convert weather JSON into a DataFrame
    weather_rows = []

    for record in weather_records:
        row = {
            "City": record["city"],
            "Country": record["country"],
            "Latitude": record["latitude"],
            "Longitude": record["longitude"],
            "Weather_Time": record.get("weather_time"),
            "Timezone": record.get("timezone"),
        }
        row.update(record.get("weather", {}))
        weather_rows.append(row)

    weather = pd.DataFrame(weather_rows)

    # 3. Clean city and country names for reliable matching
    for df in (demographics, weather):
        df["City"] = df["City"].astype("string").str.strip()
        df["Country"] = df["Country"].astype("string").str.strip()

        df["_city_key"] = df["City"].str.casefold()
        df["_country_key"] = df["Country"].str.casefold()

    # 4. Convert numeric columns safely
    if "Population" in demographics.columns:
        demographics["Population"] = pd.to_numeric(
            demographics["Population"], errors="coerce"
        ).astype("Int64")

    for column in [
        "Latitude",
        "Longitude",
    ]:
        if column in demographics.columns:
            demographics[column] = pd.to_numeric(
                demographics[column], errors="coerce"
            ).astype("float64")

    numeric_weather_columns = [
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "wind_speed_10m",
    ]

    for column in numeric_weather_columns:
        if column in weather.columns:
            weather[column] = pd.to_numeric(
                weather[column], errors="coerce"
            ).astype("float64")

    # 5. Merge demographic and weather data using Pandas
    weather_for_merge = weather.drop(
        columns=["City", "Country", "Latitude", "Longitude"],
        errors="ignore",
    )

    combined = demographics.merge(
        weather_for_merge,
        on=["_city_key", "_country_key"],
        how="left",
        validate="many_to_one",
    )

    combined.drop(
        columns=["_city_key", "_country_key"],
        inplace=True,
    )

    # 6. Remove duplicate city-country records
    combined.drop_duplicates(
        subset=["City", "Country"],
        keep="first",
        inplace=True,
    )

    # 7. Normalize temperature into categories
    if "temperature_2m" in combined.columns:
        combined["Temperature_Category"] = pd.cut(
            combined["temperature_2m"],
            bins=[float("-inf"), 10, 25, float("inf")],
            labels=["Cold", "Mild", "Hot"],
            right=False,
        ).astype("category")

    # 8. Report missing values without inventing replacement data
    print("\nMissing values before saving:")
    print(combined.isna().sum().to_string())

    # 9. Save the cleaned, merged dataset
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_FILE, index=False)

    matched = combined["Weather_Time"].notna().sum()

    print("\n--- Pipeline Transformation Summary ---")
    print(f"Demographic records loaded: {len(demographics)}")
    print(f"Weather records loaded: {len(weather)}")
    print(f"Final combined records: {len(combined)}")
    print(f"Records matched with weather: {matched}")
    print(f"\nFinal data types:\n{combined.dtypes.to_string()}")
    print(f"\nCleaned CSV saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()