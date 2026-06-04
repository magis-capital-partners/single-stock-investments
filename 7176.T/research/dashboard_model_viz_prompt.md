# Dashboard model visualization

Implementation spec for showing this ticker’s earnings model on the main portfolio dashboard:

**[`_system/prompts/dashboard_equity_model_viz.md`](../../_system/prompts/dashboard_equity_model_viz.md)**

Pilot ticker: **7176.T**. Model artifacts live in [`research/model/`](model/).

After an agent implements the dashboard UI, rebuild:

```bash
python _system/scripts/build_dashboard_data.py
cd dashboard && python -m http.server 8765
```

Open http://localhost:8765/ → **Models** tab (or model workspace from the 7176 detail panel).
