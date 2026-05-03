import os
import re
import json
import time
import math
import smtplib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import joblib
import numpy as np
import pandas as pd
import requests
from icalendar import Calendar
from dateutil import tz

try:
    import fastf1
except Exception:
    fastf1 = None

from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss


# -----------------------------
# Configuration
# -----------------------------

F1_ICS_URL = os.getenv("F1_ICS_URL", "").strip()

EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() == "true"
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

USER_TIMEZONE_NAME = os.getenv("USER_TIMEZONE", "Asia/Kolkata")
USER_TIMEZONE = tz.gettz(USER_TIMEZONE_NAME) or timezone.utc

LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "90"))
ML_START_YEAR = int(os.getenv("ML_START_YEAR", "2018"))

BASE_DIR = Path(__file__).resolve().parent
BRIEFINGS_DIR = BASE_DIR / "briefings"
DATA_CACHE_DIR = BASE_DIR / "data_cache"
HTTP_CACHE_DIR = Path(os.getenv("HTTP_CACHE_DIR", DATA_CACHE_DIR / "http"))
FASTF1_CACHE_DIR = Path(os.getenv("FASTF1_CACHE_DIR", BASE_DIR / "fastf1_cache"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "models" / "saved_models"))

MODEL_BUNDLE_PATH = MODEL_DIR / "f1_hybrid_ml_bundle.pkl"
MODEL_META_PATH = MODEL_DIR / "f1_hybrid_ml_meta.json"

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
JOLPICA_HEADERS = {
    "User-Agent": "f1-briefing-bot/2.0 (free-data ML hybrid; GitHub Actions)",
    "Accept": "application/json",
}

FASTF1_SESSION_ORDER = ["R", "Q", "SQ", "S", "FP3", "FP2", "FP1"]

PREDICTION_LABELS = {
    "ml_win_probability": "ML win probability",
    "ml_podium_probability": "ML podium probability",
    "ml_top10_probability": "ML top 10 probability",
    "driver_form": "driver form",
    "car_performance": "car performance",
    "recent_result": "recent race result",
    "qualifying": "qualifying and grid position",
    "circuit_history": "same-circuit history",
    "race_pace": "race pace",
    "pit_execution": "pit-stop execution",
    "team_strategy": "team strategy and recovery",
    "reliability": "reliability",
    "team_track_fit": "team-track fit",
    "weather_adaptation": "weather adaptation",
    "fastf1_race_pace": "FastF1 session pace",
    "fastf1_consistency": "FastF1 consistency",
    "fastf1_tyre_stint": "FastF1 tyre/stint evidence",
}


# -----------------------------
# Generic helpers
# -----------------------------

def ensure_dirs():
    for path in [BRIEFINGS_DIR, DATA_CACHE_DIR, HTTP_CACHE_DIR, FASTF1_CACHE_DIR, MODEL_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def require_env_vars():
    missing = []
    if not F1_ICS_URL:
        missing.append("F1_ICS_URL")

    if EMAIL_ENABLED:
        for key, value in {
            "EMAIL_ADDRESS": EMAIL_ADDRESS,
            "EMAIL_APP_PASSWORD": EMAIL_APP_PASSWORD,
            "EMAIL_TO": EMAIL_TO,
        }.items():
            if not value:
                missing.append(key)

    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))


def safe_step(name, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as error:
        print(f"{name} failed, but workflow will continue: {error}")
        return None


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str) and value.strip().lower() in {"nan", "none"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def average(values):
    clean = [safe_float(v) for v in values]
    clean = [v for v in clean if v is not None]
    return sum(clean) / len(clean) if clean else None


def weighted_average(items):
    total = 0
    weight_sum = 0
    for value, weight in items:
        value = safe_float(value)
        if value is None:
            continue
        total += value * weight
        weight_sum += weight
    return total / weight_sum if weight_sum else None


def normalize_name(name):
    text = str(name or "").replace("_", " ").strip()
    return " ".join(word.capitalize() if word.isupper() else word for word in text.split())


def make_slug(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:90] or "f1-briefing"


def normalize_scores(raw, reverse=False):
    if not raw:
        return {}
    values = [safe_float(v) for v in raw.values()]
    values = [v for v in values if v is not None]
    if not values:
        return {}
    low = min(values)
    high = max(values)
    out = {}
    for key, value in raw.items():
        value = safe_float(value)
        if value is None:
            continue
        if high == low:
            out[key] = 75
        elif reverse:
            out[key] = max(0, min(100, (high - value) / (high - low) * 100))
        else:
            out[key] = max(0, min(100, (value - low) / (high - low) * 100))
    return out


def score_position(position, field_size=22):
    position = safe_int(position)
    if position is None or position <= 0:
        return None
    return max(0, 100 * (field_size - position) / max(1, field_size - 1))


def parse_lap_time_to_seconds(value):
    if value is None:
        return None
    text = str(value).strip()
    try:
        parts = text.split(":")
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (TypeError, ValueError):
        return None
    return None


def now_local():
    return datetime.now(USER_TIMEZONE)


# -----------------------------
# HTTP and Jolpica
# -----------------------------

def cache_key_for_url(url, params=None):
    raw = url + "?" + json.dumps(params or {}, sort_keys=True)
    return make_slug(raw)


def safe_get(url, params=None, timeout=30, headers=None, optional_404=False, use_cache=True):
    ensure_dirs()
    cache_path = HTTP_CACHE_DIR / f"{cache_key_for_url(url, params)}.json"

    if use_cache and cache_path.exists():
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < 6 * 3600:
                text = cache_path.read_text(encoding="utf-8")
                fake = requests.Response()
                fake.status_code = 200
                fake._content = text.encode("utf-8")
                return fake
        except Exception:
            pass

    for attempt in range(3):
        try:
            response = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)

            if response.status_code == 404 and optional_404:
                print(f"Optional endpoint not available: {url}")
                return None

            if response.status_code == 429:
                wait = 3 + attempt * 3
                print(f"Rate limited. Waiting {wait}s before retry.")
                time.sleep(wait)
                continue

            response.raise_for_status()

            if use_cache and response.headers.get("content-type", "").lower().find("json") >= 0:
                cache_path.write_text(response.text, encoding="utf-8")

            return response
        except Exception as error:
            print(f"GET failed: {url} params={params} attempt={attempt + 1}/3 error={error}")
            if attempt < 2:
                time.sleep(1.5 + attempt)

    return None


def jolpica_get(endpoint, params=None, optional_404=False):
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    if not endpoint.endswith(".json"):
        endpoint += ".json"

    response = safe_get(
        JOLPICA_BASE + endpoint,
        params=params,
        headers=JOLPICA_HEADERS,
        optional_404=optional_404,
        timeout=30,
    )
    if not response:
        return {}

    try:
        data = response.json()
    except json.JSONDecodeError:
        print(f"Jolpica returned non-JSON for {endpoint}")
        return {}

    print(f"Jolpica OK: {endpoint}")
    return data


def mrdata_list(data, table_name, list_name):
    try:
        return data.get("MRData", {}).get(table_name, {}).get(list_name, [])
    except AttributeError:
        return []


def mrdata_standing_list(data):
    try:
        lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
        return lists[0] if lists else {}
    except (AttributeError, IndexError):
        return {}


def fetch_schedule(year):
    return mrdata_list(jolpica_get(f"/{year}"), "RaceTable", "Races")


def fetch_round_data(season, round_no):
    return {
        "results": mrdata_list(jolpica_get(f"/{season}/{round_no}/results"), "RaceTable", "Races"),
        "qualifying": mrdata_list(jolpica_get(f"/{season}/{round_no}/qualifying"), "RaceTable", "Races"),
        "pitstops": mrdata_list(jolpica_get(f"/{season}/{round_no}/pitstops"), "RaceTable", "Races"),
        "laps": mrdata_list(jolpica_get(f"/{season}/{round_no}/laps"), "RaceTable", "Races"),
        "sprint": mrdata_list(jolpica_get(f"/{season}/{round_no}/sprint", optional_404=True), "RaceTable", "Races"),
        "sprint_qualifying": mrdata_list(
            jolpica_get(f"/{season}/{round_no}/sprint/qualifying", optional_404=True),
            "RaceTable",
            "Races",
        ),
    }


def fetch_driver_standings(season):
    data = jolpica_get(f"/{season}/driverStandings")
    standing = mrdata_standing_list(data)
    return standing.get("DriverStandings", []) if standing else []


def fetch_constructor_standings(season):
    data = jolpica_get(f"/{season}/constructorStandings")
    standing = mrdata_standing_list(data)
    return standing.get("ConstructorStandings", []) if standing else []


def fetch_last_results(season):
    races = mrdata_list(jolpica_get(f"/{season}/last/results"), "RaceTable", "Races")
    return races[0].get("Results", []) if races else []


def parse_race_datetime(race):
    date = race.get("date")
    time_value = race.get("time") or "00:00:00Z"
    if not date:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{time_value}".replace("Z", "+00:00")).astimezone(USER_TIMEZONE)
    except ValueError:
        return None


# -----------------------------
# Calendar
# -----------------------------

def fetch_ics_calendar():
    url = F1_ICS_URL.strip().strip('"').strip("'")
    if url.startswith("webcal://"):
        url = "https://" + url.replace("webcal://", "", 1)
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("F1_ICS_URL must be an HTTP URL, not webcal or secret mask.")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return Calendar.from_ical(response.content)


def normalize_datetime(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.combine(value, datetime.min.time())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(USER_TIMEZONE)


def find_next_calendar_event(calendar):
    now = now_local()
    max_date = now + timedelta(days=LOOKAHEAD_DAYS)
    events = []

    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        title = str(component.get("summary", ""))
        location = str(component.get("location", ""))
        description = str(component.get("description", ""))
        start_raw = component.get("dtstart")
        end_raw = component.get("dtend")
        if not start_raw:
            continue
        start = normalize_datetime(start_raw.dt)
        end = normalize_datetime(end_raw.dt) if end_raw else None

        text = f"{title} {location} {description}".lower()
        looks_like_f1 = any(k in text for k in ["formula 1", "f1", "grand prix", "qualifying", "practice", "sprint", "race"])

        if looks_like_f1 and now <= start <= max_date:
            events.append({"title": title, "location": location, "description": description, "start": start, "end": end})
    events.sort(key=lambda item: item["start"])
    return events[0] if events else None


def tokenize(text):
    stop = {"formula", "one", "f1", "grand", "prix", "race", "practice", "qualifying", "sprint", "session", "round", "the", "and", "for", "gp"}
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return [w for w in words if len(w) >= 4 and w not in stop]


def race_text(race):
    circuit = race.get("Circuit", {})
    location = circuit.get("Location", {})
    return " ".join([
        str(race.get("raceName", "")),
        str(circuit.get("circuitName", "")),
        str(circuit.get("circuitId", "")),
        str(location.get("locality", "")),
        str(location.get("country", "")),
    ]).lower()


def find_best_race(event):
    event_year = event["start"].year
    event_tokens = tokenize(f"{event['title']} {event['location']} {event['description']}")

    best_race = None
    best_score = -999

    for year in [event_year, event_year - 1]:
        for race in fetch_schedule(year):
            text = race_text(race)
            score = 0
            for token in event_tokens:
                if token in text:
                    score += 6
            race_date = parse_race_datetime(race)
            if race_date:
                delta_days = abs((race_date.date() - event["start"].date()).days)
                if year == event_year:
                    score += 8
                if delta_days <= 1:
                    score += 24
                elif delta_days <= 7:
                    score += 8
                else:
                    score -= min(delta_days, 30)
            if score > best_score:
                best_score = score
                best_race = race

    return best_race if best_score >= 5 else None


# -----------------------------
# Weather
# -----------------------------

def fetch_weather_for_race(race, event_start):
    location = race.get("Circuit", {}).get("Location", {})
    lat = safe_float(location.get("lat"))
    lon = safe_float(location.get("long"))

    base = {
        "source": "Open-Meteo forecast",
        "temperature": "Unavailable",
        "rain": "Unavailable",
        "humidity": "Unavailable",
        "wind": "Unavailable",
        "track_temperature": "Unavailable",
        "rain_score": 0,
        "heat_score": 0,
        "wind_score": 0,
        "impact": "Weather unavailable.",
    }

    if lat is None or lon is None:
        base["source"] = "Unavailable"
        base["impact"] = "Circuit coordinates were missing."
        return base

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m,cloud_cover",
        "forecast_days": 10,
        "timezone": USER_TIMEZONE_NAME,
    }
    response = safe_get("https://api.open-meteo.com/v1/forecast", params=params, timeout=35, use_cache=False)
    if not response:
        base["impact"] = "Open-Meteo request failed or timed out."
        return base

    try:
        data = response.json()
    except json.JSONDecodeError:
        base["impact"] = "Open-Meteo returned non-JSON data."
        return base

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        base["impact"] = "No hourly forecast returned."
        return base

    target = event_start.replace(minute=0, second=0, microsecond=0)
    parsed = []
    for item in times:
        try:
            parsed.append(datetime.fromisoformat(item).replace(tzinfo=USER_TIMEZONE))
        except ValueError:
            parsed.append(None)
    valid = [(idx, value) for idx, value in enumerate(parsed) if value is not None]
    if not valid:
        base["impact"] = "Forecast timestamps could not be parsed."
        return base

    index = min(valid, key=lambda pair: abs(pair[1] - target))[0]

    def get_hourly(key):
        values = hourly.get(key, [])
        return values[index] if index < len(values) else None

    temp = get_hourly("temperature_2m")
    rain = get_hourly("precipitation_probability")
    humidity = get_hourly("relative_humidity_2m")
    wind = get_hourly("wind_speed_10m")
    gust = get_hourly("wind_gusts_10m")
    cloud = get_hourly("cloud_cover")

    temp_number = safe_float(temp)
    rain_score = min(100, safe_float(rain) or 0)
    wind_number = safe_float(gust) or safe_float(wind) or 0

    heat_score = 0
    if temp_number is not None:
        if temp_number >= 34:
            heat_score = 85
        elif temp_number >= 29:
            heat_score = 60
        elif temp_number <= 15:
            heat_score = 55

    wind_score = min(100, wind_number * 2.6)

    impact = []
    if rain_score >= 50:
        impact.append("high rain risk, mixed strategy possible")
    elif rain_score >= 25:
        impact.append("moderate rain risk, radar should influence pit timing")
    else:
        impact.append("dry baseline more likely")
    if heat_score >= 60:
        impact.append("heat may increase degradation and cooling demand")
    if wind_score >= 60:
        impact.append("wind may affect braking stability and aero balance")
    if safe_float(cloud) and safe_float(cloud) >= 70:
        impact.append("cloud cover may reduce track-temperature growth")

    return {
        "source": "Open-Meteo forecast",
        "temperature": f"{temp}°C" if temp is not None else "Unavailable",
        "rain": f"{rain}%" if rain is not None else "Unavailable",
        "humidity": f"{humidity}%" if humidity is not None else "Unavailable",
        "wind": f"{wind} km/h" if wind is not None else "Unavailable",
        "wind_gust": f"{gust} km/h" if gust is not None else "Unavailable",
        "cloud_cover": f"{cloud}%" if cloud is not None else "Unavailable",
        "track_temperature": "Unavailable",
        "rain_score": rain_score,
        "heat_score": heat_score,
        "wind_score": wind_score,
        "impact": "; ".join(impact),
    }


def fetch_historical_weather_summary(race, years_back=3):
    location = race.get("Circuit", {}).get("Location", {})
    lat = safe_float(location.get("lat"))
    lon = safe_float(location.get("long"))
    race_dt = parse_race_datetime(race)
    if lat is None or lon is None or not race_dt:
        return {}

    summaries = []
    for year in range(race_dt.year - years_back, race_dt.year):
        start = race_dt.replace(year=year).date().isoformat()
        end = (race_dt.replace(year=year) + timedelta(days=1)).date().isoformat()
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,cloud_cover",
            "timezone": USER_TIMEZONE_NAME,
        }
        response = safe_get("https://archive-api.open-meteo.com/v1/archive", params=params, timeout=35)
        if not response:
            continue
        try:
            data = response.json()
        except json.JSONDecodeError:
            continue
        hourly = data.get("hourly", {})
        summaries.append({
            "year": year,
            "avg_temp": average(hourly.get("temperature_2m", [])),
            "max_wind": max([safe_float(x) or 0 for x in hourly.get("wind_speed_10m", [])], default=None),
            "rain_total": sum([safe_float(x) or 0 for x in hourly.get("precipitation", [])]),
            "avg_cloud": average(hourly.get("cloud_cover", [])),
        })
    return {"source": "Open-Meteo archive", "samples": summaries}


# -----------------------------
# Historical data for ML and scoring
# -----------------------------

def driver_name(driver):
    return normalize_name(f"{driver.get('givenName', '')} {driver.get('familyName', '')}")


def standings_to_drivers(driver_standings):
    drivers = []
    for row in driver_standings:
        driver = row.get("Driver", {})
        constructors = row.get("Constructors", [])
        team = constructors[0].get("name") if constructors else "Unknown Team"
        drivers.append({
            "driver_id": driver.get("driverId"),
            "name": driver_name(driver),
            "team": team,
            "points": safe_float(row.get("points")) or 0,
            "position": safe_int(row.get("position")),
            "wins": safe_int(row.get("wins")) or 0,
            "image": None,
            "team_colour": None,
        })
    return drivers


def collect_race_rows(start_year, end_year):
    rows = []
    for year in range(start_year, end_year + 1):
        print(f"Collecting historical Jolpica rows for {year}")
        for race in fetch_schedule(year):
            round_no = race.get("round")
            if not round_no:
                continue
            data = fetch_round_data(year, round_no)
            result_races = data.get("results", [])
            if not result_races:
                continue

            q_positions = {}
            qualifying = data.get("qualifying", [])
            if qualifying:
                for q in qualifying[0].get("QualifyingResults", []):
                    driver_id = q.get("Driver", {}).get("driverId")
                    q_positions[driver_id] = safe_int(q.get("position"))

            race_id = f"{year}-{round_no}"
            circuit = race.get("Circuit", {})
            circuit_id = circuit.get("circuitId")
            race_dt = parse_race_datetime(race)
            for result in result_races[0].get("Results", []):
                driver = result.get("Driver", {})
                constructor = result.get("Constructor", {})
                driver_id = driver.get("driverId")
                constructor_name = constructor.get("name")
                pos = safe_int(result.get("positionOrder") or result.get("position"))
                grid = safe_int(result.get("grid"))
                points = safe_float(result.get("points")) or 0
                status = str(result.get("status", ""))
                if not driver_id or not constructor_name or not pos:
                    continue
                rows.append({
                    "race_id": race_id,
                    "season": year,
                    "round": safe_int(round_no),
                    "date": race_dt.isoformat() if race_dt else None,
                    "race_name": race.get("raceName"),
                    "circuit_id": circuit_id,
                    "circuit_name": circuit.get("circuitName"),
                    "driver_id": driver_id,
                    "driver_name": driver_name(driver),
                    "constructor": constructor_name,
                    "grid": grid if grid and grid > 0 else q_positions.get(driver_id),
                    "qualifying": q_positions.get(driver_id),
                    "finish_position": pos,
                    "points": points,
                    "status": status,
                    "is_finished": 1 if ("Finished" in status or "+" in status) else 0,
                    "is_win": 1 if pos == 1 else 0,
                    "is_podium": 1 if pos <= 3 else 0,
                    "is_top10": 1 if pos <= 10 else 0,
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["season", "round", "finish_position"]).reset_index(drop=True)
    return df


def create_ml_features(df):
    if df.empty:
        return df, []

    df = df.copy()
    df["grid"] = pd.to_numeric(df["grid"], errors="coerce").fillna(20)
    df["qualifying"] = pd.to_numeric(df["qualifying"], errors="coerce").fillna(df["grid"])
    df["finish_position"] = pd.to_numeric(df["finish_position"], errors="coerce")
    df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0)

    feature_rows = []
    grouped_driver = {k: g.sort_values(["season", "round"]) for k, g in df.groupby("driver_id")}
    grouped_team = {k: g.sort_values(["season", "round"]) for k, g in df.groupby("constructor")}
    grouped_circuit_driver = {k: g.sort_values(["season", "round"]) for k, g in df.groupby(["circuit_id", "driver_id"])}
    grouped_circuit_team = {k: g.sort_values(["season", "round"]) for k, g in df.groupby(["circuit_id", "constructor"])}

    for idx, race in df.iterrows():
        season = race["season"]
        round_no = race["round"]

        def before(frame):
            return frame[(frame["season"] < season) | ((frame["season"] == season) & (frame["round"] < round_no))]

        d_hist = before(grouped_driver.get(race["driver_id"], pd.DataFrame()))
        t_hist = before(grouped_team.get(race["constructor"], pd.DataFrame()))
        cd_hist = before(grouped_circuit_driver.get((race["circuit_id"], race["driver_id"]), pd.DataFrame()))
        ct_hist = before(grouped_circuit_team.get((race["circuit_id"], race["constructor"]), pd.DataFrame()))

        if len(d_hist) < 3 or len(t_hist) < 3:
            continue

        recent3 = d_hist.tail(3)
        recent5 = d_hist.tail(5)
        team_recent5 = t_hist.tail(10)

        features = {
            "race_id": race["race_id"],
            "season": season,
            "round": round_no,
            "race_name": race["race_name"],
            "circuit_id": race["circuit_id"],
            "driver_id": race["driver_id"],
            "driver_name": race["driver_name"],
            "constructor": race["constructor"],
            "finish_position": race["finish_position"],
            "is_win": race["is_win"],
            "is_podium": race["is_podium"],
            "is_top10": race["is_top10"],

            "grid_position": race["grid"],
            "qualifying_position": race["qualifying"],
            "driver_avg_finish": d_hist["finish_position"].mean(),
            "driver_median_finish": d_hist["finish_position"].median(),
            "driver_avg_points": d_hist["points"].mean(),
            "driver_win_rate": d_hist["is_win"].mean(),
            "driver_podium_rate": d_hist["is_podium"].mean(),
            "driver_top10_rate": d_hist["is_top10"].mean(),
            "driver_finish_rate": d_hist["is_finished"].mean(),
            "driver_recent3_finish": recent3["finish_position"].mean(),
            "driver_recent5_points": recent5["points"].mean(),
            "driver_recent5_podium_rate": recent5["is_podium"].mean(),

            "team_avg_finish": t_hist["finish_position"].mean(),
            "team_avg_points": t_hist["points"].mean(),
            "team_win_rate": t_hist["is_win"].mean(),
            "team_podium_rate": t_hist["is_podium"].mean(),
            "team_top10_rate": t_hist["is_top10"].mean(),
            "team_finish_rate": t_hist["is_finished"].mean(),
            "team_recent_points": team_recent5["points"].mean(),

            "driver_circuit_avg_finish": cd_hist["finish_position"].mean() if len(cd_hist) else d_hist["finish_position"].mean(),
            "driver_circuit_podium_rate": cd_hist["is_podium"].mean() if len(cd_hist) else d_hist["is_podium"].mean(),
            "team_circuit_avg_finish": ct_hist["finish_position"].mean() if len(ct_hist) else t_hist["finish_position"].mean(),
            "team_circuit_podium_rate": ct_hist["is_podium"].mean() if len(ct_hist) else t_hist["is_podium"].mean(),

            "career_starts": len(d_hist),
            "team_starts": len(t_hist),
            "circuit_experience": len(cd_hist),
        }
        feature_rows.append(features)

    feature_df = pd.DataFrame(feature_rows)
    feature_columns = [
        "grid_position",
        "qualifying_position",
        "driver_avg_finish",
        "driver_median_finish",
        "driver_avg_points",
        "driver_win_rate",
        "driver_podium_rate",
        "driver_top10_rate",
        "driver_finish_rate",
        "driver_recent3_finish",
        "driver_recent5_points",
        "driver_recent5_podium_rate",
        "team_avg_finish",
        "team_avg_points",
        "team_win_rate",
        "team_podium_rate",
        "team_top10_rate",
        "team_finish_rate",
        "team_recent_points",
        "driver_circuit_avg_finish",
        "driver_circuit_podium_rate",
        "team_circuit_avg_finish",
        "team_circuit_podium_rate",
        "career_starts",
        "team_starts",
        "circuit_experience",
    ]
    return feature_df, feature_columns


def latest_completed_race_id(current_year=None):
    year = current_year or now_local().year
    races = fetch_schedule(year)
    completed = []
    for race in races:
        race_dt = parse_race_datetime(race)
        if race_dt and race_dt < now_local() - timedelta(hours=2):
            data = fetch_round_data(year, race.get("round"))
            if data.get("results"):
                completed.append((race_dt, f"{year}-{race.get('round')}", race))
    if not completed and year > 1950:
        return latest_completed_race_id(year - 1)
    completed.sort(key=lambda item: item[0])
    return completed[-1][1] if completed else None


def should_retrain(force=False):
    if force:
        return True
    if not MODEL_BUNDLE_PATH.exists() or not MODEL_META_PATH.exists():
        return True
    try:
        meta = json.loads(MODEL_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return True
    latest = latest_completed_race_id()
    return bool(latest and meta.get("latest_completed_race_id") != latest)


def train_ml_model(force=False):
    if not should_retrain(force):
        print("ML model is current. Skipping retrain.")
        return load_ml_bundle()

    print("Training ML model from free Jolpica historical data...")
    current_year = now_local().year
    raw_df = collect_race_rows(ML_START_YEAR, current_year)
    if raw_df.empty:
        raise RuntimeError("No historical rows collected for ML training.")

    raw_path = DATA_CACHE_DIR / "ml_race_results_raw.csv"
    features_path = DATA_CACHE_DIR / "ml_race_features.csv"
    raw_df.to_csv(raw_path, index=False)

    feature_df, feature_columns = create_ml_features(raw_df)
    if len(feature_df) < 100:
        raise RuntimeError(f"Not enough ML feature rows: {len(feature_df)}")

    feature_df.to_csv(features_path, index=False)

    train_years = sorted(feature_df["season"].unique())
    validation_year = train_years[-1]
    train_df = feature_df[feature_df["season"] < validation_year].copy()
    valid_df = feature_df[feature_df["season"] == validation_year].copy()
    if len(train_df) < 50 or len(valid_df) < 20:
        train_df = feature_df.sample(frac=0.8, random_state=42)
        valid_df = feature_df.drop(train_df.index)

    X_train = train_df[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)
    X_valid = valid_df[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)

    targets = {
        "win": "is_win",
        "podium": "is_podium",
        "top10": "is_top10",
    }

    models = {}
    metrics = {}

    for name, target_col in targets.items():
        y_train = train_df[target_col].astype(int)
        y_valid = valid_df[target_col].astype(int)

        rf = RandomForestClassifier(
            n_estimators=260,
            max_depth=10,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )
        hgb = HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=0.06,
            max_leaf_nodes=31,
            l2_regularization=0.02,
            random_state=42,
        )

        rf.fit(X_train, y_train)
        hgb.fit(X_train, y_train)

        valid_rf = rf.predict_proba(X_valid)[:, 1]
        valid_hgb = hgb.predict_proba(X_valid)[:, 1]
        valid_prob = (valid_rf * 0.55) + (valid_hgb * 0.45)

        try:
            auc = roc_auc_score(y_valid, valid_prob)
        except Exception:
            auc = None
        try:
            brier = brier_score_loss(y_valid, valid_prob)
        except Exception:
            brier = None

        models[name] = {"rf": rf, "hgb": hgb}
        metrics[name] = {"auc": auc, "brier": brier, "validation_rows": len(valid_df)}

    latest_id = latest_completed_race_id()
    bundle = {
        "models": models,
        "feature_columns": feature_columns,
        "trained_at": now_local().isoformat(),
        "ml_start_year": ML_START_YEAR,
        "latest_completed_race_id": latest_id,
        "metrics": metrics,
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_BUNDLE_PATH)

    meta = {
        "trained_at": bundle["trained_at"],
        "ml_start_year": ML_START_YEAR,
        "rows_raw": len(raw_df),
        "rows_features": len(feature_df),
        "latest_completed_race_id": latest_id,
        "metrics": metrics,
        "feature_columns": feature_columns,
    }
    MODEL_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"ML model saved to {MODEL_BUNDLE_PATH}")
    return bundle


def load_ml_bundle():
    if not MODEL_BUNDLE_PATH.exists():
        return None
    try:
        return joblib.load(MODEL_BUNDLE_PATH)
    except Exception as error:
        print(f"Could not load ML model bundle: {error}")
        return None


def historical_feature_context(start_year, target_season):
    df = collect_race_rows(start_year, target_season)
    return df.sort_values(["season", "round"]) if not df.empty else df


def build_prediction_feature_rows(drivers, race, current_round_data, historical_df, feature_columns):
    season = safe_int(race.get("season")) or now_local().year
    round_no = safe_int(race.get("round")) or 0
    circuit_id = race.get("Circuit", {}).get("circuitId")
    race_id = f"{season}-{round_no}"

    q_positions = {}
    qualifying = current_round_data.get("qualifying", [])
    if qualifying:
        for q in qualifying[0].get("QualifyingResults", []):
            driver_id = q.get("Driver", {}).get("driverId")
            q_positions[driver_id] = safe_int(q.get("position"))

    rows = []
    for driver in drivers:
        driver_id = driver["driver_id"]
        team = driver["team"]
        hist = historical_df.copy()
        hist = hist[(hist["season"] < season) | ((hist["season"] == season) & (hist["round"] < round_no))]

        d_hist = hist[hist["driver_id"] == driver_id]
        t_hist = hist[hist["constructor"] == team]
        cd_hist = hist[(hist["circuit_id"] == circuit_id) & (hist["driver_id"] == driver_id)]
        ct_hist = hist[(hist["circuit_id"] == circuit_id) & (hist["constructor"] == team)]

        recent3 = d_hist.tail(3)
        recent5 = d_hist.tail(5)
        team_recent5 = t_hist.tail(10)

        standing_grid_proxy = min(20, max(1, safe_int(driver.get("position")) or 12))
        grid = q_positions.get(driver_id) or standing_grid_proxy

        row = {
            "race_id": race_id,
            "season": season,
            "round": round_no,
            "race_name": race.get("raceName"),
            "circuit_id": circuit_id,
            "driver_id": driver_id,
            "driver_name": driver["name"],
            "constructor": team,

            "grid_position": grid,
            "qualifying_position": q_positions.get(driver_id) or grid,
            "driver_avg_finish": d_hist["finish_position"].mean() if len(d_hist) else 12,
            "driver_median_finish": d_hist["finish_position"].median() if len(d_hist) else 12,
            "driver_avg_points": d_hist["points"].mean() if len(d_hist) else 0,
            "driver_win_rate": d_hist["is_win"].mean() if len(d_hist) else 0,
            "driver_podium_rate": d_hist["is_podium"].mean() if len(d_hist) else 0,
            "driver_top10_rate": d_hist["is_top10"].mean() if len(d_hist) else 0,
            "driver_finish_rate": d_hist["is_finished"].mean() if len(d_hist) else 0.8,
            "driver_recent3_finish": recent3["finish_position"].mean() if len(recent3) else (d_hist["finish_position"].mean() if len(d_hist) else 12),
            "driver_recent5_points": recent5["points"].mean() if len(recent5) else (d_hist["points"].mean() if len(d_hist) else 0),
            "driver_recent5_podium_rate": recent5["is_podium"].mean() if len(recent5) else (d_hist["is_podium"].mean() if len(d_hist) else 0),

            "team_avg_finish": t_hist["finish_position"].mean() if len(t_hist) else 12,
            "team_avg_points": t_hist["points"].mean() if len(t_hist) else 0,
            "team_win_rate": t_hist["is_win"].mean() if len(t_hist) else 0,
            "team_podium_rate": t_hist["is_podium"].mean() if len(t_hist) else 0,
            "team_top10_rate": t_hist["is_top10"].mean() if len(t_hist) else 0,
            "team_finish_rate": t_hist["is_finished"].mean() if len(t_hist) else 0.8,
            "team_recent_points": team_recent5["points"].mean() if len(team_recent5) else (t_hist["points"].mean() if len(t_hist) else 0),

            "driver_circuit_avg_finish": cd_hist["finish_position"].mean() if len(cd_hist) else (d_hist["finish_position"].mean() if len(d_hist) else 12),
            "driver_circuit_podium_rate": cd_hist["is_podium"].mean() if len(cd_hist) else (d_hist["is_podium"].mean() if len(d_hist) else 0),
            "team_circuit_avg_finish": ct_hist["finish_position"].mean() if len(ct_hist) else (t_hist["finish_position"].mean() if len(t_hist) else 12),
            "team_circuit_podium_rate": ct_hist["is_podium"].mean() if len(ct_hist) else (t_hist["is_podium"].mean() if len(t_hist) else 0),
            "career_starts": len(d_hist),
            "team_starts": len(t_hist),
            "circuit_experience": len(cd_hist),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    for col in feature_columns:
        if col not in df:
            df[col] = 0
    return df


def ml_predict_probabilities(drivers, race, current_round_data, bundle):
    if not bundle:
        return {}, {}
    try:
        feature_columns = bundle["feature_columns"]
        historical_df = historical_feature_context(bundle.get("ml_start_year", ML_START_YEAR), safe_int(race.get("season")) or now_local().year)
        pred_df = build_prediction_feature_rows(drivers, race, current_round_data, historical_df, feature_columns)
        X = pred_df[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)

        outputs = {}
        for target_name, pair in bundle["models"].items():
            rf_prob = pair["rf"].predict_proba(X)[:, 1]
            hgb_prob = pair["hgb"].predict_proba(X)[:, 1]
            prob = (rf_prob * 0.55) + (hgb_prob * 0.45)
            outputs[target_name] = prob

        by_driver = {}
        for idx, row in pred_df.iterrows():
            driver_id = row["driver_id"]
            by_driver[driver_id] = {
                "ml_win_probability": float(outputs.get("win", [0])[idx] * 100),
                "ml_podium_probability": float(outputs.get("podium", [0])[idx] * 100),
                "ml_top10_probability": float(outputs.get("top10", [0])[idx] * 100),
            }
        return by_driver, {"feature_rows": pred_df.to_dict(orient="records"), "bundle_meta": {k: v for k, v in bundle.items() if k not in {"models"}}}
    except Exception as error:
        print(f"ML prediction failed: {error}")
        return {}, {"error": str(error)}


# -----------------------------
# Track, strategy, FastF1 metrics
# -----------------------------

def fetch_historical_same_circuit(target_race, years_back=4):
    target_circuit_id = target_race.get("Circuit", {}).get("circuitId")
    target_season = safe_int(target_race.get("season")) or now_local().year
    records = []
    if not target_circuit_id:
        return records

    for year in range(target_season, target_season - years_back - 1, -1):
        for race in fetch_schedule(year):
            if race.get("Circuit", {}).get("circuitId") == target_circuit_id:
                round_no = race.get("round")
                if round_no:
                    records.append({"season": year, "round": round_no, "race": race, "data": fetch_round_data(year, round_no)})
                break
    return records


def extract_results(historical_records):
    rows = []
    for record in historical_records:
        races = record.get("data", {}).get("results", [])
        if not races:
            continue
        for row in races[0].get("Results", []):
            rows.append({**row, "season": record["season"]})
    return rows


def extract_qualifying(historical_records):
    rows = []
    for record in historical_records:
        races = record.get("data", {}).get("qualifying", [])
        if not races:
            continue
        for row in races[0].get("QualifyingResults", []):
            rows.append({**row, "season": record["season"]})
    return rows


def extract_pitstops(historical_records):
    rows = []
    for record in historical_records:
        races = record.get("data", {}).get("pitstops", [])
        if not races:
            continue
        for row in races[0].get("PitStops", []):
            rows.append({**row, "season": record["season"]})
    return rows


def infer_track_profile(race, historical_records, weather_summary, historical_weather=None):
    results = extract_results(historical_records)
    qualifying = extract_qualifying(historical_records)
    pitstops = extract_pitstops(historical_records)

    overtaking_deltas = []
    dnf_count = 0
    finished_count = 0

    for result in results:
        grid = safe_int(result.get("grid"))
        finish = safe_int(result.get("positionOrder") or result.get("position"))
        status = str(result.get("status", "")).lower()
        if grid and grid > 0 and finish:
            overtaking_deltas.append(abs(grid - finish))
        if "finished" in status or "+" in status:
            finished_count += 1
        else:
            dnf_count += 1

    avg_overtake = average(overtaking_deltas)
    if avg_overtake is None:
        overtaking = "unknown"
        overtaking_reason = "not enough grid-to-result history"
    elif avg_overtake >= 5:
        overtaking = "good"
        overtaking_reason = f"average grid-to-finish movement around {avg_overtake:.1f} places"
    elif avg_overtake >= 3:
        overtaking = "medium-good"
        overtaking_reason = f"average grid-to-finish movement around {avg_overtake:.1f} places"
    elif avg_overtake >= 1.5:
        overtaking = "medium"
        overtaking_reason = f"average grid-to-finish movement around {avg_overtake:.1f} places"
    else:
        overtaking = "low-medium"
        overtaking_reason = f"average grid-to-finish movement around {avg_overtake:.1f} places"

    drivers_seen = len(set(row.get("driverId") for row in pitstops if row.get("driverId")))
    avg_stops = len(pitstops) / drivers_seen if drivers_seen else None
    if avg_stops is None:
        tyre_stress = "unknown"
        tyre_reason = "not enough pit-stop history"
    elif avg_stops >= 2.0:
        tyre_stress = "high"
        tyre_reason = f"historical average around {avg_stops:.1f} stops per driver"
    elif avg_stops >= 1.45:
        tyre_stress = "medium-high"
        tyre_reason = f"historical average around {avg_stops:.1f} stops per driver"
    elif avg_stops >= 1.0:
        tyre_stress = "medium"
        tyre_reason = f"historical average around {avg_stops:.1f} stops per driver"
    else:
        tyre_stress = "low-medium"
        tyre_reason = f"historical average around {avg_stops:.1f} stops per driver"

    dnf_rate = dnf_count / max(1, dnf_count + finished_count)
    if dnf_rate >= 0.25:
        safety_car = "high"
    elif dnf_rate >= 0.15:
        safety_car = "medium-high"
    elif dnf_rate >= 0.08:
        safety_car = "medium"
    else:
        safety_car = "low-medium"

    circuit = race.get("Circuit", {})
    circuit_name = circuit.get("circuitName", "Unknown circuit")
    circuit_id = circuit.get("circuitId", "")
    location = circuit.get("Location", {})
    text = f"{race.get('raceName', '')} {circuit_name} {circuit_id}".lower()

    if any(k in text for k in ["monaco", "singapore", "marina", "baku", "miami", "jeddah", "vegas"]):
        track_type = "street or temporary circuit"
    else:
        track_type = "permanent circuit"

    if any(k in text for k in ["monza", "vegas", "baku", "jeddah"]):
        speed_profile = "straight-line-speed dominant"
        speed_reason = "circuit identity points to long straights and low-drag demand"
    elif any(k in text for k in ["silverstone", "suzuka", "spa", "qatar", "lusail"]):
        speed_profile = "aero-efficiency dominant"
        speed_reason = "circuit identity points to high-speed cornering load"
    elif any(k in text for k in ["monaco", "hungaroring", "singapore"]):
        speed_profile = "traction and braking dominant"
        speed_reason = "circuit identity points to slow corners and track position"
    else:
        speed_profile = "balanced speed profile"
        speed_reason = "no extreme speed profile detected from free race data"

    if speed_profile == "straight-line-speed dominant":
        dominance = "low drag and straight-line speed"
    elif speed_profile == "aero-efficiency dominant":
        dominance = "aero efficiency and tyre-load management"
    elif "street" in track_type and overtaking in {"low", "low-medium", "unknown"}:
        dominance = "track position, braking stability, and wall confidence"
    elif tyre_stress in {"high", "medium-high"}:
        dominance = "tyre management and thermal control"
    else:
        dominance = "balanced aero, traction, and tyre management"

    if tyre_stress in {"high", "medium-high"}:
        strategy_bias = "two-stop risk if degradation appears in long runs"
    elif overtaking in {"low", "low-medium"}:
        strategy_bias = "track position first, undercut can matter"
    else:
        strategy_bias = "one-stop or two-stop depending on safety car and tyre delta"

    setup = []
    if "straight-line" in dominance:
        setup.append("lower drag wing level with strong braking stability")
    elif "track position" in dominance:
        setup.append("higher downforce, braking confidence, and kerb compliance")
    elif "tyre" in dominance:
        setup.append("stable platform with tyre temperature control")
    else:
        setup.append("balanced aero platform")

    if weather_summary.get("rain_score", 0) >= 35:
        setup.append("keep wet crossover flexibility")
    if weather_summary.get("wind_score", 0) >= 60:
        setup.append("avoid unstable aero balance in wind")

    return {
        "race_name": race.get("raceName", "Unknown Grand Prix"),
        "official_name": race.get("raceName"),
        "circuit": circuit_name,
        "city": location.get("locality", "Unknown location"),
        "country": location.get("country", "Unknown country"),
        "track_type": track_type,
        "circuit_key": circuit_id,
        "meeting_key": f"{race.get('season')}-{race.get('round')}",
        "dominance": dominance,
        "speed_profile": speed_profile,
        "overtaking": overtaking,
        "tyre_stress": tyre_stress,
        "safety_car": safety_car,
        "strategy_bias": strategy_bias,
        "setup": "; ".join(setup),
        "dynamic_reasons": {
            "tyre_stress": tyre_reason,
            "overtaking": overtaking_reason,
            "safety_car": f"non-finish proxy rate around {dnf_rate * 100:.1f}%",
            "speed_profile": speed_reason,
        },
        "dynamic_track_source": {
            "used_jolpica_schedule": True,
            "used_jolpica_history": bool(historical_records),
            "used_open_meteo_archive": bool(historical_weather and historical_weather.get("samples")),
            "source": "Jolpica + Open-Meteo + optional FastF1",
        },
        "dynamic_track_metrics": {
            "historical_races_sampled": len(historical_records),
            "results_sampled": len(results),
            "qualifying_rows_sampled": len(qualifying),
            "pitstops_sampled": len(pitstops),
            "average_overtake_delta": avg_overtake,
            "average_stops_per_driver": avg_stops,
        },
        "historical_weather": historical_weather or {},
    }


def constructor_score_map(constructor_standings):
    raw = {}
    for row in constructor_standings:
        constructor = row.get("Constructor", {})
        name = constructor.get("name")
        points = safe_float(row.get("points"))
        position = safe_int(row.get("position"))
        if name:
            raw[name] = points if points is not None else (100 - position if position else 0)
    return normalize_scores(raw)


def current_result_score_map(results):
    raw = {}
    for row in results:
        driver_id = row.get("Driver", {}).get("driverId")
        pos = safe_int(row.get("positionOrder") or row.get("position"))
        if driver_id and pos:
            raw[driver_id] = score_position(pos)
    return raw


def qualifying_score_map(round_data):
    raw = {}
    races = round_data.get("qualifying", [])
    if not races:
        return raw
    for row in races[0].get("QualifyingResults", []):
        driver_id = row.get("Driver", {}).get("driverId")
        pos = safe_int(row.get("position"))
        if driver_id and pos:
            raw[driver_id] = score_position(pos)
    return raw


def circuit_history_score_map(historical_records):
    raw_result = {}
    raw_qual = {}
    for record in historical_records:
        year_weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.18)
        data = record.get("data", {})
        races = data.get("results", [])
        if races:
            for row in races[0].get("Results", []):
                driver_id = row.get("Driver", {}).get("driverId")
                pos = safe_int(row.get("positionOrder") or row.get("position"))
                if driver_id and pos:
                    raw_result.setdefault(driver_id, []).append((score_position(pos), year_weight))
        qs = data.get("qualifying", [])
        if qs:
            for row in qs[0].get("QualifyingResults", []):
                driver_id = row.get("Driver", {}).get("driverId")
                pos = safe_int(row.get("position"))
                if driver_id and pos:
                    raw_qual.setdefault(driver_id, []).append((score_position(pos), year_weight))
    out = {}
    for d in set(raw_result) | set(raw_qual):
        out[d] = weighted_average([
            (weighted_average(raw_result.get(d, [])), 0.65),
            (weighted_average(raw_qual.get(d, [])), 0.35),
        ])
    return out


def constructor_lookup_from_results(result_race):
    lookup = {}
    if not result_race:
        return lookup
    for row in result_race.get("Results", []):
        d = row.get("Driver", {}).get("driverId")
        c = row.get("Constructor", {}).get("name")
        if d and c:
            lookup[d] = c
    return lookup


def race_pace_score_map(historical_records, current_round_data):
    raw = {}

    def collect(races, weight):
        for race in races or []:
            for lap in race.get("Laps", []):
                for timing in lap.get("Timings", []):
                    driver_id = timing.get("driverId")
                    seconds = parse_lap_time_to_seconds(timing.get("time"))
                    if not driver_id or seconds is None:
                        continue
                    if seconds < 45 or seconds > 180:
                        continue
                    raw.setdefault(driver_id, []).append((seconds, weight))

    for record in historical_records:
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.18)
        collect(record.get("data", {}).get("laps", []), weight)
    collect(current_round_data.get("laps", []), 1.25)

    driver_pace = {}
    for driver_id, values in raw.items():
        seconds = [v for v, _ in values]
        if len(seconds) < 5:
            continue
        fastest = min(seconds)
        filtered = sorted([(v, w) for v, w in values if v <= fastest + 7.0], key=lambda item: item[0])
        if len(filtered) < 5:
            continue
        sample_size = max(5, int(len(filtered) * 0.35))
        driver_pace[driver_id] = weighted_average(filtered[:sample_size])
    return normalize_scores(driver_pace, reverse=True)


def pit_execution_score_maps(historical_records, current_round_data):
    driver_raw = {}
    constructor_raw = {}

    def collect(data, weight):
        result_races = data.get("results", [])
        pitstop_races = data.get("pitstops", [])
        if not result_races or not pitstop_races:
            return
        lookup = constructor_lookup_from_results(result_races[0])
        for race in pitstop_races:
            for stop in race.get("PitStops", []):
                driver_id = stop.get("driverId")
                duration = safe_float(stop.get("duration"))
                if not driver_id or duration is None:
                    continue
                if duration < 1.5 or duration > 65:
                    continue
                driver_raw.setdefault(driver_id, []).append((duration, weight))
                constructor = lookup.get(driver_id)
                if constructor:
                    constructor_raw.setdefault(constructor, []).append((duration, weight))

    for record in historical_records:
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.18)
        collect(record.get("data", {}), weight)
    collect(current_round_data, 1.25)

    driver_avg = {d: weighted_average(v) for d, v in driver_raw.items()}
    team_avg = {c: weighted_average(v) for c, v in constructor_raw.items()}
    return normalize_scores(driver_avg, reverse=True), normalize_scores(team_avg, reverse=True)


def strategy_gain_score_maps(historical_records):
    driver_raw = {}
    team_raw = {}
    for record in historical_records:
        races = record.get("data", {}).get("results", [])
        if not races:
            continue
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.18)
        for row in races[0].get("Results", []):
            driver_id = row.get("Driver", {}).get("driverId")
            team = row.get("Constructor", {}).get("name")
            grid = safe_int(row.get("grid"))
            finish = safe_int(row.get("positionOrder") or row.get("position"))
            if not driver_id or not grid or not finish or grid <= 0:
                continue
            gain = grid - finish
            driver_raw.setdefault(driver_id, []).append((gain, weight))
            if team:
                team_raw.setdefault(team, []).append((gain, weight))
    return normalize_scores({d: weighted_average(v) for d, v in driver_raw.items()}), normalize_scores({t: weighted_average(v) for t, v in team_raw.items()})


def constructor_circuit_history_score_map(historical_records):
    raw = {}
    for record in historical_records:
        races = record.get("data", {}).get("results", [])
        if not races:
            continue
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.18)
        for row in races[0].get("Results", []):
            team = row.get("Constructor", {}).get("name")
            pos = safe_int(row.get("positionOrder") or row.get("position"))
            if team and pos:
                raw.setdefault(team, []).append((score_position(pos), weight))
    return {team: weighted_average(values) for team, values in raw.items()}


def reliability_score_map(historical_records):
    raw = {}
    for record in historical_records:
        races = record.get("data", {}).get("results", [])
        if not races:
            continue
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.18)
        for row in races[0].get("Results", []):
            driver_id = row.get("Driver", {}).get("driverId")
            status = str(row.get("status", "")).lower()
            if not driver_id:
                continue
            if "finished" in status or "+" in status:
                score = 88
            elif "accident" in status or "collision" in status or "spun" in status:
                score = 35
            elif "engine" in status or "gearbox" in status or "hydraulics" in status:
                score = 45
            else:
                score = 55
            raw.setdefault(driver_id, []).append((score, weight))
    return {d: weighted_average(v) for d, v in raw.items()}


def team_track_fit_score(team, profile, constructor_circuit_score=None):
    team_text = str(team).lower()
    dominance = str(profile.get("dominance", "")).lower()
    speed = str(profile.get("speed_profile", "")).lower()
    tyre = str(profile.get("tyre_stress", "")).lower()
    overtaking = str(profile.get("overtaking", "")).lower()

    score = 50
    if constructor_circuit_score is not None:
        score = weighted_average([(score, 0.35), (constructor_circuit_score, 0.65)])

    if "straight-line" in speed and any(k in team_text for k in ["williams", "red bull", "ferrari", "cadillac"]):
        score += 7
    if "aero" in dominance and any(k in team_text for k in ["mclaren", "mercedes", "red bull"]):
        score += 8
    if ("tyre" in dominance or tyre in {"high", "medium-high"}) and any(k in team_text for k in ["mclaren", "ferrari", "mercedes"]):
        score += 7
    if ("track position" in dominance or "low" in overtaking) and any(k in team_text for k in ["ferrari", "mclaren", "mercedes"]):
        score += 5
    if "traction" in dominance and any(k in team_text for k in ["red bull", "ferrari", "aston martin"]):
        score += 5
    return max(0, min(100, score))


def setup_fastf1():
    if not fastf1:
        return False
    try:
        FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))
        return True
    except Exception as error:
        print(f"FastF1 cache setup failed: {error}")
        return False


def load_fastf1_session(season, round_no, code):
    if not setup_fastf1():
        return None
    try:
        session = fastf1.get_session(season, int(round_no), code)
        session.load(laps=True, weather=True, messages=False)
        print(f"FastF1 loaded {season} round {round_no} {code}")
        return session
    except Exception as error:
        print(f"FastF1 load skipped for {season} round {round_no} {code}: {error}")
        return None


def fastf1_enhancement_scores(season, round_no):
    scores = {
        "fastf1_race_pace": {},
        "fastf1_consistency": {},
        "fastf1_tyre_stint": {},
        "sessions_loaded": [],
    }
    if not setup_fastf1():
        return scores

    for code in FASTF1_SESSION_ORDER:
        session = load_fastf1_session(season, round_no, code)
        if session is None:
            continue
        scores["sessions_loaded"].append(code)
        try:
            laps = session.laps
            if laps is None or laps.empty:
                continue
            clean = laps.copy()
            if "IsAccurate" in clean.columns:
                clean = clean[clean["IsAccurate"] == True]
            if "Deleted" in clean.columns:
                clean = clean[clean["Deleted"] != True]
            if clean.empty:
                continue

            pace_raw = {}
            consistency_raw = {}
            stint_raw = {}

            for driver, group in clean.groupby("Driver"):
                times = []
                for value in group.get("LapTime", []):
                    try:
                        sec = value.total_seconds()
                    except Exception:
                        sec = None
                    if sec and 45 <= sec <= 180:
                        times.append(sec)
                if len(times) >= 4:
                    sorted_times = sorted(times)
                    sample = sorted_times[:max(4, int(len(sorted_times) * 0.35))]
                    pace_raw[str(driver).lower()] = average(sample)
                    consistency_raw[str(driver).lower()] = float(np.std(sample))
                if "Stint" in group.columns:
                    stint_raw[str(driver).lower()] = float(group.groupby("Stint").size().max())

            # We use driver code keys. Jolpica driver ids are different, so these are exposed in debug.
            scores["fastf1_race_pace"].update(normalize_scores(pace_raw, reverse=True))
            scores["fastf1_consistency"].update(normalize_scores(consistency_raw, reverse=True))
            scores["fastf1_tyre_stint"].update(normalize_scores(stint_raw))
        except Exception as error:
            print(f"FastF1 score extraction failed for {code}: {error}")
    return scores


def driver_code_guess(name):
    parts = str(name or "").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][:3]).lower()
    return str(name or "").lower()[:4]


def get_prediction_stage(current_round_data, event_start):
    has_qualifying = bool(current_round_data.get("qualifying"))
    has_results = bool(current_round_data.get("results"))
    now = now_local()
    if has_results and now > event_start:
        return "post-race-data", "Post-race data, historical update"
    if has_qualifying:
        return "post-qualifying", "Post-qualifying prediction"
    if event_start - now <= timedelta(days=3):
        return "race-weekend", "Race-weekend prediction"
    return "pre-weekend", "Pre-weekend prediction"


def get_prediction_weights(profile, weather_summary, stage):
    overtaking = str(profile.get("overtaking", "unknown")).lower()
    tyre = str(profile.get("tyre_stress", "unknown")).lower()
    dominance = str(profile.get("dominance", "")).lower()
    speed = str(profile.get("speed_profile", "")).lower()

    rain = weather_summary.get("rain_score", 0)
    heat = weather_summary.get("heat_score", 0)
    wind = weather_summary.get("wind_score", 0)

    weights = {
        "ml_win_probability": 0.09,
        "ml_podium_probability": 0.13,
        "ml_top10_probability": 0.07,
        "driver_form": 0.10,
        "car_performance": 0.11,
        "recent_result": 0.06,
        "qualifying": 0.09,
        "circuit_history": 0.09,
        "race_pace": 0.08,
        "pit_execution": 0.05,
        "team_strategy": 0.06,
        "reliability": 0.04,
        "team_track_fit": 0.05,
        "weather_adaptation": 0.04,
        "fastf1_race_pace": 0.08,
        "fastf1_consistency": 0.03,
        "fastf1_tyre_stint": 0.03,
    }

    if stage == "post-qualifying":
        weights["qualifying"] += 0.08
        weights["ml_podium_probability"] += 0.03
    elif stage == "race-weekend":
        weights["fastf1_race_pace"] += 0.05
        weights["fastf1_consistency"] += 0.03
    elif stage == "pre-weekend":
        weights["driver_form"] += 0.04
        weights["car_performance"] += 0.04
        weights["circuit_history"] += 0.03

    if "low" in overtaking:
        weights["qualifying"] += 0.08
        weights["pit_execution"] += 0.03
        weights["team_strategy"] += 0.03
    if "good" in overtaking:
        weights["race_pace"] += 0.05
        weights["team_strategy"] += 0.03
    if tyre in {"high", "medium-high"} or heat >= 60:
        weights["race_pace"] += 0.04
        weights["pit_execution"] += 0.03
        weights["fastf1_tyre_stint"] += 0.03
    if rain >= 35:
        weights["reliability"] += 0.06
        weights["weather_adaptation"] += 0.07
        weights["team_strategy"] += 0.04
    if wind >= 60:
        weights["reliability"] += 0.03
        weights["weather_adaptation"] += 0.03
    if "straight-line" in speed or "aero" in dominance:
        weights["car_performance"] += 0.04
        weights["team_track_fit"] += 0.04

    for k in list(weights):
        weights[k] = max(0, weights[k])
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def rank_prediction(drivers, constructor_standings, last_results, current_round_data, historical_records, profile, weather_summary, ml_outputs, fastf1_scores, stage):
    weights = get_prediction_weights(profile, weather_summary, stage)

    driver_points_raw = {d["driver_id"]: d["points"] for d in drivers}
    driver_form = normalize_scores(driver_points_raw)
    constructor_scores = constructor_score_map(constructor_standings)
    recent_scores = current_result_score_map(last_results)
    qualifying_scores = qualifying_score_map(current_round_data)
    circuit_scores = circuit_history_score_map(historical_records)
    race_pace = race_pace_score_map(historical_records, current_round_data)
    driver_pit, constructor_pit = pit_execution_score_maps(historical_records, current_round_data)
    driver_strategy, constructor_strategy = strategy_gain_score_maps(historical_records)
    reliability = reliability_score_map(historical_records)
    constructor_circuit = constructor_circuit_history_score_map(historical_records)

    predictions = []

    for driver in drivers:
        driver_id = driver["driver_id"]
        team = driver["team"]
        code_key = driver_code_guess(driver["name"])

        car_performance = weighted_average([(constructor_scores.get(team), 0.70), (constructor_circuit.get(team), 0.30)])
        pit_execution = weighted_average([(driver_pit.get(driver_id), 0.45), (constructor_pit.get(team), 0.55)])
        team_strategy = weighted_average([(driver_strategy.get(driver_id), 0.45), (constructor_strategy.get(team), 0.40), (constructor_pit.get(team), 0.15)])
        track_fit = team_track_fit_score(team, profile, constructor_circuit.get(team))
        weather_adaptation = weighted_average([
            (reliability.get(driver_id), 0.35),
            (circuit_scores.get(driver_id), 0.30),
            (race_pace.get(driver_id), 0.20),
            (team_strategy, 0.15),
        ])
        ml = ml_outputs.get(driver_id, {})

        component_scores = {
            "ml_win_probability": ml.get("ml_win_probability"),
            "ml_podium_probability": ml.get("ml_podium_probability"),
            "ml_top10_probability": ml.get("ml_top10_probability"),
            "driver_form": driver_form.get(driver_id),
            "car_performance": car_performance,
            "recent_result": recent_scores.get(driver_id),
            "qualifying": qualifying_scores.get(driver_id),
            "circuit_history": circuit_scores.get(driver_id),
            "race_pace": race_pace.get(driver_id),
            "pit_execution": pit_execution,
            "team_strategy": team_strategy,
            "reliability": reliability.get(driver_id),
            "team_track_fit": track_fit,
            "weather_adaptation": weather_adaptation,
            "fastf1_race_pace": fastf1_scores.get("fastf1_race_pace", {}).get(code_key),
            "fastf1_consistency": fastf1_scores.get("fastf1_consistency", {}).get(code_key),
            "fastf1_tyre_stint": fastf1_scores.get("fastf1_tyre_stint", {}).get(code_key),
        }

        score = weighted_average([(component_scores.get(k), w) for k, w in weights.items()])
        if score is None:
            score = 0
        available_weight = sum(w for k, w in weights.items() if component_scores.get(k) is not None)
        confidence = min(100, max(0, available_weight * 100))

        sorted_reasons = sorted(
            [(k, v) for k, v in component_scores.items() if v is not None],
            key=lambda item: item[1] * weights.get(item[0], 0),
            reverse=True,
        )
        reason_names = [PREDICTION_LABELS.get(k, k.replace("_", " ")) for k, v in sorted_reasons[:5] if v >= 35]
        if not reason_names:
            reason_names = ["limited free-data evidence"]

        predictions.append({
            "name": driver["name"],
            "team": team,
            "driver_id": driver_id,
            "score": round(score, 2),
            "confidence": round(confidence, 1),
            "reason": "; ".join(reason_names),
            "component_scores": {k: (round(v, 2) if v is not None else None) for k, v in component_scores.items()},
            "image": None,
            "team_colour": None,
        })

    predictions.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)
    top10 = predictions[:10]
    text = "\n".join(
        f"{idx}. {item['name']}, score {item['score']:.1f}, confidence {item['confidence']:.0f}%, {item['reason']}"
        for idx, item in enumerate(top10, start=1)
    )

    model = {
        "source": "Hybrid free-data ML ensemble: Jolpica + FastF1 + Open-Meteo + ICS",
        "logic": "Mintlify-style feature groups plus local free-data ensemble: grid, driver history, team form, circuit experience, weather, tyre strategy, race pace, pit execution, and race simulation scenarios",
        "prediction_stage": stage,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "available_components": {
            "ml_outputs": len(ml_outputs),
            "driver_form": len(driver_form),
            "constructor_form": len(constructor_scores),
            "recent_result": len(recent_scores),
            "qualifying": len(qualifying_scores),
            "circuit_history": len(circuit_scores),
            "race_pace": len(race_pace),
            "driver_pit_execution": len(driver_pit),
            "constructor_pit_execution": len(constructor_pit),
            "driver_strategy": len(driver_strategy),
            "constructor_strategy": len(constructor_strategy),
            "reliability": len(reliability),
            "constructor_circuit_history": len(constructor_circuit),
            "fastf1_sessions_loaded": fastf1_scores.get("sessions_loaded", []),
        },
    }
    return text, top10, model


def get_dynamic_team_fit(top10, constructor_standings):
    scores = {}
    constructor_scores = constructor_score_map(constructor_standings)
    for team, score in constructor_scores.items():
        scores[team] = scores.get(team, 0) + score * 0.45
    for index, item in enumerate(top10):
        team = item.get("team") or "Unknown Team"
        scores[team] = scores.get(team, 0) + (10 - index) * 8
    return [team for team, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]]


def pit_window_from_profile(profile, weather_summary):
    rain_score = weather_summary.get("rain_score", 0)
    tyre_stress = profile.get("tyre_stress", "unknown")
    if rain_score >= 50:
        return "Delay fixed dry-tyre stops. Watch radar and react to rain onset."
    if tyre_stress == "high":
        return "Lap 14-24 for aggressive two-stop, lap 22-32 for conservative one-stop."
    if tyre_stress == "medium-high":
        return "Lap 16-28, with safety car flexibility."
    if tyre_stress == "medium":
        return "Lap 18-32 for normal dry strategy."
    if tyre_stress == "low-medium":
        return "Lap 24-40 if track position is secure."
    return "Unavailable until pit-stop history improves."


# -----------------------------
# Briefing, files, email, GitHub
# -----------------------------

def generate_briefing(event, race, profile, weather_summary, top10_text, prediction_model, team_fit):
    start_str = event["start"].strftime("%A, %d %B %Y, %I:%M %p %Z")
    title = f"F1 Briefing: {event['title']}"
    reasons = profile["dynamic_reasons"]
    metrics = profile["dynamic_track_metrics"]
    pit_window = pit_window_from_profile(profile, weather_summary)

    weights_text = "\n".join(
        f"- {key.replace('_', ' ')}: {value * 100:.1f}%"
        for key, value in prediction_model.get("weights", {}).items()
    )

    briefing = f"""# {title}

Generated: {now_local().strftime("%A, %d %B %Y, %I:%M %p %Z")}

## 1. Grand Prix overview

- Event: {event['title']}
- Start time: {start_str}
- Calendar location: {event['location'] or 'Not provided'}
- Jolpica race: {profile['race_name']}
- Circuit: {profile['circuit']}
- City and country: {profile['city']}, {profile['country']}
- Track type: {profile['track_type']}
- Overtaking level: {profile['overtaking']}
- Safety car likelihood: {profile['safety_car']}

## 2. Weather briefing

- Weather source: {weather_summary['source']}
- Air temperature: {weather_summary['temperature']}
- Track temperature: {weather_summary['track_temperature']}
- Rain: {weather_summary['rain']}
- Humidity: {weather_summary['humidity']}
- Wind: {weather_summary['wind']}
- Strategy impact: {weather_summary['impact']}

## 3. Dynamic track model

- Dominance: {profile['dominance']}
- Speed profile: {profile['speed_profile']} ({reasons['speed_profile']})
- Tyre stress: {profile['tyre_stress']} ({reasons['tyre_stress']})
- Overtaking: {profile['overtaking']} ({reasons['overtaking']})
- Safety car: {profile['safety_car']} ({reasons['safety_car']})
- Strategy bias: {profile['strategy_bias']}

## 3A. Data source audit

- Source: {profile['dynamic_track_source']['source']}
- Historical races sampled: {metrics['historical_races_sampled']}
- Results sampled: {metrics['results_sampled']}
- Qualifying rows sampled: {metrics['qualifying_rows_sampled']}
- Pit stops sampled: {metrics['pitstops_sampled']}
- Average overtake delta: {metrics['average_overtake_delta']}
- Average stops per driver: {metrics['average_stops_per_driver']}
- Prediction stage: {prediction_model.get('prediction_stage_label', prediction_model.get('prediction_stage', 'Unknown'))}

## 4. Team advantage estimate

{chr(10).join([f"- {idx + 1}. {team}" for idx, team in enumerate(team_fit)]) if team_fit else "- Unavailable until standings data is available"}

## 5. Tyre strategy

- Baseline strategy: {profile['strategy_bias']}
- Safest dry approach: conservative one-stop if degradation data stays controlled.
- Aggressive dry approach: early undercut or two-stop if tyre stress rises.
- Wet-weather adjustment: if rain probability rises, delay fixed dry-compound plans.
- Pit window: {pit_window}

## 6. Pit stop strategy

- Likely number of stops: inferred from historical pit-stop data where available.
- Safety car response: pit if the loss is lower and track position can be retained.
- Virtual safety car response: pit if tyre age is near the planned window.
- Avoid pitting into traffic, especially where overtaking is low.

## 7. Setup direction

{profile['setup']}

## 8. Potential top 10 prediction

Prediction status: dynamic but not guaranteed. This hybrid model combines Mintlify-style F1 ML feature groups with free data from Jolpica, FastF1, Open-Meteo, and your ICS calendar. It uses driver history, grid/qualifying, car and team form, circuit experience, weather, tyre strategy, race pace, pit execution, reliability, and race-simulation scenario logic.

{top10_text if top10_text else "Unavailable until standings/session data is available."}

## 8A. Prediction model weights

{weights_text}

## 9. What to watch

- Whether current-round qualifying becomes available before race start.
- Whether weather changes alter the first pit window.
- Whether circuit history suggests track position or race pace matters more.
- Whether constructor form matches the circuit demand.
- Whether pit execution and strategy gain change the final race order.

---

Generated by the free hybrid F1 briefing bot.
"""
    return title, briefing


def save_markdown(event, briefing):
    BRIEFINGS_DIR.mkdir(exist_ok=True)
    date_part = event["start"].strftime("%Y-%m-%d")
    slug = make_slug(event["title"])
    path = BRIEFINGS_DIR / f"{date_part}-{slug}.md"
    path.write_text(briefing, encoding="utf-8")
    return path


def save_run_status(status, details):
    BRIEFINGS_DIR.mkdir(exist_ok=True)
    path = BRIEFINGS_DIR / "latest-run-status.md"
    content = f"""# F1 Briefing Bot Run Status

Generated: {now_local().strftime("%A, %d %B %Y, %I:%M %p %Z")}

Status: {status}

## Details

{details}
"""
    path.write_text(content, encoding="utf-8")
    return path


def update_index(event, race, profile, weather_summary, markdown_path, title, top10, team_fit, prediction_model):
    BRIEFINGS_DIR.mkdir(exist_ok=True)
    index_path = BRIEFINGS_DIR / "index.json"

    entry = {
        "title": title,
        "path": str(markdown_path.relative_to(BASE_DIR)).replace("\\", "/"),
        "generated": now_local().strftime("%Y-%m-%d %H:%M %Z"),
        "generated_iso": now_local().isoformat(),
        "start_iso": event["start"].isoformat(),
        "start": event["start"].strftime("%A, %d %B %Y, %I:%M %p %Z"),
        "event_title": event["title"],
        "location": event["location"],
        "jolpica_race": race,
        "circuit": profile["circuit"],
        "city": profile["city"],
        "country": profile["country"],
        "circuit_key": profile.get("circuit_key"),
        "meeting_key": profile.get("meeting_key"),
        "track_type": profile["track_type"],
        "dominance": profile["dominance"],
        "speed_profile": profile["speed_profile"],
        "overtaking": profile["overtaking"],
        "tyre_stress": profile["tyre_stress"],
        "safety_car": profile["safety_car"],
        "strategy_bias": profile["strategy_bias"],
        "pit_window": pit_window_from_profile(profile, weather_summary),
        "setup": profile["setup"],
        "team_fit": team_fit,
        "weather": weather_summary,
        "top10": top10,
        "prediction_model": prediction_model,
        "dynamic_track_source": profile["dynamic_track_source"],
        "dynamic_track_metrics": profile["dynamic_track_metrics"],
        "dynamic_reasons": profile["dynamic_reasons"],
    }

    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            briefings = data.get("briefings", []) if isinstance(data, dict) else data
            if not isinstance(briefings, list):
                briefings = []
        except json.JSONDecodeError:
            briefings = []
    else:
        briefings = []

    briefings = [item for item in briefings if item.get("path") != entry["path"]]
    briefings.insert(0, entry)
    briefings = briefings[:60]
    index_path.write_text(json.dumps({"briefings": briefings}, indent=2, ensure_ascii=False), encoding="utf-8")
    return index_path


def save_debug(payload):
    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_CACHE_DIR / "latest-model-debug.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def send_email(subject, body):
    if not EMAIL_ENABLED:
        print("Email disabled.")
        return False
    try:
        message = MIMEMultipart("alternative")
        message["From"] = EMAIL_ADDRESS
        message["To"] = EMAIL_TO
        message["Subject"] = subject

        message.attach(MIMEText(body, "plain", "utf-8"))
        html_body = "<html><body style='font-family:Arial,sans-serif;line-height:1.55;background:#050505;color:#f5f0ea;padding:24px;'>" + \
            "<pre style='white-space:pre-wrap;font-family:Arial,sans-serif'>" + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre></body></html>"
        message.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.send_message(message)
        print("Email sent.")
        return True
    except Exception as error:
        print(f"Email failed, but workflow will continue: {error}")
        return False


def github_api(method, endpoint, payload=None):
    if not GITHUB_REPOSITORY or not GITHUB_TOKEN:
        print("GitHub API variables missing. Skipping issue update.")
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}{endpoint}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.request(method, url, headers=headers, json=payload, timeout=30)
    if response.status_code >= 400:
        print(f"GitHub API error {response.status_code}: {response.text}")
        response.raise_for_status()
    return response.json() if response.text else None


def ensure_issue_label():
    try:
        github_api("POST", "/labels", {"name": "f1-briefing", "description": "Automated F1 briefing", "color": "e10600"})
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 422:
            return
        raise


def create_or_update_issue(title, body):
    ensure_issue_label()
    existing = github_api("GET", "/issues?state=open&labels=f1-briefing&per_page=100")
    if existing:
        for issue in existing:
            if issue.get("title") == title:
                number = issue["number"]
                github_api("PATCH", f"/issues/{number}", {"body": body})
                print(f"Updated issue #{number}.")
                return
    github_api("POST", "/issues", {"title": title, "body": body, "labels": ["f1-briefing"]})
    print("Created issue.")


def commit_and_push(paths):
    paths = [Path(path) for path in paths if path]
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)

    for path in paths:
        if path.exists():
            subprocess.run(["git", "add", str(path)], check=True)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("No file changes to commit.")
        return

    subprocess.run(["git", "commit", "-m", "Update F1 briefing data and ML model"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("Committed and pushed briefing data.")


def write_skip_outputs(subject, details):
    status_path = save_run_status("Skipped", details)
    safe_step("Commit status file", commit_and_push, [status_path])
    safe_step("Create or update status issue", create_or_update_issue, "F1 Briefing Bot Status", details)
    safe_step("Send status email", send_email, subject, details)


# -----------------------------
# Main
# -----------------------------

def run(force_retrain=False):
    ensure_dirs()
    require_env_vars()

    bundle = safe_step("Train or load ML model", train_ml_model, force_retrain)
    if not bundle:
        bundle = load_ml_bundle()

    calendar = fetch_ics_calendar()
    event = find_next_calendar_event(calendar)
    if not event:
        details = f"No F1 event found in the next {LOOKAHEAD_DAYS} days."
        print(details)
        write_skip_outputs("F1 Briefing Bot: Skipped", details)
        return

    race = find_best_race(event)
    if not race:
        details = (
            "Found a calendar event, but no matching Jolpica race was found.\n\n"
            f"Calendar event: {event['title']}\n"
            f"Start: {event['start']}\n"
            f"Location: {event.get('location', 'Not provided')}"
        )
        print(details)
        write_skip_outputs("F1 Briefing Bot: Jolpica Race Not Found", details)
        return

    season = safe_int(race.get("season")) or event["start"].year
    round_no = race.get("round")

    driver_standings = fetch_driver_standings(season)
    constructor_standings = fetch_constructor_standings(season)
    last_results = fetch_last_results(season)
    current_round_data = fetch_round_data(season, round_no) if round_no else {"results": [], "qualifying": [], "pitstops": [], "laps": []}
    historical_records = fetch_historical_same_circuit(race, years_back=4)

    if not driver_standings:
        details = (
            "Matched a Jolpica race, but driver standings were not available.\n\n"
            f"Race: {race.get('raceName')}\n"
            f"Season: {season}\n"
            f"Round: {round_no}"
        )
        print(details)
        write_skip_outputs("F1 Briefing Bot: Driver Standings Missing", details)
        return

    drivers = standings_to_drivers(driver_standings)
    weather_summary = fetch_weather_for_race(race, event["start"])
    historical_weather = safe_step("Fetch historical weather", fetch_historical_weather_summary, race, 3) or {}
    profile = infer_track_profile(race, historical_records, weather_summary, historical_weather)

    stage, stage_label = get_prediction_stage(current_round_data, event["start"])

    ml_outputs, ml_debug = ml_predict_probabilities(drivers, race, current_round_data, bundle)
    fastf1_scores = safe_step("FastF1 enhancement", fastf1_enhancement_scores, season, round_no) or {"sessions_loaded": []}

    top10_text, top10, prediction_model = rank_prediction(
        drivers=drivers,
        constructor_standings=constructor_standings,
        last_results=last_results,
        current_round_data=current_round_data,
        historical_records=historical_records,
        profile=profile,
        weather_summary=weather_summary,
        ml_outputs=ml_outputs,
        fastf1_scores=fastf1_scores,
        stage=stage,
    )
    prediction_model["prediction_stage_label"] = stage_label
    prediction_model["ml_model_loaded"] = bool(bundle)
    prediction_model["ml_model_meta"] = {
        "trained_at": bundle.get("trained_at") if bundle else None,
        "latest_completed_race_id": bundle.get("latest_completed_race_id") if bundle else None,
        "metrics": bundle.get("metrics") if bundle else None,
    }

    team_fit = get_dynamic_team_fit(top10, constructor_standings)

    title, briefing = generate_briefing(
        event=event,
        race=race,
        profile=profile,
        weather_summary=weather_summary,
        top10_text=top10_text,
        prediction_model=prediction_model,
        team_fit=team_fit,
    )

    markdown_path = save_markdown(event, briefing)
    index_path = update_index(event, race, profile, weather_summary, markdown_path, title, top10, team_fit, prediction_model)
    status_path = save_run_status(
        "Success",
        f"Generated hybrid ML F1 briefing successfully.\n\nTitle: {title}\nMarkdown: {markdown_path}\nIndex: {index_path}\nPrediction stage: {stage_label}",
    )
    debug_path = save_debug({
        "generated_at": now_local().isoformat(),
        "event": event,
        "race": race,
        "prediction_model": prediction_model,
        "top10": top10,
        "weather": weather_summary,
        "historical_weather": historical_weather,
        "track_profile": profile,
        "ml_debug": ml_debug,
        "fastf1_scores": fastf1_scores,
    })

    paths = [markdown_path, index_path, status_path, debug_path, MODEL_BUNDLE_PATH, MODEL_META_PATH, DATA_CACHE_DIR / "ml_race_results_raw.csv", DATA_CACHE_DIR / "ml_race_features.csv"]
    safe_step("Commit briefing/model files", commit_and_push, paths)
    safe_step("Create or update issue", create_or_update_issue, title, briefing)
    safe_step("Send email", send_email, title, briefing)


def parse_args():
    parser = argparse.ArgumentParser(description="Hybrid free-data F1 briefing and ML prediction bot.")
    parser.add_argument("--force-retrain", action="store_true", help="Force retraining of the ML model.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    force = args.force_retrain or os.getenv("FORCE_RETRAIN", "false").lower() == "true"
    run(force_retrain=force)
