"""
main.py
The brain. Runs the full pipeline once and exits:

  preferences → fetcher → dedup → matcher → notifier → mark seen

Scheduling is handled by GitHub Actions (runs every 4 hours via cron).

Run locally with:
    python3 main.py
"""

import traceback
from datetime import datetime

from preferences import load_preferences, collect_preferences
from database    import init_db, make_job_id, is_seen, mark_seen
from fetcher     import fetch_all
from matcher     import match_jobs
from notifier    import notify


def run_once(preferences):
    """One full pass: fetch → dedup → match → notify → mark seen."""
    print("\n" + "=" * 50)
    print(f"  RUN STARTED at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. Fetch all listings
    all_jobs = fetch_all(preferences)
    if not all_jobs:
        print("[main] No listings fetched. Done.")
        return

    # 2. Filter out ones already seen (dedup)
    new_jobs = []
    for job in all_jobs:
        job_id = make_job_id(job["title"], job["company"], job["location"])
        if not is_seen(job_id):
            job["_id"] = job_id
            new_jobs.append(job)

    print(f"[main] {len(new_jobs)} new listings (after dedup)")
    if not new_jobs:
        print("[main] Nothing new since last run. Done.")
        return

    # 3. AI matching
    matches = match_jobs(new_jobs, preferences)

    # 4. Send to WhatsApp
    if matches:
        notify(matches, preferences)
    else:
        print("[main] No strong matches this round. Staying silent.")

    # 5. Mark ALL new jobs as seen (matched or not)
    for job in new_jobs:
        mark_seen(job["_id"], job["title"], job["company"])

    print(f"\n[main] Run complete. {len(matches)} matches sent.")


def main():
    print("\n" + "=" * 50)
    print("  INTERNSHIP BOT  —  starting up")
    print("=" * 50)

    # Set up the database (creates seen_jobs.db if missing)
    init_db()

    # Load prefs, or trigger onboarding on first run
    preferences = load_preferences()
    if not preferences:
        print("First time running — let's set up your preferences.")
        preferences = collect_preferences()

    # Mask phone in logs — only show country code + last 4 digits
    phone = preferences.get("phone", "")
    masked = f"{phone[:3]}***{phone[-4:]}" if len(phone) > 7 else "***"
    print(f"\n[main] Loaded prefs for phone: {masked}")

    # Single run — GitHub Actions handles the schedule
    try:
        run_once(preferences)
    except Exception:
        print("\n[main] Something went wrong this run:")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[main] Stopped by user. Bye 👋")
