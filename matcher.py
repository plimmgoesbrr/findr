"""
matcher.py
Takes raw listings from fetcher.py and filters them against your saved
preferences using Groq's API (free tier, 30 RPM, 14400/day).

Uses Llama 3.3 70B — genuinely smart, very fast, very free.

For each batch of listings, the model returns:
  - a score (0-10) for how well it matches your prefs
  - a one-line reason

Anything scored MATCH_THRESHOLD or higher gets sent to WhatsApp.
"""

import json
import os
import time
import requests

# --- Settings you can tune ---
MATCH_THRESHOLD = 8        # only listings scored >= this get sent (0-10)
BATCH_SIZE      = 25       # smaller batches = fewer drops per batch
MODEL           = "openai/gpt-oss-120b"  # Groq's main model, free tier
TIMEOUT         = 30
SLEEP_BETWEEN_BATCHES = 2  # seconds — Groq lets us go faster than Gemini
MAX_BATCHES     = 10       # safety cap (40 x 10 = 400 listings max per run)


# --- Quick pre-filter: only send listings that loosely match prefs ---
def pre_filter(jobs, preferences):
    """
    Keyword-based pre-filter. Only sends listings to the AI that have any
    overlap with the user's field/keywords. Saves API tokens hugely.
    """
    # Build set of relevant words from prefs
    relevant_words = set()
    for f in preferences.get("field", []):
        # Split on spaces and slashes
        for word in f.replace("/", " ").split():
            word = word.lower().strip()
            if len(word) > 2:  # ignore short words like "AI", "UX"
                relevant_words.add(word)
    for k in preferences.get("keywords", []):
        relevant_words.add(k.lower().strip())

    # Always include common internship-related root words tied to user fields
    field_synonyms = {
        "software": ["software", "backend", "frontend", "fullstack", "full-stack",
                     "developer", "engineer", "programming", "coding", "web",
                     "python", "java", "react", "node", "django", "api"],
        "data":     ["data", "ml", "ai", "machine learning", "analytics",
                     "analyst", "scientist", "deep learning", "nlp"],
        "design":   ["design", "ui", "ux", "graphic", "product design", "figma"],
        "finance":  ["finance", "investment", "banking", "trading", "equity",
                     "analyst", "accounting", "audit"],
        "marketing":["marketing", "growth", "seo", "content", "social media",
                     "brand", "digital marketing"],
        "product":  ["product", "pm", "associate"],
    }
    for word in list(relevant_words):
        for root, synonyms in field_synonyms.items():
            if root in word:
                relevant_words.update(synonyms)

    if not relevant_words:
        return jobs  # no filter possible, send everything

    # Keep any job whose title or company mentions a relevant word
    filtered = []
    for job in jobs:
        text = f"{job['title']} {job['company']}".lower()
        if any(word in text for word in relevant_words):
            filtered.append(job)

    print(f"  [matcher] Pre-filter: {len(jobs)} → {len(filtered)} relevant listings")
    return filtered


# --- Load API key from .env or environment ---
def load_api_key():
    """
    Reads GROQ_API_KEY from environment first (GitHub Actions),
    then from .env file (local Mac).
    """
    # GitHub Actions sets this via secrets
    env_key = os.environ.get("GROQ_API_KEY")
    if env_key:
        return env_key.strip()

    # Local .env file
    env_path = ".env"
    if not os.path.exists(env_path):
        raise RuntimeError(
            "No GROQ_API_KEY found in environment or .env file."
        )

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "GROQ_API_KEY":
                return value.strip().strip('"').strip("'")

    raise RuntimeError("GROQ_API_KEY not found inside .env file.")


# --- The actual Groq API call ---
def score_batch(jobs_batch, preferences, api_key):
    """
    Sends one batch of jobs to Groq.
    Returns a list of {"score": int, "reason": str} dicts — one per job.
    """
    fields    = ", ".join(preferences.get("field", []))
    keywords  = ", ".join(preferences.get("keywords", [])) or "none"
    work_type = preferences.get("work_type", "Any")
    locations = ", ".join(preferences.get("location_preference", [])) or "any"

    listings_text = ""
    for i, job in enumerate(jobs_batch, 1):
        listings_text += (
            f"{i}. Title: {job['title']} | Company: {job['company']} | "
            f"Location: {job['location']}\n"
        )

    prompt = f"""You are filtering internship listings for a student.

Their preferences:
- Field(s): {fields}
- Work type: {work_type}
- Preferred locations: {locations}
- Keywords: {keywords}

For each listing below, give a score from 0-10 for how well it matches.
Be generous — Django/FastAPI count as Python, ML counts as Data Science, etc.
Score 0-3 = clearly unrelated, 4-6 = somewhat related, 7-10 = strong match.

Return ONLY a JSON array, one object per listing, in this exact format:
[{{"score": 8, "reason": "Backend role, matches Python"}}, ...]

Do not wrap it in markdown or explanation. Return ONLY the array.

Listings:
{listings_text}
"""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # Groq uses OpenAI-compatible response shape
        text = data["choices"][0]["message"]["content"]
        text = text.strip()

        # Sometimes the model wraps the array in an object like {"results":[...]}
        # or returns it directly. Handle both.
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            # Find the first array value inside
            for v in parsed.values():
                if isinstance(v, list):
                    scores = v
                    break
            else:
                scores = []
        elif isinstance(parsed, list):
            scores = parsed
        else:
            scores = []

        # Make sure the count matches
        if len(scores) != len(jobs_batch):
            print(
                f"  [matcher] WARNING: sent {len(jobs_batch)} jobs but "
                f"got {len(scores)} scores back — padding with zeros"
            )
            while len(scores) < len(jobs_batch):
                scores.append({"score": 0, "reason": "no response"})
            scores = scores[:len(jobs_batch)]

        return scores

    except requests.exceptions.Timeout:
        print("  [matcher] Groq timed out, skipping this batch.")
    except requests.exceptions.RequestException as e:
        print(f"  [matcher] Groq error: {e}")
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"  [matcher] Couldn't parse Groq response: {e}")
    except Exception as e:
        print(f"  [matcher] Unexpected error: {e}")

    # On any failure, return zeros so nothing from this batch gets sent
    return [{"score": 0, "reason": "error"} for _ in jobs_batch]


# --- Main entry point ---
def match_jobs(jobs, preferences):
    """
    Takes a list of jobs and returns only the ones that match.
    Each returned job gains two new keys: 'score' and 'reason'.
    """
    if not jobs:
        return []

    print(f"\n[matcher] Got {len(jobs)} raw listings, pre-filtering...")
    jobs = pre_filter(jobs, preferences)

    if not jobs:
        print("[matcher] Nothing left after pre-filter.")
        return []

    print(f"[matcher] Sending {len(jobs)} listings through Groq (Llama 3.3 70B)...")

    try:
        api_key = load_api_key()
    except RuntimeError as e:
        print(f"  [matcher] {e}")
        return []

    matches = []
    consecutive_errors = 0

    # Cap how many jobs we try to score — but balance India and Abroad
    # so we don't starve one side just because of fetch order
    max_jobs = BATCH_SIZE * MAX_BATCHES
    if len(jobs) > max_jobs:
        # Lazy import to avoid circular issues
        from notifier import classify_location

        india_jobs  = [j for j in jobs if classify_location(j.get("location", ""))[0] == "india"]
        abroad_jobs = [j for j in jobs if classify_location(j.get("location", ""))[0] == "abroad"]

        # Reserve half the cap for each side (with fallback if one side is small)
        half = max_jobs // 2
        india_keep  = min(len(india_jobs),  half)
        abroad_keep = min(len(abroad_jobs), max_jobs - india_keep)
        # If India had less than half, give the leftover slots to Abroad
        india_keep  = min(len(india_jobs), max_jobs - abroad_keep)

        jobs = india_jobs[:india_keep] + abroad_jobs[:abroad_keep]
        print(f"  [matcher] Capped at {len(jobs)} jobs "
              f"({india_keep} India + {abroad_keep} Abroad)")

    # Process in batches
    for batch_num, start in enumerate(range(0, len(jobs), BATCH_SIZE), 1):
        batch = jobs[start:start + BATCH_SIZE]
        print(f"  [matcher] Batch {batch_num} — scoring {len(batch)} listings...")
        scores = score_batch(batch, preferences, api_key)

        all_zero = all(s.get("score", 0) == 0 for s in scores)
        if all_zero:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("  [matcher] Multiple errors in a row — stopping to protect quota.")
                break
        else:
            consecutive_errors = 0

        for job, result in zip(batch, scores):
            score = result.get("score", 0)
            if score >= MATCH_THRESHOLD:
                job_copy = dict(job)
                job_copy["score"]  = score
                job_copy["reason"] = result.get("reason", "")
                matches.append(job_copy)

        if start + BATCH_SIZE < len(jobs):
            time.sleep(SLEEP_BETWEEN_BATCHES)

    matches.sort(key=lambda j: j["score"], reverse=True)

    print(f"[matcher] {len(matches)} listings passed the threshold (>= {MATCH_THRESHOLD})\n")
    return matches


if __name__ == "__main__":
    from preferences import load_preferences

    prefs = load_preferences()
    if not prefs:
        print("Run preferences.py first to set up your prefs.")
        exit()

    fake_jobs = [
        {"title": "Software Engineering Intern",  "company": "Razorpay", "location": "Bangalore",  "url": "", "source": "test"},
        {"title": "Django Backend Intern",        "company": "Cred",     "location": "Remote",     "url": "", "source": "test"},
        {"title": "Marketing Intern",             "company": "Zomato",   "location": "Delhi",      "url": "", "source": "test"},
        {"title": "ML Research Intern",           "company": "Google",   "location": "Bangalore",  "url": "", "source": "test"},
        {"title": "Frontend Designer Intern",     "company": "Figma",    "location": "Remote",     "url": "", "source": "test"},
        {"title": "Sales Intern",                 "company": "Byju's",   "location": "Mumbai",     "url": "", "source": "test"},
    ]

    matches = match_jobs(fake_jobs, prefs)

    print("=" * 50)
    print("MATCHES (sorted best first):\n")
    for m in matches:
        print(f"  [{m['score']}/10] {m['title']} @ {m['company']}")
        print(f"         Reason: {m['reason']}")
        print()