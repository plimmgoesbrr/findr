# findr

A personal internship bot that scrapes listings, uses AI to match them against your preferences, and sends the best ones to your WhatsApp every 4 hours — fully automated in the cloud, free to run.

> Built in 2 days by [Karthik](https://github.com/plimmgoestotim) as a learning project. Currently runs on GitHub Actions for a single user. See [What's next](#whats-next) for scaling ideas.

---

## What it does

Every 4 hours, the bot:

1. **Fetches** ~500 fresh internship listings from Jobicy, SimplifyJobs, and Internshala
2. **Dedupes** against ones you've already seen (SQLite + MD5 hashes)
3. **Pre-filters** by keywords (drops obvious misses before touching the AI)
4. **Scores** the rest with Groq's hosted Llama/GPT-OSS model (0–10 relevance)
5. **Buckets** matches into India / Abroad with city-level priority (Hyderabad → Bangalore → ... | USA → UK → Canada → ...)
6. **Sends** two WhatsApp messages — top 5 per bucket — via Twilio

If nothing new matched this run, the bot stays silent. No spam.

---

## The stack

| Layer | Tool | Why |
|---|---|---|
| Language | Python 3.12 | Standard, batteries included |
| Scraping | `requests` + `beautifulsoup4` | Jobicy JSON API, SimplifyJobs HTML, Internshala HTML |
| Dedup | `sqlite3` (built-in) | Single-file DB, no server needed |
| AI matching | Groq free tier (`openai/gpt-oss-120b`) | 14,400 req/day free, fast inference |
| Notifications | Twilio WhatsApp Sandbox | Free $15 credit, no WhatsApp Business approval needed |
| Scheduler | GitHub Actions cron | Free for public/private repos, 2000 min/month |
| Secrets | GitHub Secrets + local `.env` | Keys never touch committed code |

---

## Architecture

```
preferences.json ─┐
                  ↓
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ fetcher  │ → │ database │ → │ matcher  │ → │ notifier │
   │  (web)   │   │ (dedup)  │   │  (AI)    │   │(WhatsApp)│
   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                        │                              │
                        ↓                              ↓
                 seen_jobs.db                     your phone
```

Each file does exactly one thing:

| File | Responsibility |
|---|---|
| `preferences.py` | One-time onboarding → saves `preferences.json` |
| `database.py` | SQLite tracker — never notify about the same listing twice |
| `fetcher.py` | Pulls raw listings from 3 sources, normalizes to one shape |
| `matcher.py` | Keyword pre-filter + Groq AI scoring with balanced India/Abroad caps |
| `notifier.py` | Location classification, Twilio API calls, two-message split |
| `main.py` | Orchestrator — calls everything in order, runs once per invocation |
| `.github/workflows/run.yml` | GitHub Actions cron schedule |

---

## Setup — run it for yourself

### Prerequisites
- Python 3.12+
- A free [Groq API key](https://console.groq.com)
- A free [Twilio account](https://www.twilio.com/try-twilio) with the WhatsApp Sandbox activated

### Local setup

```bash
# Clone and enter
git clone https://github.com/<your-user>/findr.git
cd findr

# Install dependencies
pip3 install requests beautifulsoup4

# Create your .env from the template
cp .env.example .env
# Then edit .env and fill in your actual keys

# Create your preferences (interactive)
python3 preferences.py

# Test one run
python3 main.py
```

If everything's wired up right, you'll get two WhatsApp messages within ~30 seconds.

### Activate the Twilio WhatsApp Sandbox

Twilio's sandbox is free but needs a one-time handshake:

1. In the Twilio console, go to **Messaging → Try it out → Send a WhatsApp message**
2. From your personal WhatsApp, send `join <two-word-code>` to `+1 415 523 8886`
3. The sandbox session stays active for 72 hours per inbound message — reply "ok" to any bot message to keep it alive

### Deploy to GitHub Actions (for 24/7 runs)

1. Push your code to a GitHub repo
2. In **Settings → Secrets and variables → Actions**, add 5 secrets:
   - `GROQ_API_KEY`
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_WHATSAPP_FROM` (value: `+14155238886`)
   - `PREFERENCES_JSON` (paste the full contents of your `preferences.json`)
3. The workflow in `.github/workflows/run.yml` auto-runs every 4 hours
4. Trigger manually from the **Actions** tab for immediate testing

---

## Configuration

All tunable constants live at the top of each file:

| File | Setting | What it controls |
|---|---|---|
| `matcher.py` | `MATCH_THRESHOLD = 8` | Min score (0–10) a listing needs to be sent |
| `matcher.py` | `BATCH_SIZE = 25` | Listings per Groq API call |
| `matcher.py` | `MAX_BATCHES = 10` | Hard cap per run (safety for free tier) |
| `matcher.py` | `MODEL` | Which Groq model to use |
| `notifier.py` | `INDIA_CITIES_PRIORITY` | Reorder for your home city |
| `notifier.py` | `ABROAD_REGIONS_PRIORITY` | Reorder for your target geography |
| `.github/workflows/run.yml` | `cron: "0 */4 * * *"` | How often the bot runs |

To add more Indian cities or abroad countries, extend the keyword lists in `notifier.py`.

---

## Sources

| Source | Type | Volume | Notes |
|---|---|---|---|
| [SimplifyJobs](https://github.com/SimplifyJobs/Summer2026-Internships) | GitHub README (HTML table) | ~350 global CS internships | Community-updated hourly, highest signal |
| [Internshala](https://internshala.com) | Scraped HTML | ~50/category | Best source for India |
| [Jobicy](https://jobicy.com) | Public JSON API | Occasional internships | Free, no key, mostly full-time though |

Adding a source means writing one `fetch_X()` function that returns the normalized shape — nothing else in the pipeline needs to change.

---

## Security

- `.env` and `preferences.json` are gitignored and never committed
- Templates (`.env.example`, `preferences.example.json`) are committed so others can set up their own copy
- GitHub Secrets are encrypted at rest and auto-redacted from workflow logs
- Phone number is masked in logs as `+91***2148`
- No user data is ever sent anywhere except Twilio (for WhatsApp delivery) and Groq (for scoring)

If you fork this repo, **you must create your own `.env` and GitHub Secrets** — none of my keys are included.

---

## Bugs you'll probably hit

| Symptom | Cause | Fix |
|---|---|---|
| `429 Too Many Requests` | Groq rate limit | Lower `MAX_BATCHES`, or wait a minute |
| `21617: body exceeds 1600 chars` | Too many matches in one WhatsApp | Lower the top-5 cap in `notifier.py` |
| `No module named 'bs4'` | Missing dependency | `pip3 install beautifulsoup4` |
| Only Abroad message, no India | Seen DB already has all India | Delete `seen_jobs.db` to reset |
| Twilio stops delivering | 72hr sandbox session expired | Resend the `join` code from WhatsApp |
| Model returns 404 | Groq deprecated a model | Check [Groq deprecations](https://console.groq.com/docs/deprecations) and update `MODEL` |

---

## What's next

- [ ] Add [Unstop](https://unstop.com) as a 4th source for broader Indian coverage
- [ ] Multi-user web signup (currently one user per deployment)
- [ ] Replace Twilio sandbox with WhatsApp Business API (needs Meta business verification)
- [ ] Learn-from-feedback — thumbs up/down on messages to train a per-user ranker
- [ ] Dashboard to view past matches and apply-tracking

---

## License

MIT. Fork it, break it, make it yours.

---

Built with Groq, Twilio, GitHub Actions, and far too many 429 errors.
