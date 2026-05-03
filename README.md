# F1 Hybrid Prediction Bot + Vercel Dashboard

This is the full upgraded version of your F1 briefing project.

## What is included

### Backend

- `f1_briefing.py`
- Free data core: Jolpica + Open-Meteo + ICS
- Optional FastF1 session enhancement
- ML training pipeline inspired by the Mintlify F1 prediction project
- Saved model auto-retraining after a newer completed race is detected
- Hybrid prediction scoring:
  - ML win probability
  - ML podium probability
  - ML top 10 probability
  - driver form
  - car/team performance
  - recent result
  - qualifying/grid position
  - circuit history
  - race pace
  - pit-stop execution
  - team strategy gain
  - reliability
  - team-track fit
  - weather adaptation
  - FastF1 pace/consistency/stint signals where available
- Markdown briefing generation
- `briefings/index.json` generation for the dashboard
- `data_cache/latest-model-debug.json` for model transparency
- GitHub issue update
- Email notification

### GitHub Actions

- `.github/workflows/f1-briefing.yml`
- Runs daily
- Runs every 6 hours during race-weekend days
- Supports manual force retrain
- Caches pip, FastF1, and HTTP data
- Uploads generated files as workflow artifacts
- Commits and pushes updated briefings, model files, and debug JSON

### Vercel dashboard

- `frontend/`
- Next.js app
- F1-style animated UI
- prediction cards
- driver detail modal
- strategy simulator
- live race hub with official viewing links
- model transparency panel
- archive viewer
- official media mappings with fallbacks

## Setup in your existing repo

Copy these files into the root of your existing `f1-briefing-bot` repo:

```bash
cp f1_briefing.py /path/to/f1-briefing-bot/
cp requirements.txt /path/to/f1-briefing-bot/
mkdir -p /path/to/f1-briefing-bot/.github/workflows
cp .github/workflows/f1-briefing.yml /path/to/f1-briefing-bot/.github/workflows/f1-briefing.yml
```

Then commit:

```bash
git add f1_briefing.py requirements.txt .github/workflows/f1-briefing.yml
git commit -m "Add hybrid ML F1 prediction bot and auto retraining workflow"
git push
```

## Required GitHub secrets

Add these in your repo:

```text
F1_ICS_URL
EMAIL_ADDRESS
EMAIL_APP_PASSWORD
EMAIL_TO
```

`GITHUB_TOKEN` is provided automatically by GitHub Actions.

## Vercel setup

Deploy the `frontend` folder to Vercel.

Set this environment variable in Vercel:

```text
NEXT_PUBLIC_F1_DATA_BASE_URL=https://raw.githubusercontent.com/ShreyTriesToCode/f1-briefing-bot/main
```

## Important note about Mintlify model

This project does not copy a trained model from the Mintlify project. It uses the same kind of feature logic and ensemble design, then combines that with your own free-data backend. Directly using their trained model would require cloning that project, reproducing its training data, maintaining saved model files, and adapting feature schemas.

## Legal live dashboard note

The dashboard does not stream race video. It provides a timing-style hub and official links to F1 TV/live timing.
