"""
FastAPI API to fetch AoPS substitute requests
- Bar chart: sub requests by day + time slot
- Pie chart: sub requests by math class (from SUBJECT LINE)
- Gmail IMAP
- 24 hour caching
"""

import imaplib
import email
import os
import re
from collections import Counter
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

# -----------------------------
# APP SETUP
# -----------------------------
app = FastAPI(title="AoPS Sub Requests API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# CACHE
# -----------------------------
_cached_time_slots = None
_cached_class_counts = None
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

    for e_id in email_ids:
        _, msg_data = mail.fetch(e_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = msg["subject"] or ""

        # -----------------------------
        # BODY
        # -----------------------------
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

        # Must be a real sub request
        if "A substitute has been requested for" not in body:
            continue

        # -----------------------------
        # TIME SLOT (BAR CHART)
        # -----------------------------
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

        # -----------------------------
        # CLASS (PIE CHART)
        # -----------------------------
        class_name = extract_class_from_subject(subject)
        if class_name:
            class_names.append(class_name)

    mail.logout()
    return time_slots, class_names

# -----------------------------
# CACHE HANDLER
# -----------------------------
def refresh_cache():
    global _cached_time_slots, _cached_class_counts, _cached_time

    slots, classes = fetch_last_200_sub_requests()

    _cached_time_slots = dict(Counter(slots))
    _cached_class_counts = dict(Counter(classes))
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
    """
    Bar chart:
    Sub requests grouped by day + time slot
    Cached for 24 hours
    """
    ensure_cache()
    return JSONResponse(content=_cached_time_slots)

@app.get("/api/class_breakdown")
def get_class_breakdown():
    """
    Pie chart:
    Sub requests grouped by math class
    (parsed from SUBJECT LINE)
    Cached for 24 hours
    """
    ensure_cache()
    return JSONResponse(content=_cached_class_counts)

# -----------------------------
# RUN:
# python -m uvicorn main:app --reload
# -----------------------------
