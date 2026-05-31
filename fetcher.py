"""
fetcher.py
Pulls fresh internship listings from 3 sources:
  1. Jobicy API     — free, no key, remote global tech roles (occasional)
  2. SimplifyJobs   — GitHub repo, 350+ global CS internships, HTML parsed
  3. Internshala    — India's biggest student internship platform, scraped

Every listing is returned in the same clean format:
{
    "title":    str,
    "company":  str,
    "location": str,
    "url":      str,
    "source":   str
}
"""

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10

SIMPLIFY_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2026-Internships/dev/README.md"
)

# Internshala category slugs — these map to the user's field selection
INTERNSHALA_CATEGORIES = {
    "Software Engineering":     "computer-science",
    "Data Science / ML / AI":   "data-science",
    "Product Management":       "product-management",
    "Design (UI/UX)":           "ui-ux-design",
    "Finance / Business":       "finance",
    "Marketing / Growth":       "marketing",
}


# ─────────────────────────────────────────
# SOURCE 1: Jobicy
# ─────────────────────────────────────────

def fetch_jobicy(keywords=None):
    results = []
    params = {"count": 50}

    if keywords and isinstance(keywords, list) and len(keywords) > 0:
        params["tag"] = keywords[0]
    elif keywords and isinstance(keywords, str):
        params["tag"] = keywords

    try:
        resp = requests.get(
            "https://jobicy.com/api/v2/remote-jobs",
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        for job in data.get("jobs", []):
            job_type = job.get("jobType", "")
            if isinstance(job_type, list):
                job_type = " ".join(job_type).lower()
            else:
                job_type = job_type.lower()
            if "intern" not in job_type:
                continue

            results.append({
                "title":    job.get("jobTitle", "Unknown Title"),
                "company":  job.get("companyName", "Unknown Company"),
                "location": job.get("jobGeo", "Remote"),
                "url":      job.get("url", ""),
                "source":   "jobicy",
            })

    except requests.exceptions.Timeout:
        print("  [fetcher] Jobicy timed out, skipping.")
    except requests.exceptions.RequestException as e:
        print(f"  [fetcher] Jobicy error: {e}")
    except Exception as e:
        print(f"  [fetcher] Jobicy unexpected error: {e}")

    print(f"  [fetcher] Jobicy → {len(results)} internships found")
    return results


# ─────────────────────────────────────────
# SOURCE 2: SimplifyJobs (HTML table)
# ─────────────────────────────────────────

def fetch_simplify():
    results = []

    try:
        resp = requests.get(SIMPLIFY_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("tr")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            company  = cols[0].get_text(strip=True)
            role     = cols[1].get_text(strip=True)
            location = cols[2].get_text(strip=True)

            url = ""
            if len(cols) > 3:
                link = cols[3].find("a")
                if link and link.get("href"):
                    url = link["href"]

            if "🔒" in company or "🔒" in role:
                continue

            company = company.replace("🔥", "").strip()

            if not company or not role:
                continue

            results.append({
                "title":    role,
                "company":  company,
                "location": location,
                "url":      url,
                "source":   "simplify",
            })

    except requests.exceptions.Timeout:
        print("  [fetcher] SimplifyJobs timed out, skipping.")
    except requests.exceptions.RequestException as e:
        print(f"  [fetcher] SimplifyJobs error: {e}")
    except Exception as e:
        print(f"  [fetcher] SimplifyJobs unexpected error: {e}")

    print(f"  [fetcher] SimplifyJobs → {len(results)} internships found")
    return results


# ─────────────────────────────────────────
# SOURCE 3: Internshala (scraped HTML)
# ─────────────────────────────────────────

def fetch_internshala(fields=None):
    """
    Scrapes internships from Internshala.
    `fields` is a list of user-selected fields like
    ['Software Engineering', 'Finance / Business'].
    For each matched field, fetches one page of listings.
    """
    results = []

    # Build list of category slugs to scrape — default to computer-science
    slugs = []
    if fields and isinstance(fields, list):
        for f in fields:
            slug = INTERNSHALA_CATEGORIES.get(f)
            if slug:
                slugs.append(slug)
    if not slugs:
        slugs = ["computer-science"]

    for slug in slugs:
        url = f"https://internshala.com/internships/{slug}-internship/"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            # Each internship card is a div with class 'individual_internship'
            cards = soup.find_all("div", class_="individual_internship")

            for card in cards:
                # Title — the page uses <h2 class="job-internship-name">
                title_tag = card.find(class_="job-internship-name")
                if not title_tag:
                    continue
                title_link = title_tag.find("a")
                title = title_link.get_text(strip=True) if title_link else title_tag.get_text(strip=True)

                # Company name — <p class="company-name">
                company_tag = card.find("p", class_="company-name")
                company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                # Location — inside "row-1-item locations" → <span><a>City</a></span>
                location = "Unknown"
                loc_div = card.find("div", class_="locations")
                if loc_div:
                    # Get all text, strip whitespace, collapse spaces
                    location = " ".join(loc_div.get_text(" ", strip=True).split())

                # URL — prefer the title link's href, fallback to data-href on card
                url_path = ""
                if title_link and title_link.get("href"):
                    url_path = title_link["href"]
                elif card.get("data-href"):
                    url_path = card["data-href"]

                full_url = (
                    f"https://internshala.com{url_path}"
                    if url_path.startswith("/")
                    else url_path
                )

                if not title or not company:
                    continue

                results.append({
                    "title":    title,
                    "company":  company,
                    "location": location,
                    "url":      full_url,
                    "source":   "internshala",
                })

        except requests.exceptions.Timeout:
            print(f"  [fetcher] Internshala/{slug} timed out, skipping.")
        except requests.exceptions.RequestException as e:
            print(f"  [fetcher] Internshala/{slug} error: {e}")
        except Exception as e:
            print(f"  [fetcher] Internshala/{slug} unexpected error: {e}")

    print(f"  [fetcher] Internshala → {len(results)} internships found")
    return results


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def fetch_all(preferences):
    print("\n[fetcher] Starting fetch from all sources...")
    keywords = preferences.get("keywords", [])
    fields   = preferences.get("field", [])

    all_jobs = []
    all_jobs += fetch_jobicy(keywords=keywords)
    all_jobs += fetch_simplify()
    all_jobs += fetch_internshala(fields=fields)

    print(f"[fetcher] Total raw listings fetched: {len(all_jobs)}\n")
    return all_jobs


if __name__ == "__main__":
    fake_prefs = {
        "field": ["Software Engineering", "Data Science / ML / AI"],
        "work_type": "Both (no preference)",
        "location_preference": ["Hyderabad", "Bangalore"],
        "keywords": ["python", "backend"],
    }

    jobs = fetch_all(fake_prefs)

    print("=" * 50)
    print("Sample of first 5 results from EACH source:\n")
    by_source = {}
    for job in jobs:
        by_source.setdefault(job["source"], []).append(job)
    for source, jlist in by_source.items():
        print(f"-- {source.upper()} --")
        for job in jlist[:3]:
            print(f"  {job['title']} @ {job['company']}")
            print(f"  Location: {job['location']}")
            print(f"  URL:      {job['url'][:70]}")
            print()