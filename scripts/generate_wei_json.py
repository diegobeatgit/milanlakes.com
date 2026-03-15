#!/usr/bin/env python3
"""
generate_wei_json.py
Runs every Thursday via GitHub Actions.
Fetches live weather from Open-Meteo, computes WEI scores for all 12 lakes,
writes data/wei_latest.json (read by the frontend).

Output format (data/wei_latest.json):
{
  "generated_at": "2026-03-20T06:00:00Z",
  "weekend":      "2026-03-21",
  "source":       "live|fallback",
  "formula":      "weather*0.30 + travel*0.20 + crowd*0.15 + events*0.15 + water*0.10 + social*0.10",
  "ranking": [
    {
      "rank": 1,
      "id": "monate",
      "name": "Lake Monate",
      "name_it": "Lago di Monate",
      "score": 74,
      "travel_min": 50,
      "distance_km": 58,
      "scores": { "weather":82, "travel":88, "crowd":78, "events":35, "water":65, "social":42 },
      "labels": { "weather":"good", "travel":"excellent", "crowd":"low", "events":"fair" }
    }, ...
  ]
}
"""

import json
import math
import datetime
import os
import sys

# Try requests, fall back to urllib
try:
    import requests
    def fetch_url(url, timeout=10):
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
except ImportError:
    import urllib.request, urllib.error
    def fetch_url(url, timeout=10):
        req = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(req.read().decode())

# ─────────────────────────────────────────────────────────────
# DESTINATIONS
# ─────────────────────────────────────────────────────────────
LAKES = [
    {"id":"como",     "name":"Lake Como",    "name_it":"Lago di Como",    "lat":46.00,"lng":9.26,  "travel_min":40, "dist_km":48,  "traffic_base":22},
    {"id":"maggiore", "name":"Lake Maggiore","name_it":"Lago Maggiore",   "lat":45.85,"lng":8.53,  "travel_min":55, "dist_km":72,  "traffic_base":18},
    {"id":"garda",    "name":"Lake Garda",   "name_it":"Lago di Garda",   "lat":45.60,"lng":10.70, "travel_min":90, "dist_km":110, "traffic_base":14},
    {"id":"iseo",     "name":"Lake Iseo",    "name_it":"Lago d'Iseo",     "lat":45.72,"lng":10.07, "travel_min":60, "dist_km":70,  "traffic_base":16},
    {"id":"orta",     "name":"Lake Orta",    "name_it":"Lago d'Orta",     "lat":45.81,"lng":8.41,  "travel_min":65, "dist_km":75,  "traffic_base":12},
    {"id":"monate",   "name":"Lake Monate",  "name_it":"Lago di Monate",  "lat":45.78,"lng":8.65,  "travel_min":50, "dist_km":58,  "traffic_base":8 },
    {"id":"pusiano",  "name":"Lake Pusiano", "name_it":"Lago di Pusiano", "lat":45.80,"lng":9.29,  "travel_min":35, "dist_km":42,  "traffic_base":18},
    {"id":"segrino",  "name":"Lake Segrino", "name_it":"Lago di Segrino", "lat":45.82,"lng":9.25,  "travel_min":40, "dist_km":45,  "traffic_base":16},
    {"id":"annone",   "name":"Lake Annone",  "name_it":"Lago di Annone",  "lat":45.83,"lng":9.33,  "travel_min":42, "dist_km":48,  "traffic_base":14},
    {"id":"alserio",  "name":"Lake Alserio", "name_it":"Lago di Alserio", "lat":45.76,"lng":9.18,  "travel_min":38, "dist_km":43,  "traffic_base":12},
    {"id":"lugano",   "name":"Lake Lugano",  "name_it":"Lago di Lugano",  "lat":45.99,"lng":8.95,  "travel_min":75, "dist_km":88,  "traffic_base":16},
    {"id":"varese",   "name":"Lake Varese",  "name_it":"Lago di Varese",  "lat":45.82,"lng":8.83,  "travel_min":45, "dist_km":55,  "traffic_base":14},
]

# ─────────────────────────────────────────────────────────────
# HISTORICAL DATA MODELS (5-year averages 2019–2024)
# ─────────────────────────────────────────────────────────────
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

EVENTS_PROFILE = {
    "como":    [10,10,25,40,50,65,55,45,60,40,20,35],
    "maggiore":[10,15,30,50,55,72,65,55,45,30,20,35],
    "garda":   [10,15,25,42,55,70,80,72,58,38,18,22],
    "iseo":    [8, 10,18,35,42,35,38,28,60,42,12,14],
    "orta":    [8, 10,20,35,42,50,45,38,42,30,15,18],
    "monate":  [5,  5,12,20,28,35,35,30,28,18, 8, 8],
    "pusiano": [4,  5,10,18,25,28,25,22,22,18, 8, 8],
    "segrino": [3,  4, 8,15,20,22,20,18,18,14, 6, 6],
    "annone":  [3,  4, 8,14,18,20,18,16,16,12, 5, 5],
    "alserio": [3,  3, 6,10,15,16,15,12,12,10, 4, 4],
    "lugano":  [10,12,25,42,52,65,60,55,50,38,18,28],
    "varese":  [5,  6,10,18,24,28,25,22,22,16, 8,10],
}

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

# A9/SS36 Saturday morning traffic index [jan-dec] (0-100)
TRAFFIC_MONTHLY = [25,30,45,65,70,80,85,72,75,60,35,50]

SWIM_SEASON = {
    "como":(5,10),"maggiore":(6,9),"garda":(6,9),"iseo":(6,9),
    "orta":(6,9),"monate":(6,9),"pusiano":(5,9),"segrino":(5,9),
    "annone":(5,9),"alserio":(5,9),"lugano":(6,9),"varese":(6,9),
}

WATER_QUALITY_BONUS = {
    "monate":12,"orta":10,"segrino":10,"annone":8,"alserio":10,
    "pusiano":8,"varese":5,"lugano":6,"iseo":5,"como":0,"maggiore":3,"garda":-2,
}

# ─────────────────────────────────────────────────────────────
# WEATHER FETCHER
# ─────────────────────────────────────────────────────────────
def fetch_weekend_weather(lat, lng):
    """Fetch Open-Meteo forecast, return sat+sun averaged metrics."""
    today = datetime.date.today()
    dow = today.weekday()  # 0=Mon
    days_to_sat = (5 - dow) % 7 or 7
    sat = today + datetime.timedelta(days=days_to_sat)
    sun = sat + datetime.timedelta(days=1)

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        f"&daily=weathercode,temperature_2m_max,precipitation_probability_max"
        f",windspeed_10m_max,sunshine_duration"
        f"&timezone=Europe%2FRome&forecast_days=10"
    )
    try:
        data = fetch_url(url, timeout=8)
        daily = data["daily"]
    except Exception as e:
        print(f"    [weather] fetch failed: {e}")
        return None

    sat_entry = sun_entry = None
    for i, ds in enumerate(daily["time"]):
        d = datetime.date.fromisoformat(ds)
        entry = {
            "wcode":  daily["weathercode"][i] or 0,
            "tmax":   daily["temperature_2m_max"][i] or 15.0,
            "precip": daily["precipitation_probability_max"][i] or 0,
            "wind":   (daily.get("windspeed_10m_max") or [10]*10)[i] or 10,
            "sun_h":  ((daily.get("sunshine_duration") or [0]*10)[i] or 0) / 3600,
        }
        if d == sat and sat_entry is None:
            sat_entry = entry
        elif d == sun and sun_entry is None:
            sun_entry = entry

    if not sat_entry:
        return None

    # Average sat + sun
    sun_entry = sun_entry or sat_entry
    avg = {k: (sat_entry[k] + sun_entry[k]) / 2 for k in sat_entry}
    return avg


def score_weather(avg, mo):
    if avg is None:
        return [45,50,55,60,65,70,75,72,65,55,45,42][mo]

    p_score = max(0, 100 - avg["precip"] * 1.6)
    w = avg["wcode"]
    w_score = 100 if w<=1 else 80 if w<=3 else 60 if w<=45 else 40 if w<=61 else 20
    t = avg["tmax"]
    t_score = 20 if t<5 else 40 if t<10 else 60 if t<15 else 100 if t<30 else 75
    wind_pen = max(0, (avg["wind"] - 15) * 1.5) if avg["wind"] > 15 else 0
    sun_bonus = min(15, avg["sun_h"] * 1.5)
    raw = p_score*0.45 + w_score*0.35 + t_score*0.20 - wind_pen + sun_bonus
    return int(max(0, min(100, round(raw))))


# ─────────────────────────────────────────────────────────────
# SCORE COMPONENTS
# ─────────────────────────────────────────────────────────────
def score_travel(lake, mo, is_weekend):
    base = max(10, min(95, round(100 - (lake["travel_min"] - 30) * 0.75)))
    if is_weekend:
        penalty = round(TRAFFIC_MONTHLY[mo] * lake["traffic_base"] / 100 * 0.35)
    else:
        penalty = 0
    return int(max(5, min(100, base - penalty)))


def score_crowd(lake_id, mo, is_weekend, wx):
    base = CROWD[lake_id][mo]
    wknd_boost = 15 if is_weekend else 0
    wx_boost = round((wx - 50) * 0.15) if wx > 50 else 0
    crowd_idx = min(100, base + wknd_boost + wx_boost)
    return int(max(5, round(100 - crowd_idx * 0.85)))


def score_events(lake_id, mo):
    return int(min(100, EVENTS_PROFILE[lake_id][mo]))


def score_water(lake_id, mo):
    temp = WATER_TEMP[lake_id][mo]
    sm_start, sm_end = SWIM_SEASON[lake_id]
    in_season = sm_start <= (mo+1) <= sm_end
    if not in_season:
        return max(10, min(40, round(temp * 3)))
    if temp < 16:   t_score = 30
    elif temp < 19: t_score = 55
    elif temp < 22: t_score = 72
    elif temp < 28: t_score = 95
    else:           t_score = 80
    bonus = WATER_QUALITY_BONUS.get(lake_id, 0)
    return int(max(5, min(100, t_score + bonus)))


def score_social(lake_id, mo):
    return int(SOCIAL[lake_id][mo])


def label(score):
    if score >= 75: return "excellent"
    if score >= 55: return "good"
    if score >= 40: return "fair"
    return "poor"


def crowd_label(crowd_score):
    inverted = 100 - round(crowd_score / 0.85)
    if inverted >= 72: return "high"
    if inverted >= 42: return "moderate"
    return "low"


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def compute_all():
    today = datetime.date.today()
    mo = today.month - 1
    dow = today.weekday()
    is_weekend = dow >= 5

    days_to_sat = (5 - dow) % 7 or 7
    sat_date = today + datetime.timedelta(days=days_to_sat)
    sun_date = sat_date + datetime.timedelta(days=1)
    weekend_str = sat_date.isoformat()

    force_fallback = os.environ.get("WEI_FORCE_FALLBACK", "false").lower() == "true"

    results = []
    source = "fallback"

    print(f"[WEI] Computing for weekend {weekend_str} (month idx={mo})")
    print(f"[WEI] force_fallback={force_fallback}")

    # Fetch weather once for the Prealpi region centre (all lakes share similar forecast)
    # Then apply slight per-lake corrections
    print("[WEI] Fetching weather (Prealpi centre 45.81, 9.22)...")
    base_wx = None if force_fallback else fetch_weekend_weather(45.81, 9.22)
    if base_wx:
        source = "live"
        print(f"[WEI] Weather live: tmax={base_wx['tmax']:.1f}°C  precip={base_wx['precip']}%  wind={base_wx['wind']:.0f}km/h")
    else:
        print("[WEI] Weather unavailable — using historical fallback")

    for lake in LAKES:
        wx_score = score_weather(base_wx, mo)
        # Small correction for Garda (more exposed) and Lugano (slightly different microclimate)
        if lake["id"] == "garda":    wx_score = max(0, wx_score - 4)
        if lake["id"] == "maggiore": wx_score = max(0, wx_score - 2)

        ts = score_travel(lake, mo, is_weekend)
        cs = score_crowd(lake["id"], mo, is_weekend, wx_score)
        es = score_events(lake["id"], mo)
        ws = score_water(lake["id"], mo)
        ss = score_social(lake["id"], mo)

        final = round(
            wx_score * 0.30 +
            ts       * 0.20 +
            cs       * 0.15 +
            es       * 0.15 +
            ws       * 0.10 +
            ss       * 0.10
        )
        final = int(max(10, min(99, final)))

        results.append({
            "id":          lake["id"],
            "name":        lake["name"],
            "name_it":     lake["name_it"],
            "rank":        0,
            "travel_min":  lake["travel_min"],
            "distance_km": lake["dist_km"],
            "score":       final,
            "scores": {
                "weather": wx_score,
                "travel":  ts,
                "crowd":   cs,
                "events":  es,
                "water":   ws,
                "social":  ss,
            },
            "labels": {
                "weather": label(wx_score),
                "travel":  label(ts),
                "crowd":   crowd_label(cs),
                "events":  label(es),
                "water":   label(ws),
            }
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    output = {
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weekend":      weekend_str,
        "source":       source,
        "formula":      "weather*0.30 + travel*0.20 + crowd*0.15 + events*0.15 + water*0.10 + social*0.10",
        "month_index":  mo,
        "ranking":      results,
    }

    # Write output
    os.makedirs("data", exist_ok=True)
    out_path = "data/wei_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[WEI] Written to {out_path}")
    print(f"[WEI] Top 3:")
    for r in results[:3]:
        print(f"  #{r['rank']} {r['name']:20s} score={r['score']:3d}  wx={r['scores']['weather']} traf={r['scores']['travel']} crowd={r['scores']['crowd']}")

    return output


if __name__ == "__main__":
    compute_all()
