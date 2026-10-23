"""
notifier.py
Sends matched internships to your WhatsApp via Twilio's Sandbox.

Splits matches into two messages:
  1. Within India — Hyderabad & Bangalore prioritized
  2. Abroad      — USA prioritized

Each message capped at 5 listings to stay under WhatsApp's 1600 char limit.
"""

import os
import re
import time
import requests
from requests.auth import HTTPBasicAuth


# ──────────────────────────────────────────
# Location classification
# ──────────────────────────────────────────

# India cities, ranked by priority (Hyderabad first, then Bangalore)
INDIA_CITIES_PRIORITY = [
    ("hyderabad",         ["hyderabad", "hyd"]),
    ("bangalore",         ["bangalore", "bengaluru", "blr"]),
    ("mumbai",            ["mumbai", "bombay"]),
    ("pune",              ["pune"]),
    ("delhi",             ["delhi", "new delhi", "ncr", "gurgaon", "gurugram", "noida"]),
    ("chennai",           ["chennai", "madras"]),
    ("kolkata",           ["kolkata", "calcutta"]),
    ("ahmedabad",         ["ahmedabad"]),
    ("india-other",       ["india"]),
]

# Abroad regions, ranked by priority (USA first)
ABROAD_REGIONS_PRIORITY = [
    ("usa",       ["usa", "united states", "u.s.", "us,", "remote in usa",
                   "remote, us", "remote, usa",
                   # All US state abbreviations
                   "al,", "ak,", "az,", "ar,", "ca,", "co,", "ct,", "de,",
                   "fl,", "ga,", "hi,", "id,", "il,", "in,", "ia,", "ks,",
                   "ky,", "la,", "me,", "md,", "ma,", "mi,", "mn,", "ms,",
                   "mo,", "mt,", "ne,", "nv,", "nh,", "nj,", "nm,", "ny,",
                   "nc,", "nd,", "oh,", "ok,", "or,", "pa,", "ri,", "sc,",
                   "sd,", "tn,", "tx,", "ut,", "vt,", "va,", "wa,", "wv,",
                   "wi,", "wy,",
                   # Full state names (caught even without comma)
                   "alabama", "alaska", "arizona", "arkansas", "california",
                   "colorado", "connecticut", "delaware", "florida", "georgia",
                   "hawaii", "idaho", "illinois", "iowa", "kansas",
                   "kentucky", "louisiana", "maine", "maryland", "massachusetts",
                   "michigan", "minnesota", "mississippi", "missouri", "montana",
                   "nebraska", "nevada", "new hampshire", "new jersey",
                   "new mexico", "new york", "north carolina", "north dakota",
                   "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
                   "south carolina", "south dakota", "tennessee", "texas",
                   "utah", "vermont", "virginia", "washington", "west virginia",
                   "wisconsin", "wyoming",
                   # Common US cities
                   "san francisco", "san jose", "new york city", "nyc",
                   "los angeles", "chicago", "seattle", "boston", "austin",
                   "atlanta", "denver", "miami", "philadelphia", "phoenix",
                   "dallas", "houston", "minneapolis", "detroit", "portland"]),
    ("uk",        ["uk", "united kingdom", "london", "manchester", "england"]),
    ("canada",    ["canada", "toronto", "vancouver", "montreal"]),
    ("australia", ["australia", "sydney", "melbourne"]),
    ("singapore", ["singapore"]),
    ("europe",    ["germany", "berlin", "france", "paris", "netherlands",
                   "amsterdam", "ireland", "dublin"]),
    ("abroad-other", []),
]


def _contains_word(text, keyword):
    """
    True if `keyword` appears in `text` as a whole word/phrase.
    Stops 'india' from matching 'indianapolis', 'in,' from matching 'singapore', etc.
    """
    # Build a regex that matches the keyword surrounded by non-letter chars
    # (word boundaries don't work great with phrases containing spaces/commas)
    pattern = r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])"
    return re.search(pattern, text) is not None


def classify_location(location_str):
    """
    Returns a (side, priority) tuple.
    side: 'india' or 'abroad'
    priority: lower number = higher priority within that side
    """
    if not location_str:
        return ("india", 99)  # ambiguous → default to India side, low priority

    loc = location_str.lower()

    # Check India cities first (in priority order)
    for i, (_, keywords) in enumerate(INDIA_CITIES_PRIORITY):
        if any(_contains_word(loc, k) for k in keywords):
            return ("india", i)

    # Check abroad regions
    for i, (_, keywords) in enumerate(ABROAD_REGIONS_PRIORITY):
        if any(_contains_word(loc, k) for k in keywords):
            return ("abroad", i)

    # "Remote" with no country → India side (most accessible to user)
    if "remote" in loc:
        return ("india", 99)

    # Fallback: abroad-other
    return ("abroad", len(ABROAD_REGIONS_PRIORITY) - 1)


# ──────────────────────────────────────────
# Env loader (env vars first, .env file fallback)
# ──────────────────────────────────────────

def load_env():
    """
    Reads credentials from environment variables first (GitHub Actions),
    falls back to .env file (local Mac).
    """
    env = {}
    needed = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"]

    # Try environment first
    for key in needed:
        if os.environ.get(key):
            env[key] = os.environ[key].strip()

    # If all needed values came from env, we're done
    if all(k in env for k in needed):
        return env

    # Otherwise, try local .env file for whatever's missing
    env_path = ".env"
    if not os.path.exists(env_path):
        if not env:
            raise RuntimeError("No Twilio credentials in environment or .env file.")
        return env  # partial, but better than nothing

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in env:  # don't overwrite env-var values
                env[key] = value.strip().strip('"').strip("'")
    return env


# ──────────────────────────────────────────
# Message formatting
# ──────────────────────────────────────────

def format_message(title, jobs):
    """Builds one WhatsApp message body for a group of jobs."""
    if not jobs:
        return None

    header = f"🔔 {title} ({len(jobs)} match{'es' if len(jobs) != 1 else ''}):"
    parts = [header]

    for i, job in enumerate(jobs, 1):
        chunk  = f"\n\n{i}. {job.get('title', 'Untitled')}"
        chunk += f"\n   {job.get('company', '?')} — {job.get('location', '?')}"
        score = job.get("score")
        if score:
            chunk += f"  ({score}/10)"
        url = job.get("url", "")
        if url:
            chunk += f"\n   {url}"
        parts.append(chunk)

    msg = "".join(parts)
    # Hard truncate if somehow over 1600
    if len(msg) > 1550:
        msg = msg[:1500] + "\n\n…"
    return msg


# ──────────────────────────────────────────
# Twilio send
# ──────────────────────────────────────────

def send_whatsapp(message, phone_number, env):
    sid    = env.get("TWILIO_ACCOUNT_SID")
    token  = env.get("TWILIO_AUTH_TOKEN")
    sender = env.get("TWILIO_WHATSAPP_FROM", "+14155238886")

    if not sid or not token:
        print("  [notifier] Missing Twilio credentials in .env")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = {
        "From": f"whatsapp:{sender}",
        "To":   f"whatsapp:{phone_number}",
        "Body": message,
    }

    try:
        resp = requests.post(url, data=data, auth=HTTPBasicAuth(sid, token), timeout=15)
        if resp.status_code in (200, 201):
            print(f"  [notifier] WhatsApp sent ({len(message)} chars)")
            return True
        else:
            print(f"  [notifier] Twilio error {resp.status_code}: {resp.text[:200]}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  [notifier] Network error: {e}")
        return False


# ──────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────

def notify(matches, preferences):
    """
    Splits matches into India / Abroad buckets and sends 2 WhatsApp messages.
    """
    if not matches:
        print("[notifier] No matches to send. Staying silent.")
        return

    phone = preferences.get("phone")
    if not phone:
        print("[notifier] No phone number in preferences, skipping.")
        return

    try:
        env = load_env()
    except RuntimeError as e:
        print(f"[notifier] {e}")
        return

    # Group matches by side
    india_jobs  = []
    abroad_jobs = []
    for job in matches:
        side, priority = classify_location(job.get("location", ""))
        job["_priority"] = priority
        if side == "india":
            india_jobs.append(job)
        else:
            abroad_jobs.append(job)

    # Sort within each side: priority first (Hyderabad before others),
    # then score (highest first)
    india_jobs.sort(key=lambda j: (j["_priority"], -j.get("score", 0)))
    abroad_jobs.sort(key=lambda j: (j["_priority"], -j.get("score", 0)))

    # Cap each side at top 5
    india_top  = india_jobs[:5]
    abroad_top = abroad_jobs[:5]

    print(f"\n[notifier] India: {len(india_jobs)} matches "
          f"(sending top {len(india_top)})")
    print(f"[notifier] Abroad: {len(abroad_jobs)} matches "
          f"(sending top {len(abroad_top)})")

    # Send the India message first
    if india_top:
        msg = format_message("Within India", india_top)
        send_whatsapp(msg, phone, env)
        time.sleep(2)  # brief pause between messages

    # Then abroad
    if abroad_top:
        msg = format_message("Abroad", abroad_top)
        send_whatsapp(msg, phone, env)


if __name__ == "__main__":
    from preferences import load_preferences

    prefs = load_preferences()
    if not prefs:
        print("Run preferences.py first.")
        exit()

    # Mix of India + abroad fake matches to test the split
    fake_matches = [
        {"title": "Backend Intern",         "company": "Razorpay",   "location": "Bangalore",       "url": "https://razorpay.com/jobs",     "score": 9,  "source": "test"},
        {"title": "ML Intern",              "company": "Google",     "location": "San Jose, CA",    "url": "https://careers.google.com",    "score": 9,  "source": "test"},
        {"title": "Software Eng Intern",    "company": "Microsoft",  "location": "Hyderabad",       "url": "https://careers.microsoft.com", "score": 10, "source": "test"},
        {"title": "Full Stack Intern",      "company": "Cred",       "location": "Bangalore",       "url": "https://cred.club/jobs",        "score": 8,  "source": "test"},
        {"title": "Data Engineer Intern",   "company": "Stripe",     "location": "Remote in USA",   "url": "https://stripe.com/jobs",       "score": 8,  "source": "test"},
        {"title": "Backend Intern",         "company": "Swiggy",     "location": "Mumbai",          "url": "https://careers.swiggy.com",    "score": 8,  "source": "test"},
        {"title": "Python Intern",          "company": "Deepmind",   "location": "London",          "url": "https://deepmind.com/careers",  "score": 9,  "source": "test"},
        {"title": "Software Intern",        "company": "Shopify",    "location": "Toronto, Canada", "url": "https://shopify.com/careers",   "score": 8,  "source": "test"},
    ]

    print("=" * 50)
    print("INDIA PREVIEW:")
    print("=" * 50)
    india = [j for j in fake_matches if classify_location(j["location"])[0] == "india"]
    india.sort(key=lambda j: (classify_location(j["location"])[1], -j["score"]))
    print(format_message("Within India", india[:5]))

    print("\n" + "=" * 50)
    print("ABROAD PREVIEW:")
    print("=" * 50)
    abroad = [j for j in fake_matches if classify_location(j["location"])[0] == "abroad"]
    abroad.sort(key=lambda j: (classify_location(j["location"])[1], -j["score"]))
    print(format_message("Abroad", abroad[:5]))

    answer = input("\nSend both to WhatsApp now? (y/n): ").strip().lower()
    if answer == "y":
        notify(fake_matches, prefs)
    else:
        print("Skipped.")
