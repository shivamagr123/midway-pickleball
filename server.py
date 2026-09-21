#!/usr/bin/env python3
"""
Midway Park Pickleball Court Checker
Features:
 - Next/Previous day navigation (arrows)
 - Date picker / Jump to today
 - Day View (detailed hourly timeline & bookings for all 6 courts)
 - Month View (interactive monthly calendar showing court availability for all 6 courts)
"""

import http.server
import json
import subprocess
import re
import os
import tempfile
import urllib.parse
import base64
from datetime import datetime, timezone, timedelta

PORT = int(os.environ.get("PORT", 8787))

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


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>🏓 Midway Pickleball Schedule</title>
<style>
  :root {
    --green: #22c55e;
    --green-bg: #dcfce7;
    --red: #ef4444;
    --red-bg: #fee2e2;
    --yellow: #f59e0b;
    --yellow-bg: #fef3c7;
    --dark: #0f172a;
    --card: #1e293b;
    --text: #f8fafc;
    --muted: #94a3b8;
    --accent: #38bdf8;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #090d16 0%, #111827 50%, #090d16 100%);
    color: var(--text);
    min-height: 100vh;
    padding: 12px;
    padding-bottom: 50px;
  }

  /* Header & Navigation */
  .header {
    text-align: center;
    margin-bottom: 14px;
  }
  .title-row {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }
  .header h1 {
    font-size: 20px;
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.5px;
  }

  /* Segmented Toggle (Day vs Month) */
  .view-toggle {
    display: inline-flex;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 3px;
    margin: 6px auto 14px;
    border: 1px solid rgba(255,255,255,0.1);
  }
  .toggle-btn {
    padding: 6px 18px;
    border-radius: 9px;
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    background: transparent;
    border: none;
    cursor: pointer;
    transition: all 0.2s;
  }
  .toggle-btn.active {
    background: var(--accent);
    color: #041324;
    box-shadow: 0 2px 10px rgba(56, 189, 248, 0.4);
  }

  /* Date Navigator Bar */
  .nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(30, 41, 59, 0.7);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 8px 12px;
    margin: 0 auto 16px;
    max-width: 600px;
  }
  .nav-arrow {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255,255,255,0.12);
    color: var(--text);
    font-size: 18px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }
  .nav-arrow:active { transform: scale(0.92); background: rgba(56, 189, 248, 0.3); }
  .nav-center {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
  .nav-date-text {
    font-size: 15px;
    font-weight: 700;
    color: #fff;
  }
  .today-pill {
    font-size: 11px;
    font-weight: 700;
    background: rgba(56, 189, 248, 0.2);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 20px;
    border: 1px solid rgba(56, 189, 248, 0.4);
    cursor: pointer;
  }

  /* Summary Pills */
  .summary-bar {
    display: flex;
    justify-content: center;
    gap: 10px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .summary-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    background: rgba(255,255,255,0.05);
    padding: 4px 10px;
    border-radius: 20px;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot-open { background: var(--green); }
  .dot-partial { background: var(--yellow); }
  .dot-full { background: var(--red); }

  /* Day View Cards */
  .courts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 14px;
    max-width: 1100px;
    margin: 0 auto;
  }
  .court-card {
    background: #ffffff;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }
  .court-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    color: white;
    font-weight: 700;
    font-size: 15px;
  }
  .court-header.open { background: var(--green); }
  .court-header.partial { background: var(--yellow); color: #78350f; }
  .court-header.full { background: var(--red); }
  a[target="_blank"]:active { opacity: 0.7; transform: scale(0.95); }
  .court-status-badge {
    font-size: 11px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 20px;
    background: rgba(255,255,255,0.3);
    text-transform: uppercase;
  }
  .court-body { padding: 12px 14px 14px; color: #1e293b; }

  /* Timeline */
  .timeline {
    position: relative;
    height: 32px;
    background: #e2e8f0;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 6px;
  }
  .timeline-booked {
    position: absolute;
    top: 0;
    height: 100%;
    background: var(--red);
    opacity: 0.8;
  }
  .timeline-now {
    position: absolute;
    top: 0;
    height: 100%;
    width: 2px;
    background: #2563eb;
    z-index: 10;
  }
  .timeline-now::after {
    content: '▼';
    position: absolute;
    top: -12px;
    left: -5px;
    font-size: 9px;
    color: #2563eb;
  }
  .timeline-labels {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #64748b;
    padding: 0 2px;
    margin-bottom: 8px;
  }
  .booking-list { list-style: none; }
  .booking-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid #f1f5f9;
    font-size: 12px;
  }
  .booking-item:last-child { border-bottom: none; }
  .booking-time { font-weight: 700; color: var(--red); min-width: 115px; font-size: 11px; }
  .booking-title {
    color: #475569;
    font-size: 11px;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .no-bookings {
    color: var(--green);
    font-weight: 700;
    font-size: 13px;
    text-align: center;
    padding: 10px 0;
  }

  /* Month Calendar View */
  .month-container {
    max-width: 1000px;
    margin: 0 auto;
    background: rgba(30, 41, 59, 0.7);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 18px;
    padding: 12px;
  }
  .cal-weekdays {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    text-align: center;
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
  }
  .cal-days-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
    margin-top: 6px;
  }
  .cal-cell {
    min-height: 80px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 6px 4px;
    display: flex;
    flex-direction: column;
    cursor: pointer;
    transition: all 0.15s;
  }
  .cal-cell:hover {
    background: rgba(56, 189, 248, 0.1);
    border-color: rgba(56, 189, 248, 0.3);
  }
  .cal-cell.is-today {
    border: 1px solid var(--accent);
    background: rgba(56, 189, 248, 0.08);
  }
  .cal-cell.empty {
    background: transparent;
    border: none;
    cursor: default;
  }
  .cal-date-num {
    font-size: 12px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 4px;
  }
  .court-dots-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2px;
    margin-top: auto;
  }
  .c-dot-badge {
    font-size: 9px;
    font-weight: 700;
    padding: 2px 0;
    text-align: center;
    border-radius: 4px;
    color: #fff;
  }
  .c-dot-badge.open { background: var(--green); }
  .c-dot-badge.booked { background: var(--red); }

  /* Loading indicator */
  .spinner-box {
    text-align: center;
    padding: 50px 20px;
  }
  .spinner {
    width: 36px; height: 36px;
    border: 3px solid rgba(255,255,255,0.1);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 12px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .quick-today-btn {
    background: var(--accent);
    color: #031326;
    font-weight: 700;
    border: none;
    border-radius: 10px;
    padding: 6px 14px;
    font-size: 12px;
    cursor: pointer;
  }
</style>
</head>
<body>

<div class="header">
  <div class="title-row">
    <h1>🏓 Midway Park Pickleball</h1>
  </div>
  <div style="font-size: 12px; color: var(--muted)">Courts 1 through 6</div>


  <div class="view-toggle">
    <button class="toggle-btn active" id="btnDayView" onclick="switchView('day')">📅 Day View</button>
    <button class="toggle-btn" id="btnMonthView" onclick="switchView('month')">🗓️ Month View</button>
  </div>
  <div class="view-toggle" style="margin-top: -6px; margin-bottom: 14px;">
    <button class="toggle-btn active" id="btnMidway" onclick="switchPark('Midway')">🌳 Midway Park</button>
    <button class="toggle-btn" id="btnFowler" onclick="switchPark('Fowler')">🌲 Fowler Park</button>
  </div>

</div>

<div class="nav-bar">
  <button class="nav-arrow" onclick="navigateStep(-1)">◀</button>
  <div class="nav-center">
    <div class="nav-date-text" id="navLabel">Loading...</div>
    <div id="todayIndicator"></div>
  </div>
  <button class="nav-arrow" onclick="navigateStep(1)">▶</button>
</div>

<div id="contentArea">
  <div class="spinner-box">
    <div class="spinner"></div>
    <div style="color: var(--muted); font-size: 13px;">Loading schedules...</div>
  </div>
</div>

<script>
const DAY_START = 6, DAY_END = 22;

let currentView = 'day'; // 'day' | 'month'
let selectedPark = 'Midway'; // 'Midway' | 'Fowler'
let selectedDate = new Date(); // Current date object in EDT
let cachedDayData = null;
let cachedMonthData = null;

function switchPark(park) {
  selectedPark = park;
  document.getElementById('btnMidway').classList.toggle('active', park === 'Midway');
  document.getElementById('btnFowler').classList.toggle('active', park === 'Fowler');
  
  if (currentView === 'day' && cachedDayData) {
    renderDayView(cachedDayData);
  } else if (currentView === 'month' && cachedMonthData) {
    renderMonthView(cachedMonthData);
  } else {
    loadData();
  }
}


function pad(n) { return String(n).padStart(2, '0'); }

function dateToYMD(d) {
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}

function fmtTime(iso) {
  const d = new Date(iso.replace(' ', 'T'));
  let h = d.getHours(), m = d.getMinutes(), ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return h + (m > 0 ? ':' + pad(m) : '') + ap;
}

function cleanTitle(raw) {
  let t = raw.replace(/\\n/g, ' ').replace(/\n/g, ' ').trim();
  t = t.replace(/Pickleball Court \d+ \([^)]+ Park\)\s*/g, '');
  t = t.replace(/\d{1,2}:\d{2}\s*(AM|PM)\s*-\s*\d{1,2}:\d{2}\s*(AM|PM)/gi, '');
  t = t.replace(/Rental\s*/g, '').trim();
  return t || 'Reserved';
}

function switchView(view) {
  currentView = view;
  document.getElementById('btnDayView').classList.toggle('active', view === 'day');
  document.getElementById('btnMonthView').classList.toggle('active', view === 'month');
  loadData();
}

function navigateStep(direction) {
  if (currentView === 'day') {
    selectedDate.setDate(selectedDate.getDate() + direction);
  } else {
    selectedDate.setMonth(selectedDate.getMonth() + direction);
  }
  loadData();
}

function jumpToToday() {
  selectedDate = new Date();
  loadData();
}

function loadData() {
  const content = document.getElementById('contentArea');
  content.innerHTML = `
    <div class="spinner-box">
      <div class="spinner"></div>
      <div style="color: var(--muted); font-size: 13px;">Fetching court bookings...</div>
    </div>
  `;

  if (currentView === 'day') {
    const ymd = dateToYMD(selectedDate);
    fetch(`/api/courts?date=${ymd}&t=${Date.now()}`)
      .then(r => r.json())
      .then(d => { cachedDayData = d; renderDayView(d); })
      .catch(showError);
  } else {
    const y = selectedDate.getFullYear();
    const m = selectedDate.getMonth() + 1;
    fetch(`/api/month?year=${y}&month=${m}&t=${Date.now()}`)
      .then(r => r.json())
      .then(d => { cachedMonthData = d; renderMonthView(d); })
      .catch(showError);
  }
}

function renderDayView(data) {
  document.getElementById('navLabel').textContent = data.dateFormatted;
  const todayInd = document.getElementById('todayIndicator');
  if (data.isToday) {
    todayInd.innerHTML = `<span class="today-pill">TODAY</span>`;
  } else {
    todayInd.innerHTML = `<button class="quick-today-btn" onclick="jumpToToday()" style="padding:1px 8px;font-size:10px;margin-top:2px;">Back to Today</button>`;
  }

  const parkCourts = data.courts.filter(c => c.park === selectedPark);

  let openC = 0, partC = 0, fullC = 0;
  parkCourts.forEach(c => {
    if (!c.events.length) { openC++; return; }
    const mins = c.events.reduce((s,e) => {
      const ds = new Date(e.start.replace(' ','T')), de = new Date(e.end.replace(' ','T'));
      return s + (de - ds)/60000;
    }, 0);
    if (mins >= (DAY_END - DAY_START)*60*0.9) fullC++; else partC++;
  });

  let h = `
    <div class="summary-bar">
      <div class="summary-item"><span class="dot dot-open"></span> ${openC} Open All Day</div>
      <div class="summary-item"><span class="dot dot-partial"></span> ${partC} Partially Booked</div>
      <div class="summary-item"><span class="dot dot-full"></span> ${fullC} Fully Booked</div>
    </div>
  `;

  if (data.isToday && data.nowTime) {
    h += `<div style="text-align:center;font-size:12px;color:var(--accent);margin-bottom:12px;font-weight:600;">🕐 Current Time: ${data.nowTime}</div>`;
  }

  h += `<div class="courts-grid">`;
  parkCourts.forEach(court => {
    const has = court.events.length > 0;
    let st = 'open', sl = '✅ OPEN ALL DAY';
    if (has) {
      const mins = court.events.reduce((s,e) => {
        const ds = new Date(e.start.replace(' ','T')), de = new Date(e.end.replace(' ','T'));
        return s + (de - ds)/60000;
      }, 0);
      if (mins >= (DAY_END - DAY_START)*60*0.9) { st = 'full'; sl = '🚫 FULLY BOOKED'; }
      else { st = 'partial'; sl = '⚠️ HAS BOOKINGS'; }
    }

    h += `
      <div class="court-card">
        <div class="court-header ${st}">
          <span>${court.name}</span>
          <div style="display:flex; align-items:center; gap:8px;">
            <a href="${court.reserve_url}" target="_blank" style="font-size:11px; background:rgba(0,0,0,0.3); color:white; padding:3px 8px; border-radius:8px; text-decoration:none; font-weight:700;">RESERVE</a>
            <a href="${court.calendar_url}" target="_blank" class="court-status-badge" style="text-decoration:none; display:inline-block; color:inherit;">${sl}</a>
          </div>
        </div>
        <div class="court-body">
          <div class="timeline">
    `;

    const dayM = (DAY_END - DAY_START) * 60;
    court.events.forEach(ev => {
      const s = new Date(ev.start.replace(' ','T')), e = new Date(ev.end.replace(' ','T'));
      const sm = Math.max(0, s.getHours()*60 + s.getMinutes() - DAY_START*60);
      const em = Math.min(dayM, e.getHours()*60 + e.getMinutes() - DAY_START*60);
      h += `<div class="timeline-booked" style="left:${sm/dayM*100}%;width:${(em-sm)/dayM*100}%"></div>`;
    });

    if (data.isToday && data.nowHour >= DAY_START && data.nowHour <= DAY_END) {
      h += `<div class="timeline-now" style="left:${(data.nowHour-DAY_START)/(DAY_END-DAY_START)*100}%"></div>`;
    }

    h += `</div>
          <div class="timeline-labels"><span>6AM</span><span>9AM</span><span>12PM</span><span>3PM</span><span>6PM</span><span>9PM</span></div>
    `;

    if (!has) {
      h += `<div class="no-bookings">✅ No reservations — completely free!</div>`;
    } else {
      h += `<ul class="booking-list">`;
      const sorted = [...court.events].sort((a,b) => a.start.localeCompare(b.start));
      sorted.forEach(ev => {
        h += `
          <li class="booking-item">
            <span class="booking-time">🔴 ${fmtTime(ev.start)} – ${fmtTime(ev.end)}</span>
            <span class="booking-title">${cleanTitle(ev.title || 'Reserved')}</span>
          </li>
        `;
      });
      h += `</ul>`;
    }

    h += `</div></div>`;
  });
  h += `</div>`;

  document.getElementById('contentArea').innerHTML = h;
}
function renderMonthView(data) {
  document.getElementById('navLabel').textContent = data.monthName;
  const isCurrentMonth = (new Date().getFullYear() === data.year && (new Date().getMonth() + 1) === data.month);
  const todayInd = document.getElementById('todayIndicator');
  if (isCurrentMonth) {
    todayInd.innerHTML = `<span class="today-pill">CURRENT MONTH</span>`;
  } else {
    todayInd.innerHTML = `<button class="quick-today-btn" onclick="jumpToToday()" style="padding:1px 8px;font-size:10px;margin-top:2px;">Back to This Month</button>`;
  }

  const firstDay = new Date(data.year, data.month - 1, 1).getDay(); // 0 = Sun
  const totalDays = new Date(data.year, data.month, 0).getDate();
  
  const parkIds = selectedPark === 'Midway' 
    ? [190670,190671,190672,190673,190674,190675] 
    : [190662,190663,190664,190665,190666,190667,190668,190669];

  let h = `
    <div class="month-container">
      <div style="font-size:12px;color:var(--muted);text-align:center;margin-bottom:10px;">
        Tap any day to see full court hours and reservations. Shows Courts 1–${parkIds.length} (🟢 Open / 🔴 Booked).
      </div>
      <div class="cal-weekdays">
        <div>SUN</div><div>MON</div><div>TUE</div><div>WED</div><div>THU</div><div>FRI</div><div>SAT</div>
      </div>
      <div class="cal-days-grid">
  `;

  // Empty leading days
  for (let i = 0; i < firstDay; i++) {
    h += `<div class="cal-cell empty"></div>`;
  }

  for (let d = 1; d <= totalDays; d++) {
    const ymd = `${data.year}-${pad(data.month)}-${pad(d)}`;
    const isToday = (ymd === data.todayStr);
    const dayData = (data.days && data.days[ymd]) || {};

    h += `
      <div class="cal-cell ${isToday ? 'is-today' : ''}" onclick="selectDateFromMonth('${ymd}')">
        <div class="cal-date-num">${d}</div>
        <div class="court-dots-row">
    `;

    for (let c = 0; c < parkIds.length; c++) {
      const cEvts = dayData[parkIds[c]] || [];
      const hasBooking = cEvts.length > 0;
      const statusClass = hasBooking ? 'booked' : 'open';
      h += `<div class="c-dot-badge ${statusClass}">C${c+1}</div>`;
    }

    h += `
        </div>
      </div>
    `;
  }

  h += `</div></div>`;
  document.getElementById('contentArea').innerHTML = h;
}
function selectDateFromMonth(ymd) {
  const parts = ymd.split('-');
  selectedDate = new Date(parts[0], parts[1] - 1, parts[2]);
  switchView('day');
}

function showError(err) {
  document.getElementById('contentArea').innerHTML = `
    <div style="text-align:center;padding:40px;color:#ef4444;">
      <p>Error loading schedule: ${err.message}</p>
      <button class="quick-today-btn" onclick="loadData()" style="margin-top:10px;">Try Again</button>
    </div>
  `;
}

// Initial load
loadData();
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/api/courts":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()

            date_str = params.get("date", [None])[0]
            data = get_courts_for_date(date_str)
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif path == "/api/month":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()

            now = datetime.now(EDT)
            year = int(params.get("year", [now.year])[0])
            month = int(params.get("month", [now.month])[0])
            data = get_month_data(year, month)
            self.wfile.write(json.dumps(data).encode("utf-8"))

        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
