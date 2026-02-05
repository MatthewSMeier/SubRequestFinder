"""
FastAPI API to fetch AoPS substitute requests

Charts:
- Bar chart: sub requests by day + time slot
- Pie chart: sub requests by math class
- NEW: Bar chart by day only

Features:
- Gmail IMAP
- 24 hour caching
- Consistent ordering
"""

import imaplib
import email
import os
import re
from collections import Counter, OrderedDict
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# -----------------------------
# CONFIG
# -----------------------------
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
USERNAME = os.getenv("USERNAMEA")
PASSWORD = os.getenv("PASSWORDA")

CACHE_INTERVAL = timedelta(hours=24)

VALID_CLASSES = [
    "Math Level 1",
    "Math Level 2",
    "Math Level 3",
    "Math Level 4",
    "Math Level 5",
    "Prealgebra",
    "Algebra 1",
    "Algebra 2",
    "Geometry",
    "Precalculus",
    "Calculus",
]

WEEKDAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# -----------------------------
# APP SETUP
# -----------------------------
app = FastAPI(title="AoPS Sub Requests API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# CACHE
# -----------------------------
_cached_time_slots = None
_cached_class_counts = None
_cached_days = None
_cached_time = None


# -----------------------------
# HELPERS
# -----------------------------
def extract_class_from_subject(subject: str):
    if not subject:
        return None

    subject = subject.lower()

    for cls in VALID_CLASSES:
        if cls.lower() in subject:
            return cls

    return None


# -----------------------------
# FETCH + PARSE EMAILS
# -----------------------------
def fetch_last_200_sub_requests():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(USERNAME, PASSWORD)
    mail.select("inbox")

    status, data = mail.search(
        None, '(FROM "sandiego-cv@aopsacademy.org")'
    )
    email_ids = data[0].split()[-200:]

    time_slots = []
    class_names = []
    days_only = []

    for e_id in email_ids:
        _, msg_data = mail.fetch(e_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = msg["subject"] or ""

        # BODY
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body += part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="ignore",
                    )
        else:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8",
                errors="ignore",
            )

        # Must be real sub request
        if "A substitute has been requested for" not in body:
            continue

        # TIME SLOT
        match = re.search(
            r"begins (\w+) .*? at (\d{1,2}:\d{2})\s*(am|pm)? "
            r"and ends at (\d{1,2}:\d{2})\s*(am|pm)?",
            body,
            re.IGNORECASE,
        )

        if match:
            day = match.group(1)
            start_time = match.group(2)
            end_time = match.group(4)

            time_slots.append(f"{day} {start_time} - {end_time}")
            days_only.append(day)

        # CLASS
        class_name = extract_class_from_subject(subject)
        if class_name:
            class_names.append(class_name)

    mail.logout()
    return time_slots, class_names, days_only


# -----------------------------
# CACHE HANDLER
# -----------------------------
def refresh_cache():
    global _cached_time_slots, _cached_class_counts, _cached_days, _cached_time

    slots, classes, days = fetch_last_200_sub_requests()

    # Time slots
    _cached_time_slots = dict(Counter(slots))

    # Class counts (ordered)
    counts = Counter(classes)
    ordered_counts = OrderedDict()
    for cls in VALID_CLASSES:
        ordered_counts[cls] = counts.get(cls, 0)
    _cached_class_counts = dict(ordered_counts)

    # Days only (ordered weekdays)
    day_counts = Counter(days)
    ordered_days = OrderedDict()
    for day in WEEKDAY_ORDER:
        ordered_days[day] = day_counts.get(day, 0)

    _cached_days = dict(ordered_days)

    _cached_time = datetime.now()


def ensure_cache():
    global _cached_time

    now = datetime.now()
    if _cached_time is None or now - _cached_time > CACHE_INTERVAL:
        refresh_cache()


# -----------------------------
# API ENDPOINTS
# -----------------------------
@app.get("/api/sub_requests")
def get_sub_requests():
    ensure_cache()
    return JSONResponse(content=_cached_time_slots)


@app.get("/api/class_breakdown")
def get_class_breakdown():
    ensure_cache()
    return JSONResponse(content=_cached_class_counts)


@app.get("/api/sub_requests_by_day")
def get_sub_requests_by_day():
    ensure_cache()
    return JSONResponse(content=_cached_days)


# -----------------------------
# RUN:
# python -m uvicorn main:app --reload
# -----------------------------
