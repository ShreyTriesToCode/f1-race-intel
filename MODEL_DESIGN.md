# Model Design

The model is a hybrid system.

It combines:

1. ML model trained from historical Jolpica data:
   - RandomForestClassifier
   - HistGradientBoostingClassifier
   - targets: win, podium, top 10
   - time-aware validation using the most recent available season

2. Rule-based racing ensemble:
   - driver form
   - constructor form
   - qualifying/grid importance
   - circuit history
   - race pace from lap data
   - pit execution
   - strategy gain from grid-to-finish change
   - reliability
   - team-track fit
   - weather adaptation

3. Optional FastF1 signals:
   - clean-lap pace
   - lap-time consistency
   - longest stint proxy
   - loaded session audit

4. Dashboard scenario layer:
   - rain risk
   - safety car
   - high tyre degradation
   - low overtaking
   - baseline
