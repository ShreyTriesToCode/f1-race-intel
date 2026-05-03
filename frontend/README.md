# Race Intel Vercel Dashboard

This is the upgraded Vercel frontend for your F1 briefing bot.

It reads generated data from your GitHub repo:

- `briefings/index.json`
- `briefings/*.md`
- `data_cache/latest-model-debug.json`

## Features included

- F1-style animated UI
- Official F1 media image mappings with fallbacks
- Driver prediction cards
- Driver detail modal with component scores
- Prediction stage and confidence display
- Strategy simulator
- Live Race Hub with timing-style dashboard
- Official F1 TV and Live Timing links
- Model transparency and data-source audit
- Briefing archive
- Mobile responsive layout

## Setup

```bash
npm install
npm run dev
```

## Vercel deployment

Set this environment variable only if your repo changes:

```bash
NEXT_PUBLIC_F1_DATA_BASE_URL=https://raw.githubusercontent.com/ShreyTriesToCode/f1-briefing-bot/main
```

Then deploy to Vercel.

## Legal note

This dashboard does not stream F1 race video. It links to official viewing and live timing pages.
