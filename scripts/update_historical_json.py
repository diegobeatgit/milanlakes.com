#!/usr/bin/env python3
"""
update_historical_json.py
Runs weekly via GitHub Actions.
Generates data/historical.json with:
  - crowd_profiles (monthly, 0-100) per lake
  - traffic_monthly (A9/SS36 Saturday index)
  - water_temp (monthly °C) per lake
  - social_trends (monthly proxy) per lake

These values are updated ANNUALLY (each January) based on the previous year.
The script outputs the current in-use values to JSON so the frontend
can fetch them instead of having them hardcoded.

To update: edit CROWD, TRAFFIC, WATER_TEMP, SOCIAL at the top of this file
once a year with new observed data. The GitHub Action will then commit
the updated historical.json automatically on next Thursday run.
"""

import json
import datetime
import os

# ─────────────────────────────────────────────────────────────
# HISTORICAL DATA — Update once a year (January)
# Source: ARPA Lombardia + field observations
# Last updated: 2025 season data
# ─────────────────────────────────────────────────────────────
DATA_VERSION = "2025"  # Change to "2026" when updating next year

CROWD = {
    "como":    [22,26,36,56,70,86,96,98,82,62,32,42],
    "maggiore":[20,25,42,65,78,88,92,95,82,62,28,38],
    "garda":   [18,22,38,65,78,90,98,99,86,65,28,35],
    "iseo":    [18,22,38,58,72,82,88,90,75,58,28,32],
    "orta":    [14,18,32,52,64,76,82,84,70,54,22,28],
    "monate":  [8, 10,18,32,45,55,62,65,52,35,14,12],
    "pusiano": [10,12,26,46,66,82,96,98,72,46,18,16],
    "segrino": [10,12,25,45,65,80,95,98,70,45,18,15],
    "annone":  [8, 10,20,38,55,68,78,80,65,42,15,12],
    "alserio": [8,  9,18,35,50,65,72,75,60,38,14,10],
    "lugano":  [18,22,35,55,68,80,88,90,76,58,25,30],
    "varese":  [20,22,30,45,55,65,68,66,58,46,24,28],
}

# A9 + SS36 Saturday morning congestion index [jan-dec] (0-100)
# Source: Autostrade per l'Italia traffic reports + ANAS bulletins
TRAFFIC_MONTHLY = [25,30,45,65,70,80,85,72,75,60,35,50]

# Water temperature °C [jan-dec] — ARPA Lombardia buoy data
WATER_TEMP = {
    "como":    [6, 6, 8,11,16,21,24,24,20,15,10, 7],
    "maggiore":[6, 6, 8,12,17,22,25,25,21,15,10, 7],
    "garda":   [8, 8,10,14,19,23,26,26,22,17,12, 9],
    "iseo":    [5, 5, 7,11,16,21,24,24,19,14, 9, 6],
    "orta":    [5, 5, 7,10,15,20,23,23,18,13, 8, 5],
    "monate":  [5, 5, 7,10,15,20,23,23,18,13, 8, 5],
    "pusiano": [5, 5, 7,10,14,19,22,22,17,12, 7, 5],
    "segrino": [5, 5, 7,10,15,20,23,23,18,13, 8, 5],
    "annone":  [5, 5, 7,10,14,19,22,22,17,12, 7, 5],
    "alserio": [5, 5, 6, 9,13,18,21,21,16,12, 7, 5],
    "lugano":  [7, 7, 9,12,16,20,23,23,19,14, 9, 7],
    "varese":  [5, 5, 7,10,14,18,21,21,16,11, 7, 5],
}

# Social trend proxy [jan-dec] — Google Trends index + Instagram seasonal patterns
SOCIAL = {
    "como":    [20,22,35,55,68,80,90,88,75,58,28,38],
    "maggiore":[18,20,32,52,62,74,82,80,68,52,24,32],
    "garda":   [18,22,35,60,72,85,92,90,78,60,26,32],
    "iseo":    [15,18,28,45,58,65,70,68,60,48,20,22],
    "orta":    [12,15,25,40,52,60,65,62,55,42,18,20],
    "monate":  [ 8,10,15,25,35,42,46,44,38,28,12,10],
    "pusiano": [ 8,10,18,32,45,55,60,58,48,35,14,12],
    "segrino": [ 7, 8,14,28,38,48,55,52,42,30,12,10],
    "annone":  [ 6, 7,12,22,32,40,45,42,36,26,10, 8],
    "alserio": [ 5, 6,10,18,28,35,40,38,30,22, 8, 6],
    "lugano":  [15,18,28,45,55,65,72,70,60,46,20,28],
    "varese":  [12,14,20,32,42,50,52,50,44,34,16,18],
}

# ARPA Lombardia meteo monthly averages (Prealpi zone)
METEO_STATS = {
    "Jan":{"sun_h":3.2,"rain_days":7,"temp_max":5,"temp_min":-2},
    "Feb":{"sun_h":4.5,"rain_days":6,"temp_max":8,"temp_min":-1},
    "Mar":{"sun_h":5.8,"rain_days":8,"temp_max":13,"temp_min":4},
    "Apr":{"sun_h":6.2,"rain_days":10,"temp_max":17,"temp_min":7},
    "May":{"sun_h":7.1,"rain_days":11,"temp_max":22,"temp_min":12},
    "Jun":{"sun_h":8.5,"rain_days":9,"temp_max":27,"temp_min":16},
    "Jul":{"sun_h":9.2,"rain_days":7,"temp_max":30,"temp_min":19},
    "Aug":{"sun_h":8.8,"rain_days":8,"temp_max":29,"temp_min":18},
    "Sep":{"sun_h":6.5,"rain_days":9,"temp_max":24,"temp_min":14},
    "Oct":{"sun_h":5.1,"rain_days":8,"temp_max":17,"temp_min":9},
    "Nov":{"sun_h":3.8,"rain_days":9,"temp_max":10,"temp_min":4},
    "Dec":{"sun_h":3.0,"rain_days":7,"temp_max":6,"temp_min":0},
}


def update_historical():
    today = datetime.date.today()

    output = {
        "generated_at":   today.isoformat(),
        "data_version":   DATA_VERSION,
        "next_update":    f"{today.year + 1}-01-01",
        "source":         "ARPA Lombardia + field observations 2019-2024",
        "crowd_profiles": CROWD,
        "traffic_monthly":TRAFFIC_MONTHLY,
        "water_temp":     WATER_TEMP,
        "social_trends":  SOCIAL,
        "meteo_stats":    METEO_STATS,
        "note": (
            "Update CROWD, TRAFFIC_MONTHLY, WATER_TEMP and SOCIAL in "
            "scripts/update_historical_json.py every January with previous year data. "
            "Then change DATA_VERSION to the new year."
        )
    }

    os.makedirs("data", exist_ok=True)
    out_path = "data/historical.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[Historical] Written to {out_path} (version: {DATA_VERSION})")
    return output


if __name__ == "__main__":
    update_historical()
