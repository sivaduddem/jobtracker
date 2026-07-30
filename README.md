# Internship Intelligence Platform

Real-time Software Engineering internship detection engine.

Monitors ATS platforms (not individual company scrapers) and alerts you within minutes of a matching posting — designed to run continuously on a personal computer at **$0/month**.

## What it does

- Detects **SWE / platform / infrastructure / backend** internships as they go live
- Targets **Summer 2027**, **Fall 2026**, **Winter 2027**, **Spring 2027**
- Sends instant **Telegram** alerts (Discord / email optional)
- Serves a local **dark-mode dashboard** at `http://127.0.0.1:8000`
- Scales toward **10,000+ companies** via shared ATS adapters + YAML config

**Latency goals:** ~30–60s locally for hot/business-hours boards; ~5 min on GitHub Actions cron.

By default, only **United States** locations are kept (`LOCATION_FILTER=us`). Set `LOCATION_FILTER=any` to disable.

## Quick start

### 1. Install

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

### 2. Configure Telegram

1. Open [@BotFather](https://t.me/BotFather) → `/newbot` → copy the bot token
2. Message your new bot once
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy your `chat.id`
4. Fill in `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

### 3. Run

```bash
python main.py
```

Open the dashboard: [http://127.0.0.1:8000](http://127.0.0.1:8000)

| Command | Purpose |
|---------|---------|
| `python main.py` | Poller + dashboard (default) |
| `python main.py --once` | Single poll cycle, then exit |
| `python main.py --discover` | Refresh company registry |
| `python main.py --dashboard-only` | UI only, no polling |

### Docker

```bash
docker compose up --build
```

### GitHub Actions (cron)

Runs `python main.py --once` every **5 minutes** and persists `data/internships.db` between runs via Actions cache (so you are not re-alerted for old jobs).

1. **Settings → Secrets and variables → Actions** → add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - optional: `DISCORD_WEBHOOK_URL`
2. **Actions** tab → **Poll internships** → **Run workflow** (optional manual seed)

The first run seeds the database **without** Telegram (avoids a flood). Later runs notify only for newly seen postings.

**Caveats:** Scheduled jobs may run late; this is usually slower than a local 30–60s poller. Free-tier cron is best as a backup, not a replacement for always-on local/Docker if you need sub-minute latency.



## Architecture

```
mickeydjobtracker/
├── core/               # models, config, scheduler, ranking, discovery, prediction
├── providers/          # ATS adapters
├── companies/
│   └── companies.yaml  # monitored companies (edit this)
├── notifications/      # Telegram, Discord, email (+ future stubs)
├── dashboard/          # FastAPI UI
├── database/           # SQLite
├── tests/
├── main.py
├── Dockerfile
└── docker-compose.yml
```

### Data flow

1. **Scheduler** selects due companies (adaptive intervals + jitter)
2. **Provider** fetches public JSON/GraphQL (HTML only as fallback)
3. **Ranking / filters** keep relevant eng internships and score them
4. **SQLite** dedupes by `provider + company + job_id` and URL hash
5. **Telegram** notifies on brand-new matches above the score threshold
6. **Dashboard** shows jobs, poll status, and errors

### Supported ATS providers

Greenhouse · Lever · Ashby · Workday · SmartRecruiters · Jobvite · iCIMS · Oracle Recruiting · SuccessFactors · Eightfold · Taleo · **Google Careers** (custom)

## Adding companies

Edit `companies/companies.yaml`:

```yaml
companies:
  stripe:
    provider: greenhouse

  deepgram:
    provider: ashby

  cursor:
    provider: ashby
    board_token: cursor

  acme:
    provider: workday
    board_token: "acme:External"
    career_url: https://acme.wd5.myworkdayjobs.com/External
```

No code changes required.

**Finding a board token:** open the company's public careers / jobs page. The ATS slug is usually in the URL, e.g.:

- `boards.greenhouse.io/stripe` → `stripe`
- `jobs.ashbyhq.com/ramp` → `ramp`
- `jobs.lever.co/spotify` → `spotify`

### Automatic discovery

When `ENABLE_DISCOVERY=true` (default), startup will:

- Seed known tech companies
- Pull YC batches from the public Algolia index
- Parse public GitHub internship list READMEs
- Probe Greenhouse / Lever / Ashby / SmartRecruiters endpoints
- Fingerprint careers pages to classify the ATS

Set `ENABLE_DISCOVERY=false` to manage the YAML file only.

## Adding an ATS provider

1. Create `providers/myats.py` subclassing `BaseProvider`
2. Implement `async def fetch(self, company) -> PollResult`
3. Prefer documented JSON endpoints; HTML via BeautifulSoup only if needed
4. Register the class in `providers/__init__.py` → `PROVIDER_CLASSES`
5. Add companies with `provider: myats`

## Configuration

Copy from `.env.example`. Main knobs:

| Variable | Default | Meaning |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | — | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | — | Your Telegram chat id |
| `POLL_BUSINESS_HOURS` | `60` | Poll interval during 8–20 (seconds) |
| `POLL_OFF_HOURS` | `120` | Off-hours interval |
| `POLL_HOT` | `30` | Predicted opening / high priority |
| `POLL_INACTIVE` | `300` | Backoff for quiet or erroring boards |
| `MAX_CONCURRENT_POLLS` | `50` | In-flight HTTP polls |
| `MIN_NOTIFY_SCORE` | `40` | Minimum score to send alerts |
| `EMAIL_SMTP_HOST` | — | e.g. `smtp.gmail.com` |
| `EMAIL_SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `EMAIL_USERNAME` | — | SMTP login (your Gmail) |
| `EMAIL_PASSWORD` | — | Gmail App Password |
| `EMAIL_TO` | — | Recipient (`sivaduddempudi@gmail.com`) |
| `TARGET_TERMS` | Summer 2027, … | Terms used for classification |
| `LOCATION_FILTER` | `us` | `us` or `any` |
| `ENABLE_DISCOVERY` | `true` | Auto-discover companies on startup |
| `DASHBOARD_PORT` | `8000` | Local UI port |

### Adaptive polling

| Situation | Interval |
|-----------|----------|
| Business hours | ~5 min |
| Off hours | ~20 min |
| Predicted opening window | ~2 min |
| Recent activity | higher priority |
| Repeated errors / never found | less frequent |

Also uses ETag / Last-Modified, exponential backoff, and randomized jitter so thousands of companies don't sync-hit at once.

### Ranking

Configurable in `core/config.py`:

| Score | Example |
|------:|---------|
| 100 | Software Engineer Intern Summer 2027 |
| 98 | Platform Engineering Intern |
| 97 | Infrastructure Intern |
| 95 | Backend Intern |
| 92 | Distributed Systems Intern |
| 90 | Security Engineering Intern |
| 80 | Full Stack Intern |
| 40 | Frontend Intern |
| 0 | Non-engineering / excluded |

Titles must contain a real `intern` / `internship` word (so `Internal` / `International` do not match).

## Telegram alert example

```text
🚨 NEW INTERNSHIP

Company:
Databricks

Title:
Software Engineer Intern

Term:
Summer 2027

Location:
Mountain View, CA

Detected:
2:13 PM EST

Provider:
Greenhouse

Apply:
https://...

Score:
98
```

Inline buttons: **Open Posting** · **Dismiss**

## Dashboard

- Companies monitored, active / removed jobs
- Recent openings with search, sort, filter
- Polling status and recent errors
- Last successful scrape
- CSV / JSON export
- Force poll via **Poll now** or `POST /api/poll`
- Application tracker API (`/api/applications/{dedupe_key}`)

## Testing

```bash
pytest -q
```

Covers ranking, dedupe, provider normalization, notifications, storage, and prediction.

## Cost

- **$0/month** — local Python, SQLite, free public ATS APIs
- No paid APIs, no OpenAI, no required cloud compute
- Optional Docker on the same machine

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No Telegram messages | Confirm token + chat id; message the bot once first |
| Empty job feed | Run `python main.py --once`; check `board_token` values |
| Many 404s | Wrong ATS slug — copy it from the public careers URL |
| Workday failures | Use `board_token: tenant:site` and set `career_url` |
| High CPU | Lower `MAX_CONCURRENT_POLLS` |
| Noisy discovery | Set `ENABLE_DISCOVERY=false` |

## Development

- Python **3.12+**
- Async-first (`asyncio` + `aiohttp`)
- Pydantic v2 models + type hints
- Never commit `.env` or `data/*.db`

```bash
pytest -q
python main.py --once
```

## Roadmap

- [x] CSV / JSON export
- [x] Application tracker schema + API
- [x] Historical openings + prediction windows
- [x] Daily digest helper (`core/digest.py`)
- [ ] Scheduled daily digest cron
- [ ] RSS feed
- [ ] Activity graphs
- [ ] Browser extension
- [ ] Auto-generated GitHub internship repo

Notification stubs ready for Slack, Pushover, and ntfy in `notifications/future.py`.

## License

MIT — see [LICENSE](LICENSE).
