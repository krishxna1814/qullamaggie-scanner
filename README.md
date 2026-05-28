# Qullamaggie Breakout Scanner

A $0-cost Qullamaggie-style breakout stock scanner using GitHub Actions + Telegram Bot.

## How It Works

- **GitHub Actions** runs scheduled scans for free (2000 min/month)
- **Telegram Bot** receives alerts and lets you trigger scans on demand
- **No servers, no databases, no credit card** required

## Architecture

```
GitHub Actions (scheduler + runner)
├── EOD Scan: Mon-Fri 4:30 PM EST
├── Midday: Mon-Fri 12:30 PM EST
├── Intraday: Every 30 min market hours
└── Weekly Deep: Sunday 8 PM EST
        │
        ▼
fetches data → runs 6-layer filter → sends Telegram alert → saves to repo

Telegram Bot (PythonAnywhere)
└── /scan, /quick, /weekly, /check, /status, /last commands
```

## Setup Guide

### STEP 1 — Fork/Clone this repo to GitHub

Click Fork or clone and push to your own GitHub account.

### STEP 2 — Create Telegram Bot

1. Open Telegram, search for `@BotFather`
2. Send `/newbot` and follow prompts
3. Save the bot token you receive

### STEP 3 — Get your Chat ID

1. Open Telegram, search for `@userinfobot`
2. Send `/start`
3. Copy your numeric chat ID

### STEP 4 — Add GitHub Secrets

1. Go to your repo on GitHub: **Settings → Secrets and Variables → Actions**
2. Add these secrets:

| Secret | Value |
|---|---|
| `TELEGRAM_TOKEN` | Your bot token from BotFather |
| `CHAT_ID` | Your chat ID from userinfobot |

### STEP 5 — Enable GitHub Actions

1. Go to the **Actions** tab in your repo
2. Click **Enable Actions**
3. The scanner will run on its schedule automatically

### STEP 6 — Run first scan

1. Go to **Actions → Breakout Scanner → Run workflow**
2. Select mode: `scan` and click **Run**
3. Wait 2-5 minutes, check Telegram for results

### STEP 7 — Setup Telegram Command Bot (Optional)

For /scan /quick /check commands from Telegram:

1. Sign up for [PythonAnywhere](https://www.pythonanywhere.com) (free tier)
2. Upload `bot/telegram_bot.py`
3. Create a `.env` file with:
   ```
   TELEGRAM_TOKEN=your_token
   GITHUB_TOKEN=your_github_pat
   GITHUB_REPO=your_username/your_repo
   CHAT_ID=your_chat_id
   ```
4. Run: `python telegram_bot.py`
5. **Note:** Free PythonAnywhere tier does not keep the bot alive 24/7. For always-on, upgrade to paid ($5/mo) or keep the bot running on your local machine.

## Scan Modes

| Mode | Command | Data | Speed |
|---|---|---|---|
| EOD Scan | `python main.py --scan` | 6 months, all candidates | 3-5 min |
| Quick | `python main.py --quick` | 5 days, top 200 only | 1-2 min |
| Weekly | `python main.py --weekly` | 1 year, all candidates | 5-10 min |
| Check | `python main.py --check AAPL` | 1 year, single stock | 10 sec |
| Status | `python main.py --status` | N/A | instant |

## Qullamaggie Filter Layers

1. **Liquidity** — Price > $10, 50d avg vol > 500k
2. **Uptrend** — Close > 50/150/200 EMA
3. **Near 52w High** — Within 15% of yearly high
4. **VCP Consolidation** — 15d tightness < 12%, volume declining
5. **Breakout** — Volume spike 1.5x, new 10d high, 1%+ day
6. **EP Candidate** — Volume 3x, range 2x avg

## File Structure

```
breakout_scanner/
├── .github/workflows/scanner.yml   # GitHub Actions schedule
├── src/
│   ├── universe.py                 # NASDAQ fetcher + pre-filter
│   ├── fetcher.py                  # Smart data fetcher
│   ├── scanner.py                  # 6-layer Qullamaggie scanner
│   ├── alerts.py                   # Telegram alert sender
│   └── utils.py                    # Helpers
├── bot/
│   └── telegram_bot.py            # Telegram command bot
├── main.py                        # CLI entry point
├── requirements.txt               # Dependencies
├── .env.example                   # Secret template
├── universe.csv                   # Pre-seeded ticker list
└── README.md                      # This file
```
