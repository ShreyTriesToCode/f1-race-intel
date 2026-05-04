import os
import re
import json
import time
import gzip
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
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

try:
    import fastf1
except Exception:
    fastf1 = None


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
FINAL_RESULTS_DELAY_HOURS = int(os.getenv("FINAL_RESULTS_DELAY_HOURS", "8"))
NOTIFICATION_WINDOW_HOURS = int(os.getenv("NOTIFICATION_WINDOW_HOURS", "8"))
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "false").lower() == "true"
OUTPUT_MODE = os.getenv("OUTPUT_MODE", "auto").lower().strip()
GITHUB_EVENT_NAME = os.getenv("GITHUB_EVENT_NAME", "").lower().strip()

ML_START_YEAR = int(os.getenv("ML_START_YEAR", "2018"))
USE_FULL_HISTORICAL_DATA = os.getenv("USE_FULL_HISTORICAL_DATA", "true").lower() == "true"
FULL_DATA_BACKFILL_LIMIT = int(os.getenv("FULL_DATA_BACKFILL_LIMIT", "10"))
JOLPICA_REQUEST_SLEEP = float(os.getenv("JOLPICA_REQUEST_SLEEP", "1.2"))

BASE_DIR = Path(__file__).resolve().parent
BRIEFINGS_DIR = BASE_DIR / "briefings"
DATA_CACHE_DIR = BASE_DIR / "data_cache"
HTTP_CACHE_DIR = Path(os.getenv("HTTP_CACHE_DIR", DATA_CACHE_DIR / "http"))
FULL_RACE_CACHE_DIR = Path(os.getenv("FULL_RACE_CACHE_DIR", DATA_CACHE_DIR / "full_races"))
FASTF1_CACHE_DIR = Path(os.getenv("FASTF1_CACHE_DIR", BASE_DIR / "fastf1_cache"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "models" / "saved_models"))

MODEL_BUNDLE_PATH = MODEL_DIR / "f1_hybrid_full_data_bundle.pkl"
MODEL_META_PATH = MODEL_DIR / "f1_hybrid_full_data_meta.json"

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
OPENF1_BASE = os.getenv("OPENF1_BASE", "https://api.openf1.org/v1").rstrip("/")
OPENF1_ENABLED = os.getenv("OPENF1_ENABLED", "true").lower() == "true"
UPGRADES_ENABLED = os.getenv("UPGRADES_ENABLED", "true").lower() == "true"
F1_REGULATIONS_ENABLED = os.getenv("F1_REGULATIONS_ENABLED", "true").lower() == "true"
OFFICIAL_CALENDAR_ENABLED = os.getenv("OFFICIAL_CALENDAR_ENABLED", "true").lower() == "true"
FIA_TECH_UPDATE_BASE = os.getenv("FIA_TECH_UPDATE_BASE", "https://www.fia.com/news").rstrip("/")
OFFICIAL_F1_CALENDAR_URL = os.getenv("OFFICIAL_F1_CALENDAR_URL", "https://www.formula1.com/en/racing/{year}")
UPGRADE_NEWS_URLS = [u.strip() for u in os.getenv("UPGRADE_NEWS_URLS", "").split(",") if u.strip()]
JOLPICA_HEADERS = {
    "User-Agent": "f1-race-intel/3.0 cache-first full-data model",
    "Accept": "application/json",
}

FASTF1_SESSION_ORDER = ["R", "Q", "SQ", "S", "FP3", "FP2", "FP1"]

PREDICTION_LABELS = {
    "ml_win_probability": "ML win probability",
    "ml_podium_probability": "ML podium probability",
    "ml_top10_probability": "ML top 10 probability",
    "driver_form": "driver form",
    "driver_skill": "driver skill profile",
    "car_performance": "car performance",
    "constructor_form": "constructor form",
    "recent_result": "recent race result",
    "qualifying": "qualifying and grid position",
    "circuit_history": "same-circuit history",
    "race_pace": "historical lap pace",
    "pit_execution": "pit-stop execution",
    "team_strategy": "team strategy gain",
    "reliability": "reliability",
    "team_track_fit": "team-track fit",
    "weather_adaptation": "weather adaptation",
    "track_trait_fit": "track trait fit",
    "sprint_performance": "sprint performance",
    "current_season_car_performance": "current-season car performance",
    "current_season_recent_form": "current-season recent constructor form",
    "openf1_session_result": "OpenF1 session result",
    "openf1_starting_grid": "OpenF1 starting grid",
    "openf1_lap_pace": "OpenF1 lap pace",
    "openf1_pit_execution": "OpenF1 pit execution",
    "openf1_stint_strength": "OpenF1 stint strength",
    "openf1_telemetry_speed": "OpenF1 telemetry speed",
    "openf1_car_performance": "OpenF1 car performance",
    "upgrade_package_impact": "official upgrade package impact",
    "regulation_fit": "regulation-era fit",
    "calendar_confidence": "official calendar confidence",
    "fastf1_race_pace": "FastF1 clean-lap pace",
    "fastf1_consistency": "FastF1 consistency",
    "fastf1_tyre_stint": "FastF1 tyre/stint evidence",
}


class BackfillBudget:
    def __init__(self, limit):
        self.limit = int(limit)
        self.used = 0
        self.fetched = []

    def can_fetch(self):
        return self.used < self.limit

    def mark(self, key):
        self.used += 1
        self.fetched.append(key)


BACKFILL_BUDGET = BackfillBudget(FULL_DATA_BACKFILL_LIMIT)


def ensure_dirs():
    for path in [BRIEFINGS_DIR, DATA_CACHE_DIR, HTTP_CACHE_DIR, FULL_RACE_CACHE_DIR, FASTF1_CACHE_DIR, MODEL_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def now_local():
    return datetime.now(USER_TIMEZONE)


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
    total = 0.0
    weight_sum = 0.0
    for value, weight in items:
        value = safe_float(value)
        if value is None:
            continue
        total += value * weight
        weight_sum += weight
    return total / weight_sum if weight_sum else None


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
            out[key] = 75.0
        elif reverse:
            out[key] = max(0.0, min(100.0, (high - value) / (high - low) * 100.0))
        else:
            out[key] = max(0.0, min(100.0, (value - low) / (high - low) * 100.0))
    return out


def normalize_name(name):
    text = str(name or "").replace("_", " ").strip()
    return " ".join(part.capitalize() if part.isupper() else part for part in text.split())


def make_slug(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:100] or "f1"


def score_position(position, field_size=22):
    position = safe_int(position)
    if position is None or position <= 0:
        return None
    return max(0.0, 100.0 * (field_size - position) / max(1, field_size - 1))


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


def safe_step(name, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as error:
        print(f"{name} failed, continuing: {error}")
        return None


def cache_key_for_url(url, params=None):
    return make_slug(url + "?" + json.dumps(params or {}, sort_keys=True))


def polite_sleep():
    if JOLPICA_REQUEST_SLEEP > 0:
        time.sleep(JOLPICA_REQUEST_SLEEP)


def safe_get(url, params=None, timeout=30, headers=None, optional_404=False, use_cache=True):
    ensure_dirs()
    cache_path = HTTP_CACHE_DIR / f"{cache_key_for_url(url, params)}.json"

    if use_cache and cache_path.exists():
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < 12 * 3600:
                fake = requests.Response()
                fake.status_code = 200
                fake._content = cache_path.read_bytes()
                return fake
        except Exception:
            pass

    for attempt in range(4):
        try:
            response = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)

            if response.status_code == 404 and optional_404:
                print(f"Optional endpoint not available: {url}")
                return None

            if response.status_code == 429:
                wait = 5 + attempt * 5
                print(f"Rate limited. Waiting {wait}s before retry.")
                time.sleep(wait)
                continue

            response.raise_for_status()

            if use_cache and "json" in response.headers.get("content-type", "").lower():
                cache_path.write_bytes(response.content)

            return response
        except Exception as error:
            print(f"GET failed: {url} params={params} attempt={attempt + 1}/4 error={error}")
            if attempt < 3:
                time.sleep(2 + attempt * 2)

    return None


def jolpica_get(endpoint, params=None, optional_404=False):
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    if not endpoint.endswith(".json"):
        endpoint += ".json"

    polite_sleep()
    response = safe_get(JOLPICA_BASE + endpoint, params=params, headers=JOLPICA_HEADERS, optional_404=optional_404)
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
    except Exception:
        return {}


def fetch_schedule(year):
    return mrdata_list(jolpica_get(f"/{year}"), "RaceTable", "Races")


def parse_race_datetime(race):
    date = race.get("date")
    time_value = race.get("time") or "00:00:00Z"
    if not date:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{time_value}".replace("Z", "+00:00")).astimezone(USER_TIMEZONE)
    except ValueError:
        return None


def final_results_cutoff(race):
    race_dt = parse_race_datetime(race)
    if race_dt is None:
        return None
    return race_dt + timedelta(hours=FINAL_RESULTS_DELAY_HOURS)


def is_race_past_calendar_cutoff(race):
    cutoff = final_results_cutoff(race)
    return bool(cutoff and now_local() >= cutoff)


def is_race_future_or_not_final_yet(race):
    return not is_race_past_calendar_cutoff(race)


def race_has_results(data):
    try:
        races = data.get("results", [])
        return bool(races and races[0].get("Results"))
    except AttributeError:
        return False


def cache_status_for_race(race, data):
    if race_has_results(data):
        return "final_results_available"
    if race is not None and is_race_past_calendar_cutoff(race):
        return "past_calendar_no_results_yet"
    return "future_or_partial"


def should_use_cached_round(cached, race=None, require_final_if_past=False):
    if not cached:
        return False

    data = cached.get("data", {})
    status = cached.get("status")

    if race is None:
        return True

    if require_final_if_past and is_race_past_calendar_cutoff(race):
        # Old caches may not have a status field. For past races, trust only caches with race results.
        return race_has_results(data)

    if status == "future_or_partial" and is_race_past_calendar_cutoff(race):
        # A race cached before it happened must be refreshed after the GP.
        return False

    return True


def full_race_cache_path(season, round_no):
    return FULL_RACE_CACHE_DIR / f"{season}-{round_no}.json.gz"


def read_full_race_cache(season, round_no):
    path = full_race_cache_path(season, round_no)
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception as error:
        print(f"Could not read full race cache {path}: {error}")
        return None


def write_full_race_cache(season, round_no, payload):
    path = full_race_cache_path(season, round_no)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def fetch_round_data_direct(season, round_no):
    return {
        "results": mrdata_list(jolpica_get(f"/{season}/{round_no}/results"), "RaceTable", "Races"),
        "qualifying": mrdata_list(jolpica_get(f"/{season}/{round_no}/qualifying", optional_404=True), "RaceTable", "Races"),
        "pitstops": mrdata_list(jolpica_get(f"/{season}/{round_no}/pitstops", optional_404=True), "RaceTable", "Races"),
        "laps": mrdata_list(jolpica_get(f"/{season}/{round_no}/laps", optional_404=True), "RaceTable", "Races"),
        "sprint": mrdata_list(jolpica_get(f"/{season}/{round_no}/sprint", optional_404=True), "RaceTable", "Races"),
        "sprint_qualifying": mrdata_list(
            jolpica_get(f"/{season}/{round_no}/sprint/qualifying", optional_404=True),
            "RaceTable",
            "Races",
        ),
    }


def fetch_round_data_cached(season, round_no, allow_backfill=True, force_fetch=False, race=None, training_mode=False):
    """
    Cache-first full race loader.

    Rules:
    1. Historical ML training uses only races whose scheduled GP time plus FINAL_RESULTS_DELAY_HOURS has passed.
    2. A race is used for ML training only when race results exist.
    3. Future GPs may still be fetched for prediction/session context when force_fetch=True, but they are not used as final training rows.
    4. If a race was cached before it had results, it is refreshed after the GP cutoff.
    """
    cached = read_full_race_cache(season, round_no)

    if cached and not force_fetch and should_use_cached_round(cached, race=race, require_final_if_past=training_mode):
        data = cached.get("data", {})
        if training_mode and not race_has_results(data):
            return {}
        return data

    key = f"{season}-{round_no}"

    if race is not None and training_mode and is_race_future_or_not_final_yet(race):
        print(f"Skipping future/not-final GP for training cache: {key}")
        return {}

    if allow_backfill and not force_fetch and not BACKFILL_BUDGET.can_fetch():
        print(f"Full-data backfill limit reached. Skipping uncached historical race {key}.")
        return {}

    print(f"Fetching full round data for {key}")
    data = fetch_round_data_direct(season, round_no)
    status = cache_status_for_race(race, data) if race is not None else ("final_results_available" if race_has_results(data) else "unknown")

    # Avoid storing empty future training files as if they were complete history.
    if training_mode and status == "future_or_partial":
        print(f"Not caching future/partial training race: {key}")
        return {}

    payload = {
        "season": season,
        "round": str(round_no),
        "fetched_at": now_local().isoformat(),
        "status": status,
        "final_results_delay_hours": FINAL_RESULTS_DELAY_HOURS,
        "data": data,
    }
    write_full_race_cache(season, round_no, payload)

    if allow_backfill and not force_fetch:
        BACKFILL_BUDGET.mark(key)

    if training_mode and not race_has_results(data):
        return {}

    return data


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


def fetch_ics_calendar():
    url = F1_ICS_URL.strip().strip('"').strip("'")
    if url.startswith("webcal://"):
        url = "https://" + url.replace("webcal://", "", 1)
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("F1_ICS_URL must be a normal HTTP URL.")
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
    events = get_f1_calendar_events(calendar)
    return events[0] if events else None


def get_f1_calendar_events(calendar):
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
        text_value = f"{title} {location} {description}".lower()

        if any(k in text_value for k in ["formula 1", "f1", "grand prix", "gp", "sprint", "race", "qualifying", "practice"]):
            if now <= start <= max_date:
                event = {
                    "title": title,
                    "location": location,
                    "description": description,
                    "start": start,
                    "end": end,
                }
                event["target_type"] = classify_output_target_event(event)
                events.append(event)

    events.sort(key=lambda item: item["start"])
    return events


def classify_output_target_event(event):
    """
    Output target classifier.

    Practice, Qualifying, Sprint Qualifying, Sprint Shootout, and Sprint Qualification
    are input signals only. They are never direct output targets.

    Only two target types are allowed in public output:
    - sprint race
    - final race
    """
    title = str(event.get("title", "")).lower()
    description = str(event.get("description", "")).lower()
    text_value = f"{title} {description}"

    input_only_markers = [
        "practice", "fp1", "fp2", "fp3",
        "qualifying", "qualification", "sprint qualifying",
        "sprint qualification", "sprint shootout", "shootout",
        "sq"
    ]

    if any(k in text_value for k in input_only_markers):
        return "input_only"

    # Sprint race, not sprint qualifying/qualification.
    if "sprint" in text_value:
        return "sprint"

    # Final race. A plain Grand Prix calendar event usually means Race.
    if "race" in text_value or "grand prix" in text_value or " gp" in text_value:
        return "race"

    return "input_only"


def is_output_target_event(event):
    return classify_output_target_event(event) in {"sprint", "race"}


def selected_output_mode():
    """
    workflow_dispatch/manual run: weekend output by default.
    schedule/automatic run: today-only output by default.
    Local runs default to weekend unless OUTPUT_MODE is explicitly set.
    """
    if OUTPUT_MODE in {"weekend", "today", "next"}:
        return OUTPUT_MODE

    if GITHUB_EVENT_NAME == "schedule":
        return "today"

    if GITHUB_EVENT_NAME == "workflow_dispatch":
        return "weekend"

    return "weekend"


def event_weekend_window(anchor_event):
    start = anchor_event["start"]
    # Covers Thu-Mon around normal and sprint weekends, while avoiding pulling the next GP.
    return start - timedelta(days=4), start + timedelta(days=2)


def events_match_same_race(a, b):
    """
    Uses Jolpica matching to group Sprint and Race from the same GP.
    Falls back to title token overlap if one match fails.
    """
    try:
        race_a = find_best_race(a)
        race_b = find_best_race(b)
        if race_a and race_b:
            return str(race_a.get("season")) == str(race_b.get("season")) and str(race_a.get("round")) == str(race_b.get("round"))
    except Exception:
        pass

    tokens_a = set(tokenize(a.get("title", "")))
    tokens_b = set(tokenize(b.get("title", "")))
    return len(tokens_a & tokens_b) >= 1


def select_output_events(calendar):
    """
    Returns Sprint/Race output targets only.

    Manual/weekend mode:
      Return Sprint and Race for the next race weekend in one briefing.
      If there is no Sprint event, return Race only.

    Scheduled/today mode:
      Return only today's Sprint or Race event(s).
      Practice and Qualifying are ignored as output targets.

    Next mode:
      Return the next single Sprint/Race target.
    """
    mode = selected_output_mode()
    events = get_f1_calendar_events(calendar)
    targets = [event for event in events if is_output_target_event(event)]
    now = now_local()

    if not targets:
        return mode, []

    if mode == "today":
        today_targets = [
            event for event in targets
            if event["start"].astimezone(USER_TIMEZONE).date() == now.date()
        ]
        today_targets.sort(key=lambda item: (0 if item["target_type"] == "sprint" else 1, item["start"]))
        return mode, today_targets

    if mode == "next":
        return mode, [targets[0]]

    # Weekend mode.
    next_race = next((event for event in targets if event["target_type"] == "race"), None)
    anchor_event = next_race or targets[0]
    start_window, end_window = event_weekend_window(anchor_event)

    weekend_targets = [
        event for event in targets
        if start_window <= event["start"] <= end_window and events_match_same_race(event, anchor_event)
    ]

    # Always order Sprint before Race in the combined weekend output.
    weekend_targets.sort(key=lambda item: (0 if item["target_type"] == "sprint" else 1, item["start"]))

    # Keep at most one sprint and one race target.
    deduped = []
    seen_types = set()
    for event in weekend_targets:
        target_type = event["target_type"]
        if target_type not in seen_types:
            deduped.append(event)
            seen_types.add(target_type)

    return mode, deduped


def make_report_event(events, mode):
    if not events:
        return None

    first = events[0]
    race = find_best_race(first)
    race_name = race.get("raceName") if race else first.get("title", "F1")

    if mode == "weekend" and len(events) > 1:
        title = f"F1 Weekend Briefing: {race_name} Sprint + Race"
    elif mode == "weekend":
        title = f"F1 Weekend Briefing: {race_name}"
    else:
        title = f"F1 Briefing: {first.get('title')}"

    return {
        "title": title,
        "location": first.get("location", ""),
        "description": " | ".join(event.get("title", "") for event in events),
        "start": min(event["start"] for event in events),
        "end": max((event.get("end") or event["start"]) for event in events),
        "target_type": "weekend" if len(events) > 1 else first.get("target_type"),
    }


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
    tokens = tokenize(f"{event['title']} {event['location']} {event['description']}")
    best = None
    best_score = -999
    for year in [event_year, event_year - 1]:
        for race in fetch_schedule(year):
            text = race_text(race)
            score = sum(6 for token in tokens if token in text)
            race_dt = parse_race_datetime(race)
            if race_dt:
                delta = abs((race_dt.date() - event["start"].date()).days)
                if year == event_year:
                    score += 8
                if delta <= 1:
                    score += 24
                elif delta <= 7:
                    score += 8
                else:
                    score -= min(delta, 30)
            if score > best_score:
                best = race
                best_score = score
    return best if best_score >= 5 else None


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
            "points": safe_float(row.get("points")) or 0.0,
            "position": safe_int(row.get("position")),
            "wins": safe_int(row.get("wins")) or 0,
            "image": None,
            "team_colour": None,
        })
    return drivers


def result_rows_from_race_data(season, round_no, race, data):
    rows = []
    result_races = data.get("results", [])
    if not result_races:
        return rows

    q_positions = {}
    q_races = data.get("qualifying", [])
    if q_races:
        for q in q_races[0].get("QualifyingResults", []):
            driver_id = q.get("Driver", {}).get("driverId")
            q_positions[driver_id] = safe_int(q.get("position"))

    sprint_positions = {}
    sprint_races = data.get("sprint", [])
    if sprint_races:
        for s in sprint_races[0].get("SprintResults", []) or sprint_races[0].get("Results", []):
            driver_id = s.get("Driver", {}).get("driverId")
            sprint_positions[driver_id] = safe_int(s.get("positionOrder") or s.get("position"))

    lap_metrics = driver_lap_metrics_from_data(data)
    pit_metrics = pit_metrics_from_data(data)

    race_id = f"{season}-{round_no}"
    circuit = race.get("Circuit", {})
    circuit_id = circuit.get("circuitId")
    race_dt = parse_race_datetime(race)

    for result in result_races[0].get("Results", []):
        driver = result.get("Driver", {})
        constructor = result.get("Constructor", {})
        driver_id = driver.get("driverId")
        team = constructor.get("name")
        pos = safe_int(result.get("positionOrder") or result.get("position"))
        grid = safe_int(result.get("grid"))
        status = str(result.get("status", ""))

        if not driver_id or not team or not pos:
            continue

        dm = lap_metrics.get(driver_id, {})
        pm = pit_metrics.get(driver_id, {})

        rows.append({
            "race_id": race_id,
            "season": season,
            "round": safe_int(round_no),
            "date": race_dt.isoformat() if race_dt else None,
            "race_name": race.get("raceName"),
            "circuit_id": circuit_id,
            "circuit_name": circuit.get("circuitName"),
            "driver_id": driver_id,
            "driver_name": driver_name(driver),
            "constructor": team,
            "grid": grid if grid and grid > 0 else q_positions.get(driver_id),
            "qualifying": q_positions.get(driver_id),
            "sprint_position": sprint_positions.get(driver_id),
            "finish_position": pos,
            "points": safe_float(result.get("points")) or 0.0,
            "status": status,
            "is_finished": 1 if ("Finished" in status or "+" in status) else 0,
            "is_win": 1 if pos == 1 else 0,
            "is_podium": 1 if pos <= 3 else 0,
            "is_top10": 1 if pos <= 10 else 0,
            "best_clean_lap": dm.get("best_lap"),
            "avg_best_35pct_lap": dm.get("avg_best_35pct"),
            "lap_consistency": dm.get("consistency"),
            "valid_laps": dm.get("valid_laps", 0),
            "pit_stop_count": pm.get("pit_stop_count", 0),
            "avg_pit_duration": pm.get("avg_pit_duration"),
            "min_pit_duration": pm.get("min_pit_duration"),
        })
    return rows


def driver_lap_metrics_from_data(data):
    raw = {}
    for race in data.get("laps", []) or []:
        for lap in race.get("Laps", []):
            for timing in lap.get("Timings", []):
                driver_id = timing.get("driverId")
                sec = parse_lap_time_to_seconds(timing.get("time"))
                if not driver_id or sec is None:
                    continue
                if 45 <= sec <= 180:
                    raw.setdefault(driver_id, []).append(sec)

    out = {}
    for driver_id, times in raw.items():
        if len(times) < 3:
            continue
        fastest = min(times)
        filtered = [x for x in times if x <= fastest + 7.0]
        filtered = sorted(filtered)
        if len(filtered) < 3:
            continue
        n = max(3, int(len(filtered) * 0.35))
        sample = filtered[:n]
        out[driver_id] = {
            "best_lap": fastest,
            "avg_best_35pct": average(sample),
            "consistency": float(np.std(sample)) if len(sample) > 1 else None,
            "valid_laps": len(filtered),
        }
    return out


def pit_metrics_from_data(data):
    raw = {}
    for race in data.get("pitstops", []) or []:
        for stop in race.get("PitStops", []):
            driver_id = stop.get("driverId")
            duration = safe_float(stop.get("duration"))
            if not driver_id or duration is None:
                continue
            if 1.5 <= duration <= 65:
                raw.setdefault(driver_id, []).append(duration)

    out = {}
    for driver_id, durations in raw.items():
        out[driver_id] = {
            "pit_stop_count": len(durations),
            "avg_pit_duration": average(durations),
            "min_pit_duration": min(durations) if durations else None,
        }
    return out


def track_traits_from_race_data(data):
    rows = []
    result_races = data.get("results", [])
    if result_races:
        for row in result_races[0].get("Results", []):
            grid = safe_int(row.get("grid"))
            finish = safe_int(row.get("positionOrder") or row.get("position"))
            status = str(row.get("status", "")).lower()
            rows.append({"grid": grid, "finish": finish, "status": status})

    overtake_moves = []
    dnf = 0
    finished = 0
    for row in rows:
        if row["grid"] and row["grid"] > 0 and row["finish"]:
            overtake_moves.append(abs(row["grid"] - row["finish"]))
        if "finished" in row["status"] or "+" in row["status"]:
            finished += 1
        else:
            dnf += 1

    pits = pit_metrics_from_data(data)
    pit_counts = [item.get("pit_stop_count", 0) for item in pits.values()]
    laps = driver_lap_metrics_from_data(data)
    consistency = [item.get("consistency") for item in laps.values() if item.get("consistency") is not None]

    return {
        "avg_grid_finish_movement": average(overtake_moves),
        "dnf_rate": dnf / max(1, dnf + finished),
        "avg_pit_stops": average(pit_counts),
        "avg_lap_consistency": average(consistency),
        "drivers_with_lap_data": len(laps),
        "drivers_with_pit_data": len(pits),
    }


def collect_race_rows(start_year, end_year):
    rows = []
    races_used = 0
    races_skipped_uncached = 0

    for year in range(start_year, end_year + 1):
        print(f"Collecting full historical rows for {year}")
        schedule = fetch_schedule(year)

        for race in schedule:
            round_no = race.get("round")
            if not round_no:
                continue

            data = fetch_round_data_cached(
                year,
                round_no,
                allow_backfill=True,
                force_fetch=False,
                race=race,
                training_mode=True,
            )

            if not data or not race_has_results(data):
                races_skipped_uncached += 1
                continue

            race_rows = result_rows_from_race_data(year, round_no, race, data)
            rows.extend(race_rows)
            races_used += 1

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["season", "round", "finish_position"]).reset_index(drop=True)

    print(f"Historical full-data races used: {races_used}; skipped/uncached this run: {races_skipped_uncached}; new backfilled: {BACKFILL_BUDGET.used}")
    return df


def create_ml_features(df):
    if df.empty:
        return df, []

    df = df.copy()
    numeric_cols = [
        "grid", "qualifying", "sprint_position", "finish_position", "points",
        "best_clean_lap", "avg_best_35pct_lap", "lap_consistency",
        "valid_laps", "pit_stop_count", "avg_pit_duration", "min_pit_duration"
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    df["grid"] = df["grid"].fillna(20)
    df["qualifying"] = df["qualifying"].fillna(df["grid"])
    df["sprint_position"] = df["sprint_position"].fillna(20)
    df["points"] = df["points"].fillna(0)
    df["pit_stop_count"] = df["pit_stop_count"].fillna(0)
    df["valid_laps"] = df["valid_laps"].fillna(0)

    feature_rows = []
    grouped_driver = {k: g.sort_values(["season", "round"]) for k, g in df.groupby("driver_id")}
    grouped_team = {k: g.sort_values(["season", "round"]) for k, g in df.groupby("constructor")}
    grouped_circuit_driver = {k: g.sort_values(["season", "round"]) for k, g in df.groupby(["circuit_id", "driver_id"])}
    grouped_circuit_team = {k: g.sort_values(["season", "round"]) for k, g in df.groupby(["circuit_id", "constructor"])}
    grouped_circuit = {k: g.sort_values(["season", "round"]) for k, g in df.groupby("circuit_id")}

    for _, race in df.iterrows():
        season = race["season"]
        round_no = race["round"]

        def before(frame):
            if frame is None or len(frame) == 0:
                return pd.DataFrame()
            return frame[(frame["season"] < season) | ((frame["season"] == season) & (frame["round"] < round_no))]

        d_hist = before(grouped_driver.get(race["driver_id"]))
        t_hist = before(grouped_team.get(race["constructor"]))
        cd_hist = before(grouped_circuit_driver.get((race["circuit_id"], race["driver_id"])))
        ct_hist = before(grouped_circuit_team.get((race["circuit_id"], race["constructor"])))
        c_hist = before(grouped_circuit.get(race["circuit_id"]))

        if len(d_hist) < 3 or len(t_hist) < 3:
            continue

        recent3 = d_hist.tail(3)
        recent5 = d_hist.tail(5)
        team_recent10 = t_hist.tail(10)

        def mean_or(frame, col, fallback):
            if len(frame) and col in frame:
                val = frame[col].mean()
                if pd.notna(val):
                    return float(val)
            return fallback

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
            "sprint_position": race["sprint_position"],

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
            "team_recent_points": team_recent10["points"].mean(),

            "driver_circuit_avg_finish": mean_or(cd_hist, "finish_position", d_hist["finish_position"].mean()),
            "driver_circuit_podium_rate": mean_or(cd_hist, "is_podium", d_hist["is_podium"].mean()),
            "team_circuit_avg_finish": mean_or(ct_hist, "finish_position", t_hist["finish_position"].mean()),
            "team_circuit_podium_rate": mean_or(ct_hist, "is_podium", t_hist["is_podium"].mean()),

            "career_starts": len(d_hist),
            "team_starts": len(t_hist),
            "circuit_experience": len(cd_hist),

            "driver_lap_pace": mean_or(d_hist.tail(5), "avg_best_35pct_lap", 100),
            "driver_lap_consistency": mean_or(d_hist.tail(5), "lap_consistency", 3),
            "driver_valid_laps": mean_or(d_hist.tail(5), "valid_laps", 0),
            "driver_pit_duration": mean_or(d_hist.tail(5), "avg_pit_duration", 3.5),
            "driver_pit_stop_count": mean_or(d_hist.tail(5), "pit_stop_count", 1),
            "team_pit_duration": mean_or(t_hist.tail(10), "avg_pit_duration", 3.5),
            "team_pit_stop_count": mean_or(t_hist.tail(10), "pit_stop_count", 1),
            "track_avg_pit_stops": mean_or(c_hist, "pit_stop_count", 1),
            "track_avg_lap_consistency": mean_or(c_hist, "lap_consistency", 3),
            "track_dnf_rate": 1 - mean_or(c_hist, "is_finished", 0.85),
            "track_overtake_proxy": mean_or(c_hist, "grid", 10) - mean_or(c_hist, "finish_position", 10),
        }
        feature_rows.append(features)

    feature_df = pd.DataFrame(feature_rows)

    feature_columns = [
        "grid_position", "qualifying_position", "sprint_position",
        "driver_avg_finish", "driver_median_finish", "driver_avg_points",
        "driver_win_rate", "driver_podium_rate", "driver_top10_rate", "driver_finish_rate",
        "driver_recent3_finish", "driver_recent5_points", "driver_recent5_podium_rate",
        "team_avg_finish", "team_avg_points", "team_win_rate", "team_podium_rate",
        "team_top10_rate", "team_finish_rate", "team_recent_points",
        "driver_circuit_avg_finish", "driver_circuit_podium_rate",
        "team_circuit_avg_finish", "team_circuit_podium_rate",
        "career_starts", "team_starts", "circuit_experience",
        "driver_lap_pace", "driver_lap_consistency", "driver_valid_laps",
        "driver_pit_duration", "driver_pit_stop_count",
        "team_pit_duration", "team_pit_stop_count",
        "track_avg_pit_stops", "track_avg_lap_consistency",
        "track_dnf_rate", "track_overtake_proxy",
    ]

    return feature_df, feature_columns


def latest_completed_race_id(current_year=None):
    year = current_year or now_local().year
    completed = []
    for race in fetch_schedule(year):
        race_dt = parse_race_datetime(race)
        if race_dt and now_local() >= race_dt + timedelta(hours=FINAL_RESULTS_DELAY_HOURS):
            data = fetch_round_data_cached(
                year,
                race.get("round"),
                allow_backfill=False,
                race=race,
                training_mode=True,
            )
            if race_has_results(data):
                completed.append((race_dt, f"{year}-{race.get('round')}"))
    if not completed and year > 1950:
        return latest_completed_race_id(year - 1)
    completed.sort(key=lambda x: x[0])
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
        print("ML model is current. Checking saved bundle.")
        existing_bundle = load_ml_bundle()
        if existing_bundle:
            print("Saved ML bundle loaded successfully. Skipping retrain.")
            return existing_bundle
        print("Saved ML bundle could not be loaded. Retraining with current dependency versions.")

    print("Training full-data ML model from cached/backfilled historical data.")
    current_year = now_local().year
    raw_df = collect_race_rows(ML_START_YEAR, current_year)

    raw_path = DATA_CACHE_DIR / "ml_full_race_results_raw.csv"
    feature_path = DATA_CACHE_DIR / "ml_full_race_features.csv"
    raw_df.to_csv(raw_path, index=False)

    feature_df, feature_columns = create_ml_features(raw_df)
    feature_df.to_csv(feature_path, index=False)

    if len(feature_df) < 80:
        print(f"Not enough full-data feature rows yet: {len(feature_df)}. More backfill runs needed.")
        return load_ml_bundle()

    seasons = sorted(feature_df["season"].dropna().unique())
    validation_year = seasons[-1]
    train_df = feature_df[feature_df["season"] < validation_year].copy()
    valid_df = feature_df[feature_df["season"] == validation_year].copy()

    if len(train_df) < 60 or len(valid_df) < 20:
        train_df = feature_df.sample(frac=0.8, random_state=42)
        valid_df = feature_df.drop(train_df.index)

    X_train = train_df[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)
    X_valid = valid_df[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)

    targets = {"win": "is_win", "podium": "is_podium", "top10": "is_top10"}
    models = {}
    metrics = {}

    for name, target_col in targets.items():
        y_train = train_df[target_col].astype(int)
        y_valid = valid_df[target_col].astype(int)

        rf = RandomForestClassifier(
            n_estimators=280,
            max_depth=11,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )
        hgb = HistGradientBoostingClassifier(
            max_iter=180,
            learning_rate=0.055,
            max_leaf_nodes=31,
            l2_regularization=0.03,
            random_state=42,
        )

        rf.fit(X_train, y_train)
        hgb.fit(X_train, y_train)

        rf_prob = rf.predict_proba(X_valid)[:, 1]
        hgb_prob = hgb.predict_proba(X_valid)[:, 1]
        prob = 0.55 * rf_prob + 0.45 * hgb_prob

        try:
            auc = roc_auc_score(y_valid, prob)
        except Exception:
            auc = None
        try:
            brier = brier_score_loss(y_valid, prob)
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
        "backfill_used_this_run": BACKFILL_BUDGET.used,
        "backfilled_races_this_run": BACKFILL_BUDGET.fetched,
    }
    MODEL_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"ML model saved: {MODEL_BUNDLE_PATH}")
    return bundle


def load_ml_bundle():
    if not MODEL_BUNDLE_PATH.exists():
        return None
    try:
        return joblib.load(MODEL_BUNDLE_PATH)
    except Exception as error:
        print(f"Could not load ML bundle: {error}")
        return None


def historical_feature_context(start_year, target_season):
    df = collect_race_rows(start_year, target_season)
    if df.empty:
        return df
    return df.sort_values(["season", "round"]).reset_index(drop=True)


def build_prediction_feature_rows(drivers, race, current_round_data, historical_df, feature_columns):
    season = safe_int(race.get("season")) or now_local().year
    round_no = safe_int(race.get("round")) or 0
    circuit_id = race.get("Circuit", {}).get("circuitId")

    q_positions = {}
    if current_round_data.get("qualifying"):
        for q in current_round_data["qualifying"][0].get("QualifyingResults", []):
            q_positions[q.get("Driver", {}).get("driverId")] = safe_int(q.get("position"))

    sprint_positions = {}
    if current_round_data.get("sprint"):
        for s in current_round_data["sprint"][0].get("SprintResults", []) or current_round_data["sprint"][0].get("Results", []):
            sprint_positions[s.get("Driver", {}).get("driverId")] = safe_int(s.get("positionOrder") or s.get("position"))

    current_laps = driver_lap_metrics_from_data(current_round_data)
    current_pits = pit_metrics_from_data(current_round_data)

    rows = []
    for driver in drivers:
        driver_id = driver["driver_id"]
        team = driver["team"]
        hist = historical_df[(historical_df["season"] < season) | ((historical_df["season"] == season) & (historical_df["round"] < round_no))].copy() if not historical_df.empty else pd.DataFrame()

        d_hist = hist[hist["driver_id"] == driver_id] if not hist.empty else pd.DataFrame()
        t_hist = hist[hist["constructor"] == team] if not hist.empty else pd.DataFrame()
        cd_hist = hist[(hist["circuit_id"] == circuit_id) & (hist["driver_id"] == driver_id)] if not hist.empty else pd.DataFrame()
        ct_hist = hist[(hist["circuit_id"] == circuit_id) & (hist["constructor"] == team)] if not hist.empty else pd.DataFrame()
        c_hist = hist[hist["circuit_id"] == circuit_id] if not hist.empty else pd.DataFrame()

        def mean_or(frame, col, fallback):
            if len(frame) and col in frame:
                val = pd.to_numeric(frame[col], errors="coerce").mean()
                if pd.notna(val):
                    return float(val)
            return fallback

        standing_proxy = min(20, max(1, safe_int(driver.get("position")) or 12))
        lap_now = current_laps.get(driver_id, {})
        pit_now = current_pits.get(driver_id, {})

        row = {
            "driver_id": driver_id,
            "driver_name": driver["name"],
            "constructor": team,
            "grid_position": q_positions.get(driver_id) or standing_proxy,
            "qualifying_position": q_positions.get(driver_id) or standing_proxy,
            "sprint_position": sprint_positions.get(driver_id) or 20,

            "driver_avg_finish": mean_or(d_hist, "finish_position", 12),
            "driver_median_finish": float(pd.to_numeric(d_hist["finish_position"], errors="coerce").median()) if len(d_hist) else 12,
            "driver_avg_points": mean_or(d_hist, "points", 0),
            "driver_win_rate": mean_or(d_hist, "is_win", 0),
            "driver_podium_rate": mean_or(d_hist, "is_podium", 0),
            "driver_top10_rate": mean_or(d_hist, "is_top10", 0),
            "driver_finish_rate": mean_or(d_hist, "is_finished", 0.85),
            "driver_recent3_finish": mean_or(d_hist.tail(3), "finish_position", mean_or(d_hist, "finish_position", 12)),
            "driver_recent5_points": mean_or(d_hist.tail(5), "points", mean_or(d_hist, "points", 0)),
            "driver_recent5_podium_rate": mean_or(d_hist.tail(5), "is_podium", mean_or(d_hist, "is_podium", 0)),

            "team_avg_finish": mean_or(t_hist, "finish_position", 12),
            "team_avg_points": mean_or(t_hist, "points", 0),
            "team_win_rate": mean_or(t_hist, "is_win", 0),
            "team_podium_rate": mean_or(t_hist, "is_podium", 0),
            "team_top10_rate": mean_or(t_hist, "is_top10", 0),
            "team_finish_rate": mean_or(t_hist, "is_finished", 0.85),
            "team_recent_points": mean_or(t_hist.tail(10), "points", mean_or(t_hist, "points", 0)),

            "driver_circuit_avg_finish": mean_or(cd_hist, "finish_position", mean_or(d_hist, "finish_position", 12)),
            "driver_circuit_podium_rate": mean_or(cd_hist, "is_podium", mean_or(d_hist, "is_podium", 0)),
            "team_circuit_avg_finish": mean_or(ct_hist, "finish_position", mean_or(t_hist, "finish_position", 12)),
            "team_circuit_podium_rate": mean_or(ct_hist, "is_podium", mean_or(t_hist, "is_podium", 0)),
            "career_starts": len(d_hist),
            "team_starts": len(t_hist),
            "circuit_experience": len(cd_hist),

            "driver_lap_pace": lap_now.get("avg_best_35pct") or mean_or(d_hist.tail(5), "avg_best_35pct_lap", 100),
            "driver_lap_consistency": lap_now.get("consistency") or mean_or(d_hist.tail(5), "lap_consistency", 3),
            "driver_valid_laps": lap_now.get("valid_laps") or mean_or(d_hist.tail(5), "valid_laps", 0),
            "driver_pit_duration": pit_now.get("avg_pit_duration") or mean_or(d_hist.tail(5), "avg_pit_duration", 3.5),
            "driver_pit_stop_count": pit_now.get("pit_stop_count") or mean_or(d_hist.tail(5), "pit_stop_count", 1),
            "team_pit_duration": mean_or(t_hist.tail(10), "avg_pit_duration", 3.5),
            "team_pit_stop_count": mean_or(t_hist.tail(10), "pit_stop_count", 1),
            "track_avg_pit_stops": mean_or(c_hist, "pit_stop_count", 1),
            "track_avg_lap_consistency": mean_or(c_hist, "lap_consistency", 3),
            "track_dnf_rate": 1 - mean_or(c_hist, "is_finished", 0.85),
            "track_overtake_proxy": mean_or(c_hist, "grid", 10) - mean_or(c_hist, "finish_position", 10),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    for col in feature_columns:
        if col not in df:
            df[col] = 0
    return df


def ml_predict_probabilities(drivers, race, current_round_data, bundle):
    if not bundle:
        return {}, {"status": "no model bundle available"}
    try:
        feature_columns = bundle["feature_columns"]
        historical_df = historical_feature_context(bundle.get("ml_start_year", ML_START_YEAR), safe_int(race.get("season")) or now_local().year)
        pred_df = build_prediction_feature_rows(drivers, race, current_round_data, historical_df, feature_columns)
        X = pred_df[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)

        outputs = {}
        for target, pair in bundle["models"].items():
            rf_prob = pair["rf"].predict_proba(X)[:, 1]
            hgb_prob = pair["hgb"].predict_proba(X)[:, 1]
            outputs[target] = 0.55 * rf_prob + 0.45 * hgb_prob

        by_driver = {}
        for idx, row in pred_df.iterrows():
            driver_id = row["driver_id"]
            by_driver[driver_id] = {
                "ml_win_probability": float(outputs.get("win", [0])[idx] * 100),
                "ml_podium_probability": float(outputs.get("podium", [0])[idx] * 100),
                "ml_top10_probability": float(outputs.get("top10", [0])[idx] * 100),
            }

        return by_driver, {
            "status": "ml predictions generated",
            "feature_rows": pred_df.to_dict(orient="records"),
            "bundle_meta": {k: v for k, v in bundle.items() if k != "models"},
        }
    except Exception as error:
        print(f"ML prediction failed: {error}")
        return {}, {"status": "ml prediction failed", "error": str(error)}


def fetch_historical_same_circuit(target_race, years_back=5):
    circuit_id = target_race.get("Circuit", {}).get("circuitId")
    season = safe_int(target_race.get("season")) or now_local().year
    records = []
    if not circuit_id:
        return records

    for year in range(season, season - years_back - 1, -1):
        for race in fetch_schedule(year):
            if race.get("Circuit", {}).get("circuitId") == circuit_id:
                round_no = race.get("round")
                if round_no:
                    data = fetch_round_data_cached(
                        year,
                        round_no,
                        allow_backfill=True,
                        race=race,
                        training_mode=is_race_past_calendar_cutoff(race),
                    )
                    if data:
                        records.append({"season": year, "round": round_no, "race": race, "data": data})
                break
    return records


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
        "wind_gust": "Unavailable",
        "cloud_cover": "Unavailable",
        "track_temperature": "Unavailable",
        "rain_score": 0,
        "heat_score": 0,
        "wind_score": 0,
        "impact": "Weather unavailable.",
    }
    if lat is None or lon is None:
        base["source"] = "Unavailable"
        base["impact"] = "Circuit coordinates missing."
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
    valid = [(idx, val) for idx, val in enumerate(parsed) if val is not None]
    if not valid:
        return base

    idx = min(valid, key=lambda pair: abs(pair[1] - target))[0]

    def get(key):
        vals = hourly.get(key, [])
        return vals[idx] if idx < len(vals) else None

    temp = get("temperature_2m")
    rain = get("precipitation_probability")
    humidity = get("relative_humidity_2m")
    wind = get("wind_speed_10m")
    gust = get("wind_gusts_10m")
    cloud = get("cloud_cover")

    temp_num = safe_float(temp)
    rain_score = min(100, safe_float(rain) or 0)
    wind_num = safe_float(gust) or safe_float(wind) or 0
    heat_score = 85 if temp_num and temp_num >= 34 else 60 if temp_num and temp_num >= 29 else 55 if temp_num and temp_num <= 15 else 0
    wind_score = min(100, wind_num * 2.6)

    impacts = []
    if rain_score >= 50:
        impacts.append("high rain risk, mixed strategy possible")
    elif rain_score >= 25:
        impacts.append("moderate rain risk, radar should influence pit timing")
    else:
        impacts.append("dry baseline more likely")
    if heat_score >= 60:
        impacts.append("heat may increase degradation and cooling demand")
    if wind_score >= 60:
        impacts.append("wind may affect braking stability and aero balance")
    if safe_float(cloud) and safe_float(cloud) >= 70:
        impacts.append("cloud cover may reduce track-temperature growth")

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
        "impact": "; ".join(impacts),
    }


def fetch_historical_weather_summary(race, years_back=5):
    location = race.get("Circuit", {}).get("Location", {})
    lat = safe_float(location.get("lat"))
    lon = safe_float(location.get("long"))
    race_dt = parse_race_datetime(race)
    if lat is None or lon is None or not race_dt:
        return {}
    samples = []
    for year in range(race_dt.year - years_back, race_dt.year):
        try:
            start_dt = race_dt.replace(year=year)
        except ValueError:
            continue
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_dt.date().isoformat(),
            "end_date": (start_dt + timedelta(days=1)).date().isoformat(),
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
        samples.append({
            "year": year,
            "avg_temp": average(hourly.get("temperature_2m", [])),
            "rain_total": sum(safe_float(x) or 0 for x in hourly.get("precipitation", [])),
            "max_wind": max([safe_float(x) or 0 for x in hourly.get("wind_speed_10m", [])], default=None),
            "avg_cloud": average(hourly.get("cloud_cover", [])),
        })
    return {"source": "Open-Meteo archive", "samples": samples}


def infer_track_profile(race, historical_records, weather_summary, historical_weather=None):
    trait_samples = []
    all_results = []
    for record in historical_records:
        data = record.get("data", {})
        trait = track_traits_from_race_data(data)
        if trait:
            trait_samples.append(trait)
        result_races = data.get("results", [])
        if result_races:
            all_results.extend(result_races[0].get("Results", []))

    avg_overtake = average([x.get("avg_grid_finish_movement") for x in trait_samples])
    avg_stops = average([x.get("avg_pit_stops") for x in trait_samples])
    dnf_rate = average([x.get("dnf_rate") for x in trait_samples])
    lap_consistency = average([x.get("avg_lap_consistency") for x in trait_samples])

    if avg_overtake is None:
        overtaking = "unknown"
    elif avg_overtake >= 5:
        overtaking = "good"
    elif avg_overtake >= 3:
        overtaking = "medium-good"
    elif avg_overtake >= 1.5:
        overtaking = "medium"
    else:
        overtaking = "low-medium"

    if avg_stops is None:
        tyre_stress = "unknown"
    elif avg_stops >= 2:
        tyre_stress = "high"
    elif avg_stops >= 1.45:
        tyre_stress = "medium-high"
    elif avg_stops >= 1:
        tyre_stress = "medium"
    else:
        tyre_stress = "low-medium"

    if dnf_rate is None:
        safety_car = "unknown"
    elif dnf_rate >= 0.25:
        safety_car = "high"
    elif dnf_rate >= 0.15:
        safety_car = "medium-high"
    elif dnf_rate >= 0.08:
        safety_car = "medium"
    else:
        safety_car = "low-medium"

    circuit = race.get("Circuit", {})
    location = circuit.get("Location", {})
    circuit_name = circuit.get("circuitName", "Unknown circuit")
    circuit_id = circuit.get("circuitId", "")
    text = f"{race.get('raceName', '')} {circuit_name} {circuit_id}".lower()

    street = any(k in text for k in ["monaco", "singapore", "marina", "baku", "miami", "jeddah", "vegas"])
    if street:
        track_type = "street or temporary circuit"
    else:
        track_type = "permanent circuit"

    if any(k in text for k in ["monza", "vegas", "baku", "jeddah"]):
        speed_profile = "straight-line-speed dominant"
        car_trait = "low drag efficiency, braking stability, power delivery"
    elif any(k in text for k in ["silverstone", "suzuka", "spa", "qatar", "lusail"]):
        speed_profile = "aero-efficiency dominant"
        car_trait = "high-speed downforce, aero efficiency, tyre load control"
    elif any(k in text for k in ["monaco", "hungaroring", "singapore"]):
        speed_profile = "traction and braking dominant"
        car_trait = "high downforce, slow-corner traction, kerb compliance"
    else:
        speed_profile = "balanced speed profile"
        car_trait = "balanced aero, traction, braking, and tyre management"

    if "straight-line" in speed_profile:
        dominance = "low drag and straight-line speed"
    elif "aero" in speed_profile:
        dominance = "aero efficiency and high-speed downforce"
    elif street and overtaking in {"low", "low-medium", "unknown"}:
        dominance = "track position, downforce, braking stability, and wall confidence"
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

    setup = [car_trait]
    if weather_summary.get("rain_score", 0) >= 35:
        setup.append("wet crossover flexibility")
    if weather_summary.get("wind_score", 0) >= 60:
        setup.append("stable aero balance in wind")

    return {
        "race_name": race.get("raceName", "Unknown Grand Prix"),
        "circuit": circuit_name,
        "city": location.get("locality", "Unknown location"),
        "country": location.get("country", "Unknown country"),
        "track_type": track_type,
        "circuit_key": circuit_id,
        "meeting_key": f"{race.get('season')}-{race.get('round')}",
        "dominance": dominance,
        "speed_profile": speed_profile,
        "car_trait": car_trait,
        "overtaking": overtaking,
        "tyre_stress": tyre_stress,
        "safety_car": safety_car,
        "strategy_bias": strategy_bias,
        "setup": "; ".join(setup),
        "dynamic_reasons": {
            "overtaking": f"average grid-to-finish movement around {avg_overtake}" if avg_overtake is not None else "not enough cached historical data yet",
            "tyre_stress": f"historical average around {avg_stops} stops per driver" if avg_stops is not None else "not enough cached pit data yet",
            "safety_car": f"non-finish proxy rate around {dnf_rate * 100:.1f}%" if dnf_rate is not None else "not enough cached result data yet",
            "speed_profile": f"car trait inferred as {car_trait}",
        },
        "dynamic_track_source": {
            "source": "Jolpica full cached history + Open-Meteo + optional FastF1",
            "used_full_race_cache": True,
            "used_open_meteo_archive": bool(historical_weather and historical_weather.get("samples")),
        },
        "dynamic_track_metrics": {
            "historical_races_sampled": len(historical_records),
            "average_overtake_delta": avg_overtake,
            "average_stops_per_driver": avg_stops,
            "dnf_rate": dnf_rate,
            "lap_consistency": lap_consistency,
            "backfill_used_this_run": BACKFILL_BUDGET.used,
            "backfilled_races_this_run": BACKFILL_BUDGET.fetched,
        },
        "historical_weather": historical_weather or {},
    }


def constructor_score_map(constructor_standings):
    raw = {}
    for row in constructor_standings:
        name = row.get("Constructor", {}).get("name")
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


def sprint_score_map(round_data):
    raw = {}
    races = round_data.get("sprint", [])
    if not races:
        return raw
    for row in races[0].get("SprintResults", []) or races[0].get("Results", []):
        driver_id = row.get("Driver", {}).get("driverId")
        pos = safe_int(row.get("positionOrder") or row.get("position"))
        if driver_id and pos:
            raw[driver_id] = score_position(pos)
    return raw


def circuit_history_score_map(historical_records):
    raw = {}
    for record in historical_records:
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.12)
        result_races = record.get("data", {}).get("results", [])
        if not result_races:
            continue
        for row in result_races[0].get("Results", []):
            driver_id = row.get("Driver", {}).get("driverId")
            pos = safe_int(row.get("positionOrder") or row.get("position"))
            if driver_id and pos:
                raw.setdefault(driver_id, []).append((score_position(pos), weight))
    return {driver_id: weighted_average(vals) for driver_id, vals in raw.items()}


def constructor_circuit_score_map(historical_records):
    raw = {}
    for record in historical_records:
        weight = max(0.35, 1 - (now_local().year - record["season"]) * 0.12)
        result_races = record.get("data", {}).get("results", [])
        if not result_races:
            continue
        for row in result_races[0].get("Results", []):
            team = row.get("Constructor", {}).get("name")
            pos = safe_int(row.get("positionOrder") or row.get("position"))
            if team and pos:
                raw.setdefault(team, []).append((score_position(pos), weight))
    return {team: weighted_average(vals) for team, vals in raw.items()}


def race_pace_score_map(historical_records, current_round_data):
    raw = {}
    records = [{"season": now_local().year, "data": current_round_data, "weight": 1.35}]
    for rec in historical_records:
        records.append({"season": rec["season"], "data": rec.get("data", {}), "weight": max(0.35, 1 - (now_local().year - rec["season"]) * 0.12)})

    for rec in records:
        metrics = driver_lap_metrics_from_data(rec["data"])
        for driver_id, item in metrics.items():
            if item.get("avg_best_35pct"):
                raw.setdefault(driver_id, []).append((item["avg_best_35pct"], rec["weight"]))

    avg_laps = {driver_id: weighted_average(vals) for driver_id, vals in raw.items()}
    return normalize_scores(avg_laps, reverse=True)


def pit_execution_score_maps(historical_records, current_round_data):
    driver_raw = {}
    team_raw = {}

    def constructor_lookup(data):
        lookup = {}
        result_races = data.get("results", [])
        if result_races:
            for row in result_races[0].get("Results", []):
                lookup[row.get("Driver", {}).get("driverId")] = row.get("Constructor", {}).get("name")
        return lookup

    records = [{"season": now_local().year, "data": current_round_data, "weight": 1.35}]
    for rec in historical_records:
        records.append({"season": rec["season"], "data": rec.get("data", {}), "weight": max(0.35, 1 - (now_local().year - rec["season"]) * 0.12)})

    for rec in records:
        metrics = pit_metrics_from_data(rec["data"])
        lookup = constructor_lookup(rec["data"])
        for driver_id, item in metrics.items():
            duration = item.get("avg_pit_duration")
            if duration:
                driver_raw.setdefault(driver_id, []).append((duration, rec["weight"]))
                team = lookup.get(driver_id)
                if team:
                    team_raw.setdefault(team, []).append((duration, rec["weight"]))

    return normalize_scores({d: weighted_average(v) for d, v in driver_raw.items()}, reverse=True), normalize_scores({t: weighted_average(v) for t, v in team_raw.items()}, reverse=True)


def strategy_gain_score_maps(historical_records):
    driver_raw = {}
    team_raw = {}
    for rec in historical_records:
        weight = max(0.35, 1 - (now_local().year - rec["season"]) * 0.12)
        races = rec.get("data", {}).get("results", [])
        if not races:
            continue
        for row in races[0].get("Results", []):
            driver_id = row.get("Driver", {}).get("driverId")
            team = row.get("Constructor", {}).get("name")
            grid = safe_int(row.get("grid"))
            finish = safe_int(row.get("positionOrder") or row.get("position"))
            if driver_id and grid and grid > 0 and finish:
                gain = grid - finish
                driver_raw.setdefault(driver_id, []).append((gain, weight))
                if team:
                    team_raw.setdefault(team, []).append((gain, weight))
    return normalize_scores({d: weighted_average(v) for d, v in driver_raw.items()}), normalize_scores({t: weighted_average(v) for t, v in team_raw.items()})


def reliability_score_map(historical_records):
    raw = {}
    for rec in historical_records:
        weight = max(0.35, 1 - (now_local().year - rec["season"]) * 0.12)
        races = rec.get("data", {}).get("results", [])
        if not races:
            continue
        for row in races[0].get("Results", []):
            driver_id = row.get("Driver", {}).get("driverId")
            status = str(row.get("status", "")).lower()
            if not driver_id:
                continue
            if "finished" in status or "+" in status:
                score = 90
            elif any(x in status for x in ["accident", "collision", "spun"]):
                score = 35
            elif any(x in status for x in ["engine", "gearbox", "hydraulics", "electrical"]):
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
    score = 50.0
    if constructor_circuit_score is not None:
        score = weighted_average([(score, 0.35), (constructor_circuit_score, 0.65)])
    if "straight-line" in speed and any(k in team_text for k in ["williams", "red bull", "ferrari", "cadillac"]):
        score += 7
    if ("aero" in dominance or "downforce" in dominance) and any(k in team_text for k in ["mclaren", "mercedes", "red bull", "aston martin"]):
        score += 8
    if ("tyre" in dominance or tyre in {"high", "medium-high"}) and any(k in team_text for k in ["mclaren", "ferrari", "mercedes"]):
        score += 7
    if ("track position" in dominance or "low" in overtaking) and any(k in team_text for k in ["ferrari", "mclaren", "mercedes", "red bull"]):
        score += 5
    if "traction" in dominance and any(k in team_text for k in ["red bull", "ferrari", "aston martin", "racing bulls"]):
        score += 5
    return max(0, min(100, score))


def setup_fastf1():
    if fastf1 is None:
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
        session = fastf1.get_session(int(season), int(round_no), code)
        session.load(laps=True, weather=True, messages=False)
        print(f"FastF1 loaded {season} round {round_no} {code}")
        return session
    except Exception as error:
        print(f"FastF1 skipped {season} round {round_no} {code}: {error}")
        return None


def fastf1_enhancement_scores(season, round_no):
    scores = {"fastf1_race_pace": {}, "fastf1_consistency": {}, "fastf1_tyre_stint": {}, "sessions_loaded": []}
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
                for lap_time in group.get("LapTime", []):
                    try:
                        sec = lap_time.total_seconds()
                    except Exception:
                        sec = None
                    if sec and 45 <= sec <= 180:
                        times.append(sec)
                if len(times) >= 4:
                    sample = sorted(times)[:max(4, int(len(times) * 0.35))]
                    pace_raw[str(driver).lower()] = average(sample)
                    consistency_raw[str(driver).lower()] = float(np.std(sample)) if len(sample) > 1 else None
                if "Stint" in group.columns:
                    stint_raw[str(driver).lower()] = float(group.groupby("Stint").size().max())
            scores["fastf1_race_pace"].update(normalize_scores(pace_raw, reverse=True))
            scores["fastf1_consistency"].update(normalize_scores(consistency_raw, reverse=True))
            scores["fastf1_tyre_stint"].update(normalize_scores(stint_raw))
        except Exception as error:
            print(f"FastF1 extraction failed for {code}: {error}")
    return scores



def openf1_get(endpoint, params=None, optional_404=True):
    """
    OpenF1 historical endpoints are used only when the free public API responds.
    If OpenF1 rejects the request, the model falls back to Jolpica + FastF1.
    """
    if not OPENF1_ENABLED:
        return None
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    url = OPENF1_BASE + endpoint
    response = safe_get(url, params=params or {}, headers={"User-Agent": "f1-race-intel/3.1 openf1-fallback"}, timeout=35, optional_404=optional_404)
    if not response:
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        print(f"OpenF1 returned non-JSON for {endpoint}")
        return None


def find_openf1_meeting(race):
    season = safe_int(race.get("season")) or now_local().year
    location = race.get("Circuit", {}).get("Location", {})
    country = location.get("country")
    city = location.get("locality")
    circuit = race.get("Circuit", {}).get("circuitName")
    race_name = race.get("raceName", "")

    queries = []
    if country:
        queries.append({"year": season, "country_name": country})
    if city:
        queries.append({"year": season, "location": city})
    if circuit:
        queries.append({"year": season})

    candidates = []
    for params in queries:
        data = openf1_get("/meetings", params=params)
        if isinstance(data, list):
            candidates.extend(data)

    if not candidates:
        return None

    target = " ".join([str(country or ""), str(city or ""), str(circuit or ""), str(race_name or "")]).lower()
    best = None
    best_score = -1
    for meeting in candidates:
        text = " ".join([
            str(meeting.get("country_name", "")),
            str(meeting.get("location", "")),
            str(meeting.get("circuit_short_name", "")),
            str(meeting.get("meeting_name", "")),
            str(meeting.get("meeting_official_name", "")),
        ]).lower()
        score = sum(1 for token in tokenize(target) if token in text)
        if score > best_score:
            best = meeting
            best_score = score
    return best


def choose_openf1_session(sessions, wanted_type):
    if not sessions:
        return None
    wanted_type = wanted_type.lower()
    for session in sessions:
        name = str(session.get("session_name", "")).lower()
        typ = str(session.get("session_type", "")).lower()
        if wanted_type == "race" and (typ == "race" or name == "race"):
            return session
        if wanted_type == "qualifying" and ("qualifying" in name or typ == "qualifying"):
            return session
    return None


def match_openf1_driver_to_id(openf1_driver, known_drivers):
    full = normalize_name(openf1_driver.get("full_name") or " ".join([str(openf1_driver.get("first_name", "")), str(openf1_driver.get("last_name", ""))]))
    full_key = set(tokenize(full))
    best = None
    best_score = -1
    for driver in known_drivers:
        key = set(tokenize(driver.get("name", "")))
        score = len(full_key & key)
        if score > best_score:
            best = driver
            best_score = score
    if best_score <= 0:
        return None
    return best.get("driver_id")


def openf1_enhancement_scores(race, known_drivers):
    """
    Adds OpenF1 if the free historical API works. If OpenF1 fails, all maps stay empty.
    Data used: meetings, sessions, drivers, session_result, starting_grid, laps, pit, stints, weather, car_data.
    """
    empty = {
        "provider_status": "not_used",
        "meeting": None,
        "sessions": [],
        "driver_scores": {},
        "team_scores": {},
        "weather_traits": {},
        "openf1_session_result": {},
        "openf1_starting_grid": {},
        "openf1_lap_pace": {},
        "openf1_pit_execution": {},
        "openf1_stint_strength": {},
        "openf1_telemetry_speed": {},
        "openf1_car_performance": {},
    }
    if not OPENF1_ENABLED:
        empty["provider_status"] = "disabled"
        return empty

    meeting = find_openf1_meeting(race)
    if not meeting:
        empty["provider_status"] = "unavailable_or_rejected"
        return empty

    meeting_key = meeting.get("meeting_key")
    sessions = openf1_get("/sessions", params={"meeting_key": meeting_key}) or []
    race_session = choose_openf1_session(sessions, "race")
    quali_session = choose_openf1_session(sessions, "qualifying")
    session_key = (race_session or quali_session or {}).get("session_key")
    if not session_key:
        empty["provider_status"] = "meeting_found_no_session"
        empty["meeting"] = meeting
        return empty

    drivers_data = openf1_get("/drivers", params={"session_key": session_key}) or []
    number_to_driver = {}
    number_to_team = {}
    for od in drivers_data:
        number = safe_int(od.get("driver_number"))
        driver_id = match_openf1_driver_to_id(od, known_drivers)
        if number and driver_id:
            number_to_driver[number] = driver_id
            number_to_team[number] = od.get("team_name")

    result_raw = {}
    grid_raw = {}
    lap_raw = {}
    pit_raw = {}
    stint_raw = {}
    speed_raw = {}
    team_raw = {}

    result_rows = openf1_get("/session_result", params={"session_key": session_key}) or []
    for row in result_rows:
        number = safe_int(row.get("driver_number"))
        driver_id = number_to_driver.get(number)
        if not driver_id:
            continue
        pos = safe_int(row.get("position"))
        result_raw[driver_id] = score_position(pos)
        duration = safe_float(row.get("duration"))
        if duration:
            lap_raw.setdefault(driver_id, []).append(duration)

    grid_rows = openf1_get("/starting_grid", params={"session_key": session_key}) or []
    for row in grid_rows:
        number = safe_int(row.get("driver_number"))
        driver_id = number_to_driver.get(number)
        if driver_id:
            grid_raw[driver_id] = score_position(row.get("position"))

    laps = openf1_get("/laps", params={"session_key": session_key}) or []
    for row in laps:
        number = safe_int(row.get("driver_number"))
        driver_id = number_to_driver.get(number)
        lap_duration = safe_float(row.get("lap_duration"))
        if driver_id and lap_duration and 45 <= lap_duration <= 180:
            lap_raw.setdefault(driver_id, []).append(lap_duration)

    pits = openf1_get("/pit", params={"session_key": session_key}) or []
    for row in pits:
        number = safe_int(row.get("driver_number"))
        driver_id = number_to_driver.get(number)
        duration = safe_float(row.get("stop_duration")) or safe_float(row.get("pit_duration")) or safe_float(row.get("lane_duration"))
        if driver_id and duration and 1.5 <= duration <= 80:
            pit_raw.setdefault(driver_id, []).append(duration)

    stints = openf1_get("/stints", params={"session_key": session_key}) or []
    for row in stints:
        number = safe_int(row.get("driver_number"))
        driver_id = number_to_driver.get(number)
        start = safe_int(row.get("lap_start"))
        end = safe_int(row.get("lap_end"))
        if driver_id and start is not None and end is not None:
            stint_raw.setdefault(driver_id, []).append(max(0, end - start + 1))

    # Keep telemetry bounded: high-speed samples are enough for straight-line car signal.
    car_data = openf1_get("/car_data", params={"session_key": session_key, "speed>=": 300}) or []
    if not car_data:
        car_data = openf1_get("/car_data", params={"session_key": session_key, "speed>=": 280}) or []
    for row in car_data:
        number = safe_int(row.get("driver_number"))
        driver_id = number_to_driver.get(number)
        speed = safe_float(row.get("speed"))
        rpm = safe_float(row.get("rpm"))
        throttle = safe_float(row.get("throttle"))
        if driver_id and speed:
            speed_raw.setdefault(driver_id, []).append(weighted_average([(speed, 0.70), (rpm / 100 if rpm else None, 0.15), (throttle, 0.15)]))

    weather_rows = openf1_get("/weather", params={"session_key": session_key}) or []
    weather_traits = {}
    if weather_rows:
        weather_traits = {
            "openf1_air_temperature": average([r.get("air_temperature") for r in weather_rows]),
            "openf1_track_temperature": average([r.get("track_temperature") for r in weather_rows]),
            "openf1_rainfall": average([r.get("rainfall") for r in weather_rows]),
            "openf1_wind_speed": average([r.get("wind_speed") for r in weather_rows]),
            "openf1_humidity": average([r.get("humidity") for r in weather_rows]),
        }

    lap_avg = {d: average(v) for d, v in lap_raw.items()}
    pit_avg = {d: average(v) for d, v in pit_raw.items()}
    stint_avg = {d: average(v) for d, v in stint_raw.items()}
    speed_avg = {d: average(v) for d, v in speed_raw.items()}

    lap_score = normalize_scores(lap_avg, reverse=True)
    pit_score = normalize_scores(pit_avg, reverse=True)
    stint_score = normalize_scores(stint_avg)
    speed_score = normalize_scores(speed_avg)

    car_score = {}
    for driver_id in set(result_raw) | set(grid_raw) | set(lap_score) | set(pit_score) | set(stint_score) | set(speed_score):
        car_score[driver_id] = weighted_average([
            (result_raw.get(driver_id), 0.14),
            (grid_raw.get(driver_id), 0.12),
            (lap_score.get(driver_id), 0.25),
            (speed_score.get(driver_id), 0.22),
            (pit_score.get(driver_id), 0.12),
            (stint_score.get(driver_id), 0.15),
        ])

    for number, driver_id in number_to_driver.items():
        team = number_to_team.get(number)
        if team and car_score.get(driver_id) is not None:
            team_raw.setdefault(team, []).append(car_score[driver_id])

    empty.update({
        "provider_status": "used",
        "meeting": meeting,
        "sessions": sessions,
        "driver_scores": car_score,
        "team_scores": {team: average(vals) for team, vals in team_raw.items()},
        "weather_traits": weather_traits,
        "openf1_session_result": result_raw,
        "openf1_starting_grid": grid_raw,
        "openf1_lap_pace": lap_score,
        "openf1_pit_execution": pit_score,
        "openf1_stint_strength": stint_score,
        "openf1_telemetry_speed": speed_score,
        "openf1_car_performance": car_score,
    })
    return empty


def collect_current_season_constructor_performance(season, current_round):
    team_rows = {}
    if not current_round:
        return {}

    for race in fetch_schedule(season):
        round_no = safe_int(race.get("round"))
        if not round_no or round_no >= safe_int(current_round):
            continue
        data = fetch_round_data_cached(season, round_no, allow_backfill=True)
        if not data or not race_has_results(data):
            continue

        result_race = data["results"][0]
        qualifying_race = data.get("qualifying", [{}])[0] if data.get("qualifying") else {}
        lap_metrics = driver_lap_metrics_from_data(data)
        pit_metrics = pit_metrics_from_data(data)

        q_by_driver = {}
        for q in qualifying_race.get("QualifyingResults", []):
            q_by_driver[q.get("Driver", {}).get("driverId")] = safe_int(q.get("position"))

        for result in result_race.get("Results", []):
            driver_id = result.get("Driver", {}).get("driverId")
            team = result.get("Constructor", {}).get("name")
            finish = safe_int(result.get("positionOrder") or result.get("position"))
            grid = safe_int(result.get("grid"))
            points = safe_float(result.get("points")) or 0
            status = str(result.get("status", "")).lower()
            if not team or not driver_id:
                continue
            lap = lap_metrics.get(driver_id, {})
            pit = pit_metrics.get(driver_id, {})
            reliability_score = 90 if ("finished" in status or "+" in status) else 45
            grid_gain = grid - finish if grid and grid > 0 and finish else None
            team_rows.setdefault(team, []).append({
                "finish_score": score_position(finish),
                "qualifying_score": score_position(q_by_driver.get(driver_id) or grid),
                "points": points,
                "grid_gain": grid_gain,
                "lap_pace": lap.get("avg_best_35pct"),
                "lap_consistency": lap.get("consistency"),
                "pit_duration": pit.get("avg_pit_duration"),
                "reliability": reliability_score,
            })

    raw = {}
    for team, rows in team_rows.items():
        raw[team] = {
            "finish_score": average([r["finish_score"] for r in rows]),
            "qualifying_score": average([r["qualifying_score"] for r in rows]),
            "points_score": average([r["points"] for r in rows]),
            "strategy_score": average([r["grid_gain"] for r in rows]),
            "lap_pace_raw": average([r["lap_pace"] for r in rows]),
            "lap_consistency_raw": average([r["lap_consistency"] for r in rows]),
            "pit_duration_raw": average([r["pit_duration"] for r in rows]),
            "reliability": average([r["reliability"] for r in rows]),
        }

    lap_scores = normalize_scores({t: r["lap_pace_raw"] for t, r in raw.items() if r["lap_pace_raw"] is not None}, reverse=True)
    consistency_scores = normalize_scores({t: r["lap_consistency_raw"] for t, r in raw.items() if r["lap_consistency_raw"] is not None}, reverse=True)
    pit_scores = normalize_scores({t: r["pit_duration_raw"] for t, r in raw.items() if r["pit_duration_raw"] is not None}, reverse=True)
    point_scores = normalize_scores({t: r["points_score"] for t, r in raw.items() if r["points_score"] is not None})
    strategy_scores = normalize_scores({t: r["strategy_score"] for t, r in raw.items() if r["strategy_score"] is not None})

    final = {}
    for team, row in raw.items():
        final[team] = weighted_average([
            (row["finish_score"], 0.20),
            (row["qualifying_score"], 0.16),
            (point_scores.get(team), 0.16),
            (lap_scores.get(team), 0.18),
            (consistency_scores.get(team), 0.08),
            (pit_scores.get(team), 0.08),
            (strategy_scores.get(team), 0.06),
            (row["reliability"], 0.08),
        ])
    return final


def collect_recent_current_season_constructor_form(season, current_round, recent_n=3):
    if not current_round:
        return {}
    completed = []
    for race in fetch_schedule(season):
        round_no = safe_int(race.get("round"))
        if round_no and round_no < safe_int(current_round):
            completed.append((round_no, race))
    completed = sorted(completed, key=lambda x: x[0])[-recent_n:]
    team_scores = {}
    for round_no, race in completed:
        data = fetch_round_data_cached(season, round_no, allow_backfill=True)
        if not data or not race_has_results(data):
            continue
        for result in data["results"][0].get("Results", []):
            team = result.get("Constructor", {}).get("name")
            finish = safe_int(result.get("positionOrder") or result.get("position"))
            points = safe_float(result.get("points")) or 0
            if not team:
                continue
            team_scores.setdefault(team, []).append(weighted_average([(score_position(finish), 0.62), (points, 0.38)]))
    return {team: average(scores) for team, scores in team_scores.items() if scores}

def driver_code_guess(name):
    parts = str(name or "").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][:3]).lower()
    return str(name or "").lower()[:4]



# -----------------------------
# Official upgrades, regulations, calendar resilience
# -----------------------------

TRUSTED_UPGRADE_SOURCE_DOMAINS = (
    "fia.com",
    "formula1.com",
)

UPGRADE_TRAIT_KEYWORDS = {
    "downforce": ["downforce", "load", "floor", "diffuser", "front wing", "rear wing", "beam wing", "bodywork", "underfloor", "floor edge", "floor fence"],
    "aero_efficiency": ["aero efficiency", "aerodynamic efficiency", "efficiency", "flow", "wake", "sidepod", "engine cover", "coke", "fence", "fences"],
    "straight_line": ["low drag", "drag reduction", "straight", "straightline", "straight-line", "monza", "low-downforce"],
    "traction": ["traction", "rear suspension", "suspension", "mechanical grip", "slow-speed", "low speed", "kerb", "kerbs"],
    "braking": ["brake", "braking", "brake duct", "brake cooling", "front brake", "rear brake"],
    "cooling": ["cooling", "louvre", "louvres", "heat rejection", "exit", "inlet", "radiator", "high altitude"],
    "tyre_management": ["tyre", "tire", "thermal", "degradation", "temperature", "rear tyre", "front tyre"],
    "stability": ["stability", "balance", "sensitivity", "wind", "yaw", "ride height", "porpoising", "bouncing"],
    "power_efficiency": ["power unit", "energy", "ers", "battery", "deployment", "fuel", "sustainable fuel", "compression ratio"],
}

REGULATION_CONTEXTS = {
    "2025": {
        "era": "2025 bodywork flexibility control era",
        "notes": [
            "FIA front and rear wing flexibility checks make aero compliance and load stability more important.",
            "Teams with efficient legal wing load and stable platforms should be less exposed to regulatory disruption.",
        ],
        "boost_traits": ["aero_efficiency", "stability", "downforce"],
    },
    "2026+": {
        "era": "2026+ active-aero and new power-unit era",
        "notes": [
            "The FIA/F1 2026 rules introduce smaller, lighter cars, reduced drag/downforce targets, active aerodynamics, more electrical power, sustainable fuels, and Manual Override Mode.",
            "Prediction should reward efficient aero switching, straight-line efficiency, energy deployment, traction, braking stability, reliability, and driver adaptability.",
        ],
        "boost_traits": ["aero_efficiency", "straight_line", "power_efficiency", "stability", "traction", "braking", "reliability"],
    },
    "2027+": {
        "era": "2027+ evolved 2026 regulation era",
        "notes": [
            "From 2027 onward the FIA compression-ratio control language moves toward operating-condition control, so power-unit reliability and thermal stability remain relevant model traits.",
            "The model keeps 2026-era active aero and power-unit assumptions unless newer regulation text is added through source notes.",
        ],
        "boost_traits": ["power_efficiency", "cooling", "reliability", "aero_efficiency", "stability"],
    },
}

PROMPT_REQUIREMENT_CHECKLIST = [
    "cache_first_backfill_for_github",
    "use_local_full_cache_after_manual_download",
    "openf1_if_free_and_working_else_fallback",
    "jolpica_fastf1_openmeteo_core",
    "current_season_car_performance",
    "recent_constructor_form",
    "team_upgrade_package_impact",
    "trusted_upgrade_sources",
    "track_traits_downforce_straightline_traction_braking_tyre_overtaking",
    "weather_traits_rain_heat_wind_cloud_historical_weather",
    "driver_skill_form_reliability_circuit_history_recent_results",
    "qualifying_grid_sprint_lap_pace_pit_execution_strategy_gain",
    "f1_regulation_context_2025_2026_2027_and_future_safe",
    "official_calendar_or_jolpica_fallback",
    "season_change_resilience_uses_previous_data_when_current_missing",
    "email_issue_markdown_dashboard_json",
]


def strip_html(html):
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def candidate_fia_upgrade_urls(race):
    race_name = str(race.get("raceName", ""))
    circuit = race.get("Circuit", {}).get("circuitName", "")
    candidates = []
    base_terms = []
    for source in [race_name, circuit]:
        cleaned = re.sub(r"\b(formula|1|f1|grand|prix|gp|the|de|del|d')\b", " ", source.lower())
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
        if cleaned:
            base_terms.append(cleaned)
    for term in base_terms:
        slug = make_slug(term)
        candidates.append(f"{FIA_TECH_UPDATE_BASE}/f1-tech-updates-{slug}-grand-prix")
        candidates.append(f"{FIA_TECH_UPDATE_BASE}/f1-tech-updates-{slug}-gp")
    for url in UPGRADE_NEWS_URLS:
        candidates.append(url)
    seen = []
    for url in candidates:
        if url not in seen:
            seen.append(url)
    return seen[:10]


def fetch_text_from_trusted_url(url):
    if not any(domain in url for domain in TRUSTED_UPGRADE_SOURCE_DOMAINS):
        return None
    response = safe_get(url, timeout=25, use_cache=False, optional_404=True)
    if not response:
        return None
    try:
        return strip_html(response.text)
    except Exception:
        return None


def classify_upgrade_text(text):
    text_l = str(text or "").lower()
    traits = {}
    components = []
    for trait, keywords in UPGRADE_TRAIT_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in text_l:
                score += 12
                components.append(keyword)
        if score:
            traits[trait] = min(100, score)
    if not traits:
        return {}, []
    return traits, sorted(set(components))[:12]


def extract_team_upgrade_sections(text, team_names):
    sections = {}
    lower = text.lower()
    aliases = {
        "red bull racing": ["red bull", "oracle red bull"],
        "mclaren": ["mclaren"],
        "ferrari": ["ferrari", "scuderia ferrari"],
        "mercedes": ["mercedes", "silver arrows"],
        "aston martin": ["aston martin"],
        "alpine": ["alpine"],
        "williams": ["williams"],
        "haas": ["haas"],
        "racing bulls": ["racing bulls", "rb", "visa cash app"],
        "audi": ["audi", "sauber", "kick sauber"],
        "cadillac": ["cadillac"],
    }
    for team in team_names:
        team_key = str(team or "").lower()
        names = [team_key] + aliases.get(team_key, [])
        hits = []
        for name in names:
            if not name:
                continue
            for match in re.finditer(re.escape(name), lower):
                start = max(0, match.start() - 450)
                end = min(len(text), match.end() + 900)
                hits.append(text[start:end])
        if hits:
            sections[team] = " ".join(hits[:3])
    return sections


def trait_alignment_score(traits, profile, weather_summary, regulation_context):
    if not traits:
        return None
    dominance = str(profile.get("dominance", "")).lower()
    speed = str(profile.get("speed_profile", "")).lower()
    tyre = str(profile.get("tyre_stress", "")).lower()
    overtaking = str(profile.get("overtaking", "")).lower()
    rain = safe_float(weather_summary.get("rain_score")) or 0
    heat = safe_float(weather_summary.get("heat_score")) or 0
    wind = safe_float(weather_summary.get("wind_score")) or 0
    weights = {trait: 0.35 for trait in traits}
    if "straight" in speed or "low drag" in dominance:
        weights["straight_line"] = weights.get("straight_line", 0) + 0.9
        weights["aero_efficiency"] = weights.get("aero_efficiency", 0) + 0.45
    if "aero" in dominance or "downforce" in dominance:
        weights["downforce"] = weights.get("downforce", 0) + 0.75
        weights["aero_efficiency"] = weights.get("aero_efficiency", 0) + 0.65
    if "traction" in speed or "track position" in dominance or "low" in overtaking:
        weights["traction"] = weights.get("traction", 0) + 0.55
        weights["braking"] = weights.get("braking", 0) + 0.45
        weights["downforce"] = weights.get("downforce", 0) + 0.45
    if tyre in {"high", "medium-high"}:
        weights["tyre_management"] = weights.get("tyre_management", 0) + 0.65
        weights["cooling"] = weights.get("cooling", 0) + 0.35
    if heat >= 60:
        weights["cooling"] = weights.get("cooling", 0) + 0.7
        weights["tyre_management"] = weights.get("tyre_management", 0) + 0.4
    if wind >= 55:
        weights["stability"] = weights.get("stability", 0) + 0.55
    if rain >= 35:
        weights["stability"] = weights.get("stability", 0) + 0.35
        weights["traction"] = weights.get("traction", 0) + 0.35
    for trait in regulation_context.get("boost_traits", []):
        weights[trait] = weights.get(trait, 0) + 0.3
    return weighted_average([(traits.get(k), weights.get(k, 0.25)) for k in set(traits) | set(weights)])


def regulation_context_for_season(season):
    season = safe_int(season) or now_local().year
    if season >= 2027:
        ctx = dict(REGULATION_CONTEXTS["2026+"])
        ctx["era"] = REGULATION_CONTEXTS["2027+"]["era"]
        ctx["notes"] = REGULATION_CONTEXTS["2026+"]["notes"] + REGULATION_CONTEXTS["2027+"]["notes"]
        ctx["boost_traits"] = sorted(set(REGULATION_CONTEXTS["2026+"]["boost_traits"] + REGULATION_CONTEXTS["2027+"]["boost_traits"]))
        ctx["source_urls"] = ["https://www.fia.com/news/fia-statement-amendments-2026-f1-regulations", "https://www.fia.com/news/new-era-competition-fia-showcases-future-focused-formula-1-regulations-2026-and-beyond"]
        return ctx
    if season == 2026:
        ctx = dict(REGULATION_CONTEXTS["2026+"])
        ctx["source_urls"] = ["https://www.fia.com/news/new-era-competition-fia-showcases-future-focused-formula-1-regulations-2026-and-beyond"]
        return ctx
    if season == 2025:
        ctx = dict(REGULATION_CONTEXTS["2025"])
        ctx["source_urls"] = ["FIA bodywork flexibility directive reporting"]
        return ctx
    return {"era": "stable pre-2026 regulation era", "notes": ["No special regulation-era modifier beyond normal track and car traits."], "boost_traits": [], "source_urls": []}


def regulation_fit_score_for_driver(team, profile, weather_summary, regulation_context, car_performance=None, reliability=None, openf1_car=None):
    base = weighted_average([
        (team_track_fit_score(team, profile), 0.42),
        (car_performance, 0.30),
        (reliability, 0.16),
        (openf1_car, 0.12),
    ])
    if base is None:
        base = 50
    boosts = regulation_context.get("boost_traits", [])
    dominance = str(profile.get("dominance", "")).lower()
    speed = str(profile.get("speed_profile", "")).lower()
    if "straight_line" in boosts and "straight" in speed:
        base += 4
    if "aero_efficiency" in boosts and ("aero" in dominance or "downforce" in dominance):
        base += 4
    if "power_efficiency" in boosts and "straight" in speed:
        base += 2
    if "cooling" in boosts and (safe_float(weather_summary.get("heat_score")) or 0) >= 60:
        base += 3
    return max(0, min(100, base))


def fetch_upgrade_package_context(race, drivers, profile, weather_summary, regulation_context):
    if not UPGRADES_ENABLED:
        return {"provider_status": "disabled", "sources": [], "team_scores": {}, "team_traits": {}, "notes": []}
    teams = sorted(set(d.get("team") for d in drivers if d.get("team")))
    sources = []
    team_traits = {team: {} for team in teams}
    notes = []
    for url in candidate_fia_upgrade_urls(race):
        text = fetch_text_from_trusted_url(url)
        if not text or len(text) < 400:
            continue
        sources.append(url)
        sections = extract_team_upgrade_sections(text, teams)
        for team, section in sections.items():
            traits, components = classify_upgrade_text(section)
            if not traits:
                continue
            merged = team_traits.setdefault(team, {})
            for trait, value in traits.items():
                merged[trait] = max(merged.get(trait, 0), value)
            notes.append({"team": team, "source": url, "components": components, "excerpt": section[:420]})
    team_scores = {}
    for team, traits in team_traits.items():
        score = trait_alignment_score(traits, profile, weather_summary, regulation_context)
        if score is not None:
            # Conservative cap: upgrades can move predictions, but they must not overwhelm race pace, grid, or car data.
            team_scores[team] = max(40, min(88, score))
    status = "official_upgrade_data_used" if team_scores else "no_current_official_upgrade_data_found"
    return {"provider_status": status, "sources": sources, "team_scores": team_scores, "team_traits": team_traits, "notes": notes[:20]}


def official_calendar_context_for_season(season, race=None):
    ctx = {"enabled": OFFICIAL_CALENDAR_ENABLED, "source": "Jolpica/ICS primary", "official_url": None, "status": "not_checked", "race_name_seen": False}
    if not OFFICIAL_CALENDAR_ENABLED:
        ctx["status"] = "disabled"
        return ctx
    url = OFFICIAL_F1_CALENDAR_URL.format(year=season)
    ctx["official_url"] = url
    response = safe_get(url, timeout=25, use_cache=False, optional_404=True)
    if not response:
        ctx["status"] = "official_f1_calendar_unavailable_using_ics_jolpica"
        return ctx
    text = strip_html(response.text).lower()
    race_name = str((race or {}).get("raceName", "")).lower()
    ctx["status"] = "official_f1_calendar_page_reachable"
    ctx["race_name_seen"] = bool(race_name and any(token in text for token in tokenize(race_name)))
    return ctx


def fetch_latest_available_standings_with_fallback(season):
    for year in range(safe_int(season) or now_local().year, ML_START_YEAR - 1, -1):
        drivers = fetch_driver_standings(year)
        constructors = fetch_constructor_standings(year)
        if drivers and constructors:
            return drivers, constructors, {"standings_season_used": year, "fallback_used": year != season}
    return [], [], {"standings_season_used": None, "fallback_used": True}

def get_prediction_stage(current_round_data, event_start):
    has_qualifying = bool(current_round_data.get("qualifying"))
    has_results = bool(current_round_data.get("results"))
    if has_results and now_local() > event_start:
        return "post-race-data", "Post-race data, historical update"
    if has_qualifying:
        return "post-qualifying", "Post-qualifying prediction"
    if event_start - now_local() <= timedelta(days=3):
        return "race-weekend", "Race-weekend prediction"
    return "pre-weekend", "Pre-weekend prediction"


def get_prediction_weights(profile, weather_summary, stage, regulation_context=None, upgrade_context=None):
    overtaking = str(profile.get("overtaking", "unknown")).lower()
    tyre = str(profile.get("tyre_stress", "unknown")).lower()
    dominance = str(profile.get("dominance", "")).lower()
    speed = str(profile.get("speed_profile", "")).lower()
    rain = weather_summary.get("rain_score", 0)
    heat = weather_summary.get("heat_score", 0)
    wind = weather_summary.get("wind_score", 0)
    regulation_context = regulation_context or {}
    upgrade_context = upgrade_context or {}

    weights = {
        "ml_win_probability": 0.08,
        "ml_podium_probability": 0.12,
        "ml_top10_probability": 0.06,
        "driver_form": 0.07,
        "driver_skill": 0.06,
        "car_performance": 0.09,
        "constructor_form": 0.07,
        "recent_result": 0.05,
        "qualifying": 0.08,
        "circuit_history": 0.07,
        "race_pace": 0.07,
        "pit_execution": 0.05,
        "team_strategy": 0.05,
        "reliability": 0.04,
        "team_track_fit": 0.06,
        "weather_adaptation": 0.04,
        "track_trait_fit": 0.05,
        "sprint_performance": 0.03,
        "current_season_car_performance": 0.06,
        "current_season_recent_form": 0.04,
        "openf1_session_result": 0.04,
        "openf1_starting_grid": 0.04,
        "openf1_lap_pace": 0.05,
        "openf1_pit_execution": 0.03,
        "openf1_stint_strength": 0.03,
        "openf1_telemetry_speed": 0.04,
        "openf1_car_performance": 0.07,
        "upgrade_package_impact": 0.05,
        "regulation_fit": 0.04,
        "calendar_confidence": 0.01,
        "fastf1_race_pace": 0.06,
        "fastf1_consistency": 0.03,
        "fastf1_tyre_stint": 0.02,
    }

    if stage == "post-qualifying":
        weights["qualifying"] += 0.08
        weights["ml_podium_probability"] += 0.03
    elif stage == "race-weekend":
        weights["fastf1_race_pace"] += 0.05
        weights["fastf1_consistency"] += 0.03
    else:
        weights["driver_form"] += 0.03
        weights["car_performance"] += 0.03
        weights["circuit_history"] += 0.02

    if "low" in overtaking:
        weights["qualifying"] += 0.08
        weights["pit_execution"] += 0.03
        weights["team_strategy"] += 0.03
    if "good" in overtaking:
        weights["race_pace"] += 0.04
        weights["team_strategy"] += 0.03
    if tyre in {"high", "medium-high"} or heat >= 60:
        weights["race_pace"] += 0.04
        weights["pit_execution"] += 0.03
        weights["fastf1_tyre_stint"] += 0.03
    if rain >= 35:
        weights["reliability"] += 0.05
        weights["weather_adaptation"] += 0.07
        weights["team_strategy"] += 0.04
    if wind >= 60:
        weights["reliability"] += 0.03
        weights["weather_adaptation"] += 0.03
    if "straight-line" in speed or "aero" in dominance or "downforce" in dominance:
        weights["car_performance"] += 0.04
        weights["team_track_fit"] += 0.04
        weights["track_trait_fit"] += 0.03
    if regulation_context.get("boost_traits"):
        weights["regulation_fit"] += 0.04
        weights["car_performance"] += 0.02
    if upgrade_context.get("team_scores"):
        weights["upgrade_package_impact"] += 0.05
        weights["track_trait_fit"] += 0.02

    total = sum(max(0, value) for value in weights.values())
    return {key: max(0, value) / total for key, value in weights.items()}


def rank_prediction(drivers, constructor_standings, last_results, current_round_data, historical_records, profile, weather_summary, ml_outputs, fastf1_scores, openf1_scores, upgrade_context, regulation_context, calendar_context, season, current_round, stage):
    weights = get_prediction_weights(profile, weather_summary, stage, regulation_context, upgrade_context)

    driver_points = {d["driver_id"]: d["points"] for d in drivers}
    driver_form = normalize_scores(driver_points)
    constructor_form = constructor_score_map(constructor_standings)
    current_season_car = collect_current_season_constructor_performance(season, current_round)
    recent_current_season_car = collect_recent_current_season_constructor_form(season, current_round)
    openf1_team_scores = openf1_scores.get("team_scores", {}) if openf1_scores else {}
    upgrade_team_scores = upgrade_context.get("team_scores", {}) if upgrade_context else {}

    for team in set(constructor_form) | set(current_season_car) | set(recent_current_season_car) | set(openf1_team_scores) | set(upgrade_team_scores):
        constructor_form[team] = weighted_average([
            (constructor_form.get(team), 0.38),
            (current_season_car.get(team), 0.30),
            (recent_current_season_car.get(team), 0.18),
            (openf1_team_scores.get(team), 0.12),
            (upgrade_team_scores.get(team), 0.08),
        ])

    recent = current_result_score_map(last_results)
    qualifying = qualifying_score_map(current_round_data)
    sprint = sprint_score_map(current_round_data)
    circuit = circuit_history_score_map(historical_records)
    race_pace = race_pace_score_map(historical_records, current_round_data)
    driver_pit, team_pit = pit_execution_score_maps(historical_records, current_round_data)
    driver_strategy, team_strategy_map = strategy_gain_score_maps(historical_records)
    reliability = reliability_score_map(historical_records)
    constructor_circuit = constructor_circuit_score_map(historical_records)

    predictions = []
    for driver in drivers:
        driver_id = driver["driver_id"]
        team = driver["team"]
        code = driver_code_guess(driver["name"])
        ml = ml_outputs.get(driver_id, {})

        openf1_driver_car = openf1_scores.get("openf1_car_performance", {}).get(driver_id) if openf1_scores else None
        upgrade_score = upgrade_team_scores.get(team)
        track_fit = team_track_fit_score(team, profile, constructor_circuit.get(team))
        car_performance = weighted_average([
            (constructor_form.get(team), 0.42),
            (current_season_car.get(team), 0.20),
            (recent_current_season_car.get(team), 0.10),
            (constructor_circuit.get(team), 0.08),
            (track_fit, 0.08),
            (openf1_driver_car, 0.08),
            (upgrade_score, 0.08),
        ])
        pit_execution = weighted_average([(driver_pit.get(driver_id), 0.45), (team_pit.get(team), 0.55)])
        team_strategy = weighted_average([(driver_strategy.get(driver_id), 0.45), (team_strategy_map.get(team), 0.4), (team_pit.get(team), 0.15)])
        driver_skill = weighted_average([
            (driver_form.get(driver_id), 0.4),
            (circuit.get(driver_id), 0.25),
            (race_pace.get(driver_id), 0.2),
            (reliability.get(driver_id), 0.15),
        ])
        weather_adaptation = weighted_average([
            (reliability.get(driver_id), 0.35),
            (circuit.get(driver_id), 0.25),
            (race_pace.get(driver_id), 0.20),
            (team_strategy, 0.20),
        ])
        track_trait_fit = weighted_average([
            (track_fit, 0.5),
            (car_performance, 0.35),
            (pit_execution, 0.15),
        ])
        regulation_fit = regulation_fit_score_for_driver(team, profile, weather_summary, regulation_context, car_performance, reliability.get(driver_id), openf1_driver_car)
        calendar_confidence = 80 if calendar_context.get("status") == "official_f1_calendar_page_reachable" else 55

        component_scores = {
            "ml_win_probability": ml.get("ml_win_probability"),
            "ml_podium_probability": ml.get("ml_podium_probability"),
            "ml_top10_probability": ml.get("ml_top10_probability"),
            "driver_form": driver_form.get(driver_id),
            "driver_skill": driver_skill,
            "car_performance": car_performance,
            "constructor_form": constructor_form.get(team),
            "current_season_car_performance": current_season_car.get(team),
            "current_season_recent_form": recent_current_season_car.get(team),
            "openf1_session_result": openf1_scores.get("openf1_session_result", {}).get(driver_id) if openf1_scores else None,
            "openf1_starting_grid": openf1_scores.get("openf1_starting_grid", {}).get(driver_id) if openf1_scores else None,
            "openf1_lap_pace": openf1_scores.get("openf1_lap_pace", {}).get(driver_id) if openf1_scores else None,
            "openf1_pit_execution": openf1_scores.get("openf1_pit_execution", {}).get(driver_id) if openf1_scores else None,
            "openf1_stint_strength": openf1_scores.get("openf1_stint_strength", {}).get(driver_id) if openf1_scores else None,
            "openf1_telemetry_speed": openf1_scores.get("openf1_telemetry_speed", {}).get(driver_id) if openf1_scores else None,
            "openf1_car_performance": openf1_scores.get("openf1_car_performance", {}).get(driver_id) if openf1_scores else None,
            "upgrade_package_impact": upgrade_score,
            "regulation_fit": regulation_fit,
            "calendar_confidence": calendar_confidence,
            "recent_result": recent.get(driver_id),
            "qualifying": qualifying.get(driver_id),
            "circuit_history": circuit.get(driver_id),
            "race_pace": race_pace.get(driver_id),
            "pit_execution": pit_execution,
            "team_strategy": team_strategy,
            "reliability": reliability.get(driver_id),
            "team_track_fit": track_fit,
            "weather_adaptation": weather_adaptation,
            "track_trait_fit": track_trait_fit,
            "sprint_performance": sprint.get(driver_id),
            "fastf1_race_pace": fastf1_scores.get("fastf1_race_pace", {}).get(code),
            "fastf1_consistency": fastf1_scores.get("fastf1_consistency", {}).get(code),
            "fastf1_tyre_stint": fastf1_scores.get("fastf1_tyre_stint", {}).get(code),
        }

        score = weighted_average([(component_scores.get(k), w) for k, w in weights.items()]) or 0
        available_weight = sum(w for k, w in weights.items() if component_scores.get(k) is not None)
        confidence = min(100, max(0, available_weight * 100))

        reasons = sorted(
            [(k, v) for k, v in component_scores.items() if v is not None],
            key=lambda item: item[1] * weights.get(item[0], 0),
            reverse=True,
        )
        reason_names = [PREDICTION_LABELS.get(k, k) for k, v in reasons[:5] if v >= 35] or ["limited cached data evidence"]

        predictions.append({
            "name": driver["name"],
            "team": team,
            "driver_id": driver_id,
            "score": round(score, 2),
            "confidence": round(confidence, 1),
            "reason": "; ".join(reason_names),
            "component_scores": {k: round(v, 2) if v is not None else None for k, v in component_scores.items()},
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
        "source": "Hybrid full-data cache model: Jolpica full history + OpenF1 when free/working + FastF1 + Open-Meteo + ICS",
        "logic": "Mintlify-style feature groups plus full-data racing ensemble: grid, driver history, current-season car performance, team form, car telemetry, circuit experience, track traits, weather traits, tyre strategy, lap pace, pit stops, sprint, reliability, and race simulation scenarios",
        "prediction_stage": stage,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "available_components": {
            "ml_outputs": len(ml_outputs),
            "driver_form": len(driver_form),
            "constructor_form": len(constructor_form),
            "current_season_car_performance": len(current_season_car),
            "current_season_recent_form": len(recent_current_season_car),
            "openf1_provider_status": openf1_scores.get("provider_status") if openf1_scores else "not_used",
            "openf1_car_performance": len(openf1_scores.get("openf1_car_performance", {})) if openf1_scores else 0,
            "openf1_telemetry_speed": len(openf1_scores.get("openf1_telemetry_speed", {})) if openf1_scores else 0,
            "upgrade_provider_status": upgrade_context.get("provider_status") if upgrade_context else "not_used",
            "upgrade_package_impact": len(upgrade_team_scores),
            "regulation_era": regulation_context.get("era"),
            "official_calendar_status": calendar_context.get("status"),
            "recent_result": len(recent),
            "qualifying": len(qualifying),
            "sprint": len(sprint),
            "circuit_history": len(circuit),
            "race_pace": len(race_pace),
            "pit_execution_drivers": len(driver_pit),
            "strategy_drivers": len(driver_strategy),
            "reliability": len(reliability),
            "fastf1_sessions_loaded": fastf1_scores.get("sessions_loaded", []),
            "backfill_used_this_run": BACKFILL_BUDGET.used,
        },
    }
    return text, top10, model


def get_dynamic_team_fit(top10, constructor_standings):
    scores = {}
    for team, score in constructor_score_map(constructor_standings).items():
        scores[team] = scores.get(team, 0) + score * 0.45
    for idx, item in enumerate(top10):
        team = item.get("team") or "Unknown Team"
        scores[team] = scores.get(team, 0) + (10 - idx) * 8
    return [team for team, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]]


def pit_window_from_profile(profile, weather_summary):
    rain = weather_summary.get("rain_score", 0)
    tyre = profile.get("tyre_stress", "unknown")
    if rain >= 50:
        return "Delay fixed dry-tyre stops. Watch radar and react to rain onset."
    if tyre == "high":
        return "Lap 14-24 for aggressive two-stop, lap 22-32 for conservative one-stop."
    if tyre == "medium-high":
        return "Lap 16-28, with safety car flexibility."
    if tyre == "medium":
        return "Lap 18-32 for normal dry strategy."
    if tyre == "low-medium":
        return "Lap 24-40 if track position is secure."
    return "Unavailable until more cached pit-stop history is available."



def notification_status(event):
    """
    Predictions are generated on every run.
    Email and GitHub Issue notifications are gated to avoid spam.

    Notifications are allowed when:
    - FORCE_NOTIFY=true, or
    - the matched upcoming calendar event is within NOTIFICATION_WINDOW_HOURS.
    """
    if FORCE_NOTIFY:
        return {
            "allowed": True,
            "reason": "FORCE_NOTIFY=true",
            "hours_until_event": None,
        }

    start = event.get("start") if event else None
    if start is None:
        return {
            "allowed": False,
            "reason": "No event start time found.",
            "hours_until_event": None,
        }

    hours_until = (start - now_local()).total_seconds() / 3600

    if 0 <= hours_until <= NOTIFICATION_WINDOW_HOURS:
        return {
            "allowed": True,
            "reason": f"Event starts within {NOTIFICATION_WINDOW_HOURS} hours.",
            "hours_until_event": round(hours_until, 2),
        }

    if hours_until < 0:
        return {
            "allowed": False,
            "reason": "Matched event has already started or passed.",
            "hours_until_event": round(hours_until, 2),
        }

    return {
        "allowed": False,
        "reason": f"Event is more than {NOTIFICATION_WINDOW_HOURS} hours away.",
        "hours_until_event": round(hours_until, 2),
    }


def notification_status_for_events(events):
    if FORCE_NOTIFY:
        return {
            "allowed": True,
            "reason": "FORCE_NOTIFY=true",
            "hours_until_event": None,
            "matched_event": None,
        }

    if not events:
        return {
            "allowed": False,
            "reason": "No Sprint/Race output target was selected.",
            "hours_until_event": None,
            "matched_event": None,
        }

    statuses = []
    for event in events:
        status = notification_status(event)
        status["matched_event"] = event.get("title")
        statuses.append(status)

    allowed = [status for status in statuses if status.get("allowed")]
    if allowed:
        allowed.sort(key=lambda item: item.get("hours_until_event") if item.get("hours_until_event") is not None else 9999)
        return allowed[0]

    future_statuses = [status for status in statuses if status.get("hours_until_event") is not None and status.get("hours_until_event") >= 0]
    if future_statuses:
        future_statuses.sort(key=lambda item: item.get("hours_until_event"))
        status = future_statuses[0]
        return {
            "allowed": False,
            "reason": f"Nearest Sprint/Race target is more than {NOTIFICATION_WINDOW_HOURS} hours away.",
            "hours_until_event": status.get("hours_until_event"),
            "matched_event": status.get("matched_event"),
        }

    return statuses[0]


def maybe_send_outputs(title, briefing, event_or_events):
    """
    Always generate and commit dashboard data.
    Only send email and update GitHub issue inside notification window.
    """
    events = event_or_events if isinstance(event_or_events, list) else [event_or_events]
    status = notification_status_for_events(events)
    print(f"Notification gate: allowed={status['allowed']} reason={status['reason']} hours_until_event={status['hours_until_event']} matched_event={status.get('matched_event')}")

    if not status["allowed"]:
        return status

    safe_step("Create or update issue", create_or_update_issue, title, briefing)
    safe_step("Send email", send_email, title, briefing)
    return status


def generate_briefing(event, race, profile, weather, top10_text, prediction_model, team_fit, upgrade_context, regulation_context, calendar_context):
    """
    Clean public briefing.

    The full model still runs internally. This output is deliberately short so
    email, GitHub Issue, Markdown, and the website stay readable.
    """
    target_type = prediction_model.get("output_target_type", classify_output_target_event(event))
    title_prefix = "Sprint" if target_type == "sprint" else "Race" if target_type == "race" else "F1"
    title = f"F1 {title_prefix} Briefing: {event['title']}"
    start_str = event["start"].strftime("%A, %d %B %Y, %I:%M %p %Z")

    top_prediction = top10_text if top10_text else "Prediction unavailable until enough data is cached."

    team_text = "\n".join(
        f"{idx + 1}. {team}" for idx, team in enumerate((team_fit or [])[:5])
    ) if team_fit else "Unavailable"

    upgrade_scores = upgrade_context.get("team_scores") or {}
    upgrade_traits = upgrade_context.get("team_traits") or {}
    upgrade_lines = []
    for team, score in sorted(upgrade_scores.items(), key=lambda item: item[1], reverse=True)[:3]:
        traits = upgrade_traits.get(team, {})
        useful_traits = [trait.replace("_", " ") for trait, value in traits.items() if value]
        trait_text = ", ".join(useful_traits[:3]) if useful_traits else "no clear trait match"
        upgrade_lines.append(f"- {team}: {score:.1f}/100, {trait_text}")
    if not upgrade_lines:
        upgrade_lines = ["- No trusted upgrade-package signal found for this event."]

    weights = prediction_model.get("weights", {}) or {}
    top_weights = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:5]
    model_lines = [
        f"- {key.replace('_', ' ')}: {value * 100:.1f}%"
        for key, value in top_weights
    ] or ["- Weight audit unavailable"]

    available = prediction_model.get("available_components", {}) or {}
    source_lines = [
        f"- Stage: {prediction_model.get('prediction_stage_label', 'Unknown')}",
        f"- ML model: {'loaded' if prediction_model.get('ml_model_loaded') else 'fallback mode'}",
        f"- OpenF1: {available.get('openf1_provider_status', available.get('openf1_status', 'fallback if unavailable'))}",
        f"- FastF1 sessions: {available.get('fastf1_sessions_loaded', [])}",
        f"- Calendar check: {calendar_context.get('status', 'not checked')}",
    ]

    regulation_notes = regulation_context.get("notes", []) or []
    regulation_text = "\n".join(f"- {note}" for note in regulation_notes[:2]) if regulation_notes else "- No special regulation modifier beyond normal model traits."

    briefing = f"""# {title}

Generated: {now_local().strftime("%A, %d %B %Y, %I:%M %p %Z")}

## Event

- Target: {title_prefix}
- Start: {start_str}
- Circuit: {profile['circuit']}
- Location: {profile['city']}, {profile['country']}

## Prediction

{top_prediction}

## Track and weather

- Key car trait: {profile['car_trait']}
- Track profile: {profile['speed_profile']}
- Overtaking: {profile['overtaking']}
- Tyre stress: {profile['tyre_stress']}
- Safety car/DNF risk proxy: {profile['safety_car']}
- Weather: {weather['temperature']}, rain {weather['rain']}, wind {weather['wind']}
- Weather impact: {weather['impact']}

## Strategy

- Baseline: {profile['strategy_bias']}
- Pit window: {pit_window_from_profile(profile, weather)}
- Main risk: tyre drop-off, safety-car timing, traffic after pit stop, and weather crossover.

## Team fit

{team_text}

## Upgrade impact

{chr(10).join(upgrade_lines)}

## Regulation context

Era: {regulation_context.get('era')}

{regulation_text}

## Main model signals

{chr(10).join(model_lines)}

## Source status

{chr(10).join(source_lines)}

---

Predictions are estimates, not guaranteed race results.
"""
    return title, briefing


def save_markdown(event, briefing):
    BRIEFINGS_DIR.mkdir(exist_ok=True)
    date = event["start"].strftime("%Y-%m-%d")
    slug = make_slug(event["title"])
    path = BRIEFINGS_DIR / f"{date}-{slug}.md"
    path.write_text(briefing, encoding="utf-8")
    return path


def save_run_status(status, details):
    BRIEFINGS_DIR.mkdir(exist_ok=True)
    path = BRIEFINGS_DIR / "latest-run-status.md"
    path.write_text(f"# F1 Race Intel Run Status\n\nGenerated: {now_local().strftime('%A, %d %B %Y, %I:%M %p %Z')}\n\nStatus: {status}\n\n## Details\n\n{details}\n", encoding="utf-8")
    return path


def update_index(event, race, profile, weather, markdown_path, title, top10, team_fit, prediction_model, upgrade_context, regulation_context, calendar_context):
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
        "circuit_key": profile["circuit_key"],
        "meeting_key": profile["meeting_key"],
        "track_type": profile["track_type"],
        "dominance": profile["dominance"],
        "speed_profile": profile["speed_profile"],
        "car_trait": profile["car_trait"],
        "overtaking": profile["overtaking"],
        "tyre_stress": profile["tyre_stress"],
        "safety_car": profile["safety_car"],
        "strategy_bias": profile["strategy_bias"],
        "pit_window": pit_window_from_profile(profile, weather),
        "setup": profile["setup"],
        "team_fit": team_fit,
        "weather": weather,
        "top10": top10,
        "prediction_model": prediction_model,
        "upgrade_context": upgrade_context,
        "regulation_context": regulation_context,
        "official_calendar_context": calendar_context,
        "prompt_requirement_checklist": PROMPT_REQUIREMENT_CHECKLIST,
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
        except Exception:
            briefings = []
    else:
        briefings = []

    briefings = [x for x in briefings if x.get("path") != entry["path"]]
    briefings.insert(0, entry)
    briefings = briefings[:60]
    index_path.write_text(json.dumps({"briefings": briefings}, indent=2, ensure_ascii=False), encoding="utf-8")
    return index_path


def save_debug(payload):
    path = DATA_CACHE_DIR / "latest-model-debug.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def send_email(subject, body):
    if not EMAIL_ENABLED:
        print("Email disabled.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        html = "<html><body style='font-family:Arial,sans-serif;line-height:1.55;background:#050505;color:#f5f0ea;padding:24px;'><pre style='white-space:pre-wrap;font-family:Arial,sans-serif'>" + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre></body></html>"
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("Email sent.")
        return True
    except Exception as error:
        print(f"Email failed: {error}")
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
                github_api("PATCH", f"/issues/{issue['number']}", {"body": body})
                print(f"Updated issue #{issue['number']}.")
                return
    github_api("POST", "/issues", {"title": title, "body": body, "labels": ["f1-briefing"]})
    print("Created issue.")


def commit_and_push(paths):
    paths = [Path(p) for p in paths if p]
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)

    for path in paths:
        if path.exists():
            subprocess.run(["git", "add", str(path)], check=True)

    # Include full-race cache files generated this run.
    if FULL_RACE_CACHE_DIR.exists():
        subprocess.run(["git", "add", str(FULL_RACE_CACHE_DIR)], check=True)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("No file changes to commit.")
        return
    subprocess.run(["git", "commit", "-m", "Update F1 full-data model and briefing"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("Committed and pushed generated data.")


def write_skip_outputs(subject, details):
    status_path = save_run_status("Skipped", details)
    safe_step("Commit status", commit_and_push, [status_path])
    safe_step("Issue status", create_or_update_issue, "F1 Race Intel Status", details)
    safe_step("Email status", send_email, subject, details)


def build_single_output_payload(event, bundle):
    """
    Builds one compact output payload for a Sprint or Race target.

    Practice, qualifying, sprint qualifying, FastF1, OpenF1, weather, upgrades,
    and historical data may be used as inputs, but only Sprint/Race targets are
    exposed as output.
    """
    target_type = classify_output_target_event(event)
    if target_type not in {"sprint", "race"}:
        return {
            "ok": False,
            "event": event,
            "error": f"Skipping non-output event: {event.get('title')}",
        }

    race = find_best_race(event)
    if not race:
        return {
            "ok": False,
            "event": event,
            "error": f"Could not match Jolpica race for {event.get('title')}",
        }

    season = safe_int(race.get("season")) or event["start"].year
    round_no = race.get("round")

    current_round_data = fetch_round_data_cached(
        season,
        round_no,
        allow_backfill=False,
        force_fetch=True,
        race=race,
        training_mode=False,
    )

    driver_standings, constructor_standings, standings_context = fetch_latest_available_standings_with_fallback(season)
    last_results = fetch_last_results(season)
    historical_records = fetch_historical_same_circuit(race, years_back=5)

    if not driver_standings:
        return {
            "ok": False,
            "event": event,
            "race": race,
            "error": f"Matched {race.get('raceName')} but driver standings are unavailable.",
        }

    drivers = standings_to_drivers(driver_standings)
    weather = fetch_weather_for_race(race, event["start"])
    historical_weather = safe_step("Historical weather", fetch_historical_weather_summary, race, 5) or {}
    profile = infer_track_profile(race, historical_records, weather, historical_weather)
    regulation_context = regulation_context_for_season(season) if F1_REGULATIONS_ENABLED else {"era": "disabled", "notes": [], "boost_traits": []}
    upgrade_context = fetch_upgrade_package_context(race, drivers, profile, weather, regulation_context)
    calendar_context = official_calendar_context_for_season(season, race)

    stage, stage_label = get_prediction_stage(current_round_data, event["start"])

    # Make the target explicit. The same round data may contain qualifying or sprint results,
    # but output is restricted to sprint/race.
    if target_type == "sprint":
        stage_label = f"Sprint prediction, {stage_label}"
    elif target_type == "race":
        stage_label = f"Race prediction, {stage_label}"

    ml_outputs, ml_debug = ml_predict_probabilities(drivers, race, current_round_data, bundle)
    openf1_scores = safe_step("OpenF1 enhancement", openf1_enhancement_scores, race, drivers) or {"provider_status": "failed"}
    fastf1_scores = safe_step("FastF1 enhancement", fastf1_enhancement_scores, season, round_no) or {"sessions_loaded": []}

    top10_text, top10, prediction_model = rank_prediction(
        drivers=drivers,
        constructor_standings=constructor_standings,
        last_results=last_results,
        current_round_data=current_round_data,
        historical_records=historical_records,
        profile=profile,
        weather_summary=weather,
        ml_outputs=ml_outputs,
        fastf1_scores=fastf1_scores,
        openf1_scores=openf1_scores,
        upgrade_context=upgrade_context,
        regulation_context=regulation_context,
        calendar_context=calendar_context,
        season=season,
        current_round=round_no,
        stage=stage,
    )

    prediction_model["prediction_stage_label"] = stage_label
    prediction_model["output_target_type"] = target_type
    prediction_model["ml_model_loaded"] = bool(bundle)
    prediction_model["ml_model_meta"] = {
        "trained_at": bundle.get("trained_at") if bundle else None,
        "latest_completed_race_id": bundle.get("latest_completed_race_id") if bundle else None,
        "metrics": bundle.get("metrics") if bundle else None,
    }

    team_fit = get_dynamic_team_fit(top10, constructor_standings)
    title, briefing = generate_briefing(
        event,
        race,
        profile,
        weather,
        top10_text,
        prediction_model,
        team_fit,
        upgrade_context,
        regulation_context,
        calendar_context,
    )

    return {
        "ok": True,
        "event": event,
        "race": race,
        "season": season,
        "round_no": round_no,
        "target_type": target_type,
        "title": title,
        "briefing": briefing,
        "profile": profile,
        "weather": weather,
        "historical_weather": historical_weather,
        "top10_text": top10_text,
        "top10": top10,
        "team_fit": team_fit,
        "prediction_model": prediction_model,
        "ml_debug": ml_debug,
        "openf1_scores": openf1_scores,
        "fastf1_scores": fastf1_scores,
        "upgrade_context": upgrade_context,
        "regulation_context": regulation_context,
        "calendar_context": calendar_context,
        "standings_context": standings_context,
    }


def strip_briefing_heading(briefing):
    lines = str(briefing or "").splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    # Remove duplicate generated line from subsections; combined report already has one.
    cleaned = []
    for line in lines:
        if line.startswith("Generated:"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def combine_weekend_briefings(report_event, payloads, mode):
    if not payloads:
        return "F1 Race Intel: No Sprint/Race output target found", ""

    if len(payloads) == 1:
        return payloads[0]["title"], payloads[0]["briefing"]

    targets = "\n".join(
        f"- {payload['target_type'].title()}: {payload['event']['title']} at {payload['event']['start'].strftime('%A, %d %B %Y, %I:%M %p %Z')}"
        for payload in payloads
    )

    sections = []
    for payload in payloads:
        heading = f"## {payload['target_type'].title()} Target: {payload['event']['title']}"
        sections.append(f"{heading}\n\n{strip_briefing_heading(payload['briefing'])}")

    title = report_event["title"]
    briefing = f"""# {title}

Generated: {now_local().strftime("%A, %d %B %Y, %I:%M %p %Z")}

Output mode: {mode}

This briefing deliberately outputs only Sprint and Race predictions. Practice, Qualifying, Sprint Qualifying, weather, upgrades, OpenF1, FastF1, Jolpica, track traits, regulations, and historical cache data are used as supporting inputs only.

## Output targets

{targets}

---

{chr(10).join(sections)}

---

Generated by F1 Race Intel. Predictions are model estimates, not guaranteed race results.
"""
    return title, briefing


def run(force_retrain=False):
    ensure_dirs()
    require_env_vars()

    bundle = safe_step("Train/load full-data ML model", train_ml_model, force_retrain)
    if not bundle:
        bundle = load_ml_bundle()

    calendar = fetch_ics_calendar()
    mode, target_events = select_output_events(calendar)

    if not target_events:
        details = (
            f"No Sprint/Race output target selected.\\n\\n"
            f"Output mode: {mode}\\n"
            f"Reason: Manual runs use weekend mode; scheduled runs use today mode. "
            f"Practice, Qualifying, and Sprint Qualifying are ignored as direct outputs."
        )
        print(details)
        status_path = save_run_status("Skipped", details)
        safe_step("Commit status", commit_and_push, [status_path])
        return

    print("Selected output targets:")
    for event in target_events:
        print(f"- {event.get('target_type')}: {event.get('title')} at {event.get('start')}")

    payloads = []
    errors = []

    for event in target_events:
        payload = build_single_output_payload(event, bundle)
        if payload.get("ok"):
            payloads.append(payload)
        else:
            errors.append(payload.get("error", "Unknown target generation error"))
            print(f"Target skipped: {payload.get('error')}")

    if not payloads:
        details = "No Sprint/Race target could be generated.\\n\\n" + "\\n".join(f"- {error}" for error in errors)
        print(details)
        status_path = save_run_status("Skipped", details)
        safe_step("Commit status", commit_and_push, [status_path])
        return

    report_event = make_report_event([payload["event"] for payload in payloads], mode)
    title, briefing = combine_weekend_briefings(report_event, payloads, mode)

    primary = payloads[-1] if any(payload["target_type"] == "race" for payload in payloads) else payloads[0]
    markdown_path = save_markdown(report_event, briefing)
    index_path = update_index(
        report_event,
        primary["race"],
        primary["profile"],
        primary["weather"],
        markdown_path,
        title,
        primary["top10"],
        primary["team_fit"],
        primary["prediction_model"],
        primary["upgrade_context"],
        primary["regulation_context"],
        primary["calendar_context"],
    )

    generated_targets = ", ".join(f"{payload['target_type']}={payload['event']['title']}" for payload in payloads)
    status_details = (
        f"Generated Sprint/Race-only F1 briefing.\\n\\n"
        f"Output mode: {mode}\\n"
        f"Targets: {generated_targets}\\n"
        f"Backfill used this run: {BACKFILL_BUDGET.used}\\n"
        f"Errors: {'; '.join(errors) if errors else 'None'}"
    )
    status_path = save_run_status("Success", status_details)

    debug_path = save_debug({
        "generated_at": now_local().isoformat(),
        "output_mode": mode,
        "selected_targets": [
            {
                "title": payload["event"].get("title"),
                "target_type": payload["target_type"],
                "start": payload["event"].get("start"),
            }
            for payload in payloads
        ],
        "primary_target": primary["event"],
        "race": primary["race"],
        "payloads": payloads,
        "errors": errors,
        "notification_gate": notification_status_for_events([payload["event"] for payload in payloads]),
        "backfill": {
            "limit": BACKFILL_BUDGET.limit,
            "used": BACKFILL_BUDGET.used,
            "races": BACKFILL_BUDGET.fetched,
        },
    })

    paths = [
        markdown_path,
        index_path,
        status_path,
        debug_path,
        MODEL_BUNDLE_PATH,
        MODEL_META_PATH,
        DATA_CACHE_DIR / "ml_full_race_results_raw.csv",
        DATA_CACHE_DIR / "ml_full_race_features.csv",
    ]

    safe_step("Commit generated files", commit_and_push, paths)
    maybe_send_outputs(title, briefing, [payload["event"] for payload in payloads])

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-retrain", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    force = args.force_retrain or os.getenv("FORCE_RETRAIN", "false").lower() == "true"
    run(force_retrain=force)
