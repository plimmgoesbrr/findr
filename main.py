"""
main.py
The brain. Runs the full pipeline on a schedule:

  preferences → fetcher → dedup → matcher → notifier → mark seen → sleep

Run with:
    python3 main.py

Stops on Ctrl+C.
"""

import time
import traceback
from datetime import datetime

from preferences import load_preferences, collect_preferences
from database    import init_db, make_job_id, is_seen, mark_seen
from fetcher     import fetch_all
from matcher     import match_jobs
from notifier    import notify

# How often the pipeline runs, in hours
RUN_EVERY_HOURS = 4


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
            job["_id"] = job_id   # carry it forward to mark_seen later
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

    # 5. Mark ALL new jobs as seen (matched or not) so we don't re-score them
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

    print(f"\n[main] Loaded prefs for phone: {preferences.get('phone')}")
    print(f"[main] Bot will run every {RUN_EVERY_HOURS} hour(s). Ctrl+C to stop.\n")

    # Infinite loop — run, sleep, run, sleep
    while True:
        try:
            run_once(preferences)
        except Exception:
            # Catch any error in a single run so the bot doesn't die overnight
            print("\n[main] Something went wrong this run:")
            traceback.print_exc()
            print("[main] Continuing to next cycle anyway.\n")

        sleep_seconds = RUN_EVERY_HOURS * 60 * 60
        next_run = datetime.now().timestamp() + sleep_seconds
        next_run_str = datetime.fromtimestamp(next_run).strftime("%H:%M:%S")
        print(f"\n[main] Sleeping {RUN_EVERY_HOURS}h. Next run at {next_run_str}.\n")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[main] Stopped by user. Bye 👋")
