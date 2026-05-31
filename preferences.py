"""
preferences.py
Runs once on first launch. Collects user preferences and phone number.
Saves everything to preferences.json.
"""

import json
import os
import re

PREFS_FILE = "preferences.json"


def ask(prompt, options=None, allow_multiple=False):
    """Ask a question, optionally with numbered options."""
    print(f"\n{prompt}")
    if options:
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        if allow_multiple:
            print("  (Enter numbers separated by commas, e.g. 1,3)")
        while True:
            raw = input("> ").strip()
            if allow_multiple:
                try:
                    picks = [int(x.strip()) for x in raw.split(",")]
                    if all(1 <= p <= len(options) for p in picks):
                        return [options[p - 1] for p in picks]
                except ValueError:
                    pass
                print(f"Please enter valid numbers between 1 and {len(options)}.")
            else:
                try:
                    pick = int(raw)
                    if 1 <= pick <= len(options):
                        return options[pick - 1]
                except ValueError:
                    pass
                print(f"Please enter a number between 1 and {len(options)}.")
    else:
        return input("> ").strip()


def validate_phone(number):
    """
    Basic validation: must start with + and contain 7-15 digits.
    E.g. +919876543210
    """
    pattern = re.compile(r"^\+\d{7,15}$")
    return bool(pattern.match(number))


def collect_preferences():
    print("\n" + "=" * 50)
    print("  INTERNSHIP BOT — SETUP")
    print("=" * 50)
    print("Answer a few quick questions. This runs only once.\n")

    # Field — now allows multiple
    field = ask(
        "What field(s) are you looking for? (you can pick multiple)",
        options=[
            "Software Engineering",
            "Data Science / ML / AI",
            "Product Management",
            "Design (UI/UX)",
            "Finance / Business",
            "Marketing / Growth",
            "Other",
        ],
        allow_multiple=True,
    )

    if "Other" in field:
        other = ask("Describe your other field (e.g. Cybersecurity, Embedded Systems):")
        field = [f for f in field if f != "Other"] + [other]

    # Work type
    work_type = ask(
        "What kind of internship?",
        options=["Remote only", "In-person only", "Both (no preference)"],
    )

    # Location preference
    location_pref = []
    if work_type != "Remote only":
        print("\nAny preferred cities or countries for in-person? (e.g. Hyderabad, Bangalore, USA)")
        print("Press Enter to skip (no preference).")
        raw_loc = input("> ").strip()
        if raw_loc:
            location_pref = [x.strip() for x in raw_loc.split(",") if x.strip()]

    # Experience level
    experience = ask(
        "Your experience level?",
        options=["Fresher / No experience", "Some projects / 1 internship", "Multiple internships"],
    )

    # Extra keywords
    print("\nAny specific keywords to look for? (e.g. React, Python, Finance, Fintech)")
    print("Press Enter to skip.")
    raw_keywords = input("> ").strip()
    keywords = [x.strip() for x in raw_keywords.split(",") if x.strip()] if raw_keywords else []

    # Phone number
    print("\n" + "-" * 50)
    print("Finally, your WhatsApp number.")
    print("Format: +[country code][number]  e.g. +919876543210")
    print("This is the ONLY personal data stored. It stays on your machine.")
    while True:
        number = input("> ").strip()
        if validate_phone(number):
            break
        print("Invalid format. Must start with + followed by 7-15 digits. Try again.")

    prefs = {
        "field": field,
        "work_type": work_type,
        "location_preference": location_pref,
        "experience": experience,
        "keywords": keywords,
        "phone": number,
    }

    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

    print("\n✅ Preferences saved. Bot will now run in the background.")
    print(f"   Field(s):    {', '.join(field)}")
    print(f"   Work type:   {work_type}")
    print(f"   Locations:   {', '.join(location_pref) if location_pref else 'Any'}")
    print(f"   Keywords:    {', '.join(keywords) if keywords else 'None'}")
    print(f"   Phone:       {number}")
    print()

    return prefs


def load_preferences():
    """Load preferences from file. Returns None if not set up yet."""
    if not os.path.exists(PREFS_FILE):
        return None
    with open(PREFS_FILE, "r") as f:
        return json.load(f)


if __name__ == "__main__":
    prefs = collect_preferences()
    print("Loaded back from file:", load_preferences())