# Hybrid Prediction Model Notes

This dashboard uses a best-of-both approach.

It does not directly import the Mintlify project's trained model. To do that exactly, we would need to clone that repo, build its historical dataset, train or load its Random Forest/XGBoost models, and keep those model files in the backend.

Instead, this Vercel dashboard and your existing GitHub Actions backend combine:

1. Mintlify-style ML feature groups:
   - grid / qualifying importance
   - driver historical performance
   - recent form
   - team average performance
   - circuit experience
   - weather impact
   - tire degradation and pit window logic
   - race simulation scenarios

2. Your existing free-data model:
   - Jolpica schedule, standings, results, qualifying, laps, pit stops, sprint data
   - FastF1 optional session pace, consistency, tyre/stint signals
   - Open-Meteo forecast and historical weather
   - ICS calendar event matching
   - GitHub Issues, Markdown, JSON output, and email automation

The result is a hybrid ensemble-style system that remains free, deployable, and reliable on GitHub Actions and Vercel.
