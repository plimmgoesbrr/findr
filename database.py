"""
database.py
Tracks every internship the bot has already seen.
Prevents you from being notified about the same listing twice.
Uses SQLite — one file on disk, no setup needed.
"""

import sqlite3
import hashlib

DB_FILE = "seen_jobs.db"


def init_db():
    """Create the database and table if they don't exist yet."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def make_job_id(title, company, location):
    """
    Creates a unique ID for a job by hashing title + company + location.
    Same listing from two different sources won't be shown twice.
    """
    raw = f"{title.lower().strip()}{company.lower().strip()}{location.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def is_seen(job_id):
    """Returns True if this job has already been sent to the user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM seen_jobs WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_seen(job_id, title, company):
    """Mark a job as seen so it won't be sent again."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO seen_jobs (id, title, company) VALUES (?, ?, ?)",
        (job_id, title, company),
    )
    conn.commit()
    conn.close()


def count_seen():
    """Returns how many jobs have been tracked so far. Used for testing."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM seen_jobs")
    count = cursor.fetchone()[0]
    conn.close()
    return count


if __name__ == "__main__":
    # Test the database
    init_db()
    print("✅ Database initialized.")

    # Simulate 3 fake jobs
    fake_jobs = [
        ("Backend Intern", "Stripe", "Remote"),
        ("ML Intern", "Google", "Bangalore"),
        ("Backend Intern", "Stripe", "Remote"),  # duplicate — should be caught
    ]

    print("\nTesting deduplication with 3 jobs (one is a duplicate):\n")
    for title, company, location in fake_jobs:
        job_id = make_job_id(title, company, location)
        if is_seen(job_id):
            print(f"  SKIP (already seen): {title} at {company}")
        else:
            mark_seen(job_id, title, company)
            print(f"  NEW (saved):         {title} at {company}")

    print(f"\nTotal unique jobs tracked: {count_seen()}")
    print("(Should be 2, not 3 — duplicate was caught)")