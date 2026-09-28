#!/usr/bin/env python3
"""
Midway Park Pickleball Court Checker
Features:
 - Next/Previous day navigation (arrows)
 - Date picker / Jump to today
 - Day View (detailed hourly timeline & bookings for all 6 courts)
 - Month View (interactive monthly calendar showing court availability for all 6 courts)
"""


import json
import subprocess
import re
import os
import tempfile
import urllib.parse
import base64
from datetime import datetime, timezone, timedelta



COURTS = [
    {"id": 190670, "park": "Midway", "name": "Court 1", "num": 1},
    {"id": 190671, "park": "Midway", "name": "Court 2", "num": 2},
    {"id": 190672, "park": "Midway", "name": "Court 3", "num": 3},
    {"id": 190673, "park": "Midway", "name": "Court 4", "num": 4},
    {"id": 190674, "park": "Midway", "name": "Court 5", "num": 5},
    {"id": 190675, "park": "Midway", "name": "Court 6", "num": 6},
    
    {"id": 190662, "park": "Fowler", "name": "Court 1", "num": 1},
    {"id": 190663, "park": "Fowler", "name": "Court 2", "num": 2},
    {"id": 190664, "park": "Fowler", "name": "Court 3", "num": 3},
    {"id": 190665, "park": "Fowler", "name": "Court 4", "num": 4},
    {"id": 190666, "park": "Fowler", "name": "Court 5", "num": 5},
    {"id": 190667, "park": "Fowler", "name": "Court 6", "num": 6},
    {"id": 190668, "park": "Fowler", "name": "Court 7", "num": 7},
    {"id": 190669, "park": "Fowler", "name": "Court 8", "num": 8},
]

for c in COURTS:
    # URL to view the calendar directly
    c["calendar_url"] = f"https://secure.rec1.com/GA/forsyth-county-ga/{c['park']}-Park-Pickleball-Court-{c['num']}/{c['id']}fcal"
    
    # URL to the catalog with a search filter for this specific court
    search_term = f"search={c['park']} Park Pickleball Court {c['num']}"
    b64_filter = base64.b64encode(search_term.encode('utf-8')).decode('utf-8')
    c["reserve_url"] = f"https://secure.rec1.com/GA/forsyth-county-ga/catalog?filter={b64_filter}"


BASE_URL = "https://secure.rec1.com/GA/forsyth-county-ga"
API_URL = f"{BASE_URL}/cal_ajax.php?request=publicCalendar"
PAGE_URL = f"{BASE_URL}/Midway-Park-Pickleball-Court-1/190670fcal"

EDT = timezone(timedelta(hours=-4))
COOKIE_FILE = os.path.join(tempfile.gettempdir(), "rec1_pickleball_cookies.txt")


def get_session_and_csrf():
    """Load the rec1 page to get a session cookie and CSRF tokens via curl."""
    if os.path.exists(COOKIE_FILE):
        os.remove(COOKIE_FILE)

    result = subprocess.run(
        [
            "curl", "-s",
            "-c", COOKIE_FILE,
            "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            PAGE_URL,
        ],
        capture_output=True, text=True, timeout=20,
    )
    html = result.stdout

    csrf_key_match = re.search(r'csrf-key"\s+content="([^"]+)"', html)
    csrf_token_match = re.search(r'csrf-token"\s+content="([^"]+)"', html)

    if not csrf_key_match or not csrf_token_match:
        raise RuntimeError("Could not extract CSRF tokens from rec1 page")

    return csrf_key_match.group(1), csrf_token_match.group(1)


def fetch_events_for_range(start_ts: int, end_ts: int, csrf_key: str, csrf_token: str):
    """Fetch all court events in one single fast call for all 6 courts."""
    fac_params = "&".join([f"facilities%5B%5D={c['id']}" for c in COURTS])
    body = (
        f"start={start_ts}&end={end_ts}"
        f"&{fac_params}"
        f"&eventsBubbled=true&eventLabelStyle=1"
        f"&{csrf_key}={csrf_token}"
    )

    result = subprocess.run(
        [
            "curl", "-s",
            "-b", COOKIE_FILE,
            "-X", "POST", API_URL,
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "-d", body,
        ],
        capture_output=True, text=True, timeout=25,
    )

    try:
        data = json.loads(result.stdout)
        if data.get("errors") and "session" in str(data["errors"]).lower():
            return None
        return data.get("events", [])
    except Exception as e:
        print(f"  ⚠ Error parsing events response: {e}")
        return []


def get_courts_for_date(target_date_str: str = None) -> dict:
    """Fetch data for a specific date (YYYY-MM-DD), default to today."""
    now_real = datetime.now(EDT)
    if target_date_str:
        try:
            target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=EDT)
        except ValueError:
            target_dt = now_real
    else:
        target_dt = now_real

    start_of_day = datetime(target_dt.year, target_dt.month, target_dt.day, 0, 0, 0, tzinfo=EDT)
    end_of_day = datetime(target_dt.year, target_dt.month, target_dt.day + 1, 0, 0, 0, tzinfo=EDT)
    start_ts = int(start_of_day.timestamp())
    end_ts = int(end_of_day.timestamp())

    csrf_key, csrf_token = get_session_and_csrf()
    raw_events = fetch_events_for_range(start_ts, end_ts, csrf_key, csrf_token)
    if raw_events is None:
        csrf_key, csrf_token = get_session_and_csrf()
        raw_events = fetch_events_for_range(start_ts, end_ts, csrf_key, csrf_token) or []

    # Map events to individual courts
    court_events = {c["id"]: [] for c in COURTS}
    for ev in raw_events:
        m = re.search(r"Pickleball Court (\d+)\s*\(([^)]+) Park\)", ev.get("title", ""))
        if m:
            c_num = int(m.group(1))
            park_name = m.group(2).strip()
            matched_id = None
            for c in COURTS:
                if c["num"] == c_num and c["park"].lower() == park_name.lower():
                    matched_id = c["id"]
                    break
            if matched_id in court_events:
                court_events[matched_id].append(ev)

    is_today = (target_dt.date() == now_real.date())

    courts_data = []
    for court in COURTS:
        courts_data.append({
            "id": court["id"],
            "park": court["park"],
            "name": court["name"],
            "courtNum": court["num"],
            "reserve_url": court["reserve_url"],
            "calendar_url": court["calendar_url"],
            "events": court_events[court["id"]],
        })


    return {
        "view": "day",
        "dateStr": target_dt.strftime("%Y-%m-%d"),
        "dateFormatted": target_dt.strftime("%A, %B %d, %Y"),
        "isToday": is_today,
        "nowTime": now_real.strftime("%I:%M %p"),
        "nowHour": (now_real.hour + now_real.minute / 60) if is_today else None,
        "courts": courts_data,
    }


def get_month_data(year: int, month: int) -> dict:
    """Fetch entire month's events across all 6 courts for the Month View."""
    now_real = datetime.now(EDT)
    # Start of month
    m_start = datetime(year, month, 1, 0, 0, 0, tzinfo=EDT)
    # End of month
    if month == 12:
        m_end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=EDT)
    else:
        m_end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=EDT)

    start_ts = int(m_start.timestamp())
    end_ts = int(m_end.timestamp())

    csrf_key, csrf_token = get_session_and_csrf()
    raw_events = fetch_events_for_range(start_ts, end_ts, csrf_key, csrf_token)
    if raw_events is None:
        csrf_key, csrf_token = get_session_and_csrf()
        raw_events = fetch_events_for_range(start_ts, end_ts, csrf_key, csrf_token) or []

    # Bucket events by date (YYYY-MM-DD) and court
    day_map = {}
    for ev in raw_events:
        date_key = ev["start"].split(" ")[0]
        if date_key not in day_map:
            day_map[date_key] = {c["id"]: [] for c in COURTS}

        m = re.search(r"Pickleball Court (\d+)\s*\(([^)]+) Park\)", ev.get("title", ""))
        if m:
            c_num = int(m.group(1))
            park_name = m.group(2).strip()
            matched_id = None
            for c in COURTS:
                if c["num"] == c_num and c["park"].lower() == park_name.lower():
                    matched_id = c["id"]
                    break
            if matched_id and matched_id in day_map[date_key]:
                day_map[date_key][matched_id].append(ev)


    return {
        "view": "month",
        "year": year,
        "month": month,
        "monthName": m_start.strftime("%B %Y"),
        "todayStr": now_real.strftime("%Y-%m-%d"),
        "days": day_map,
    }


