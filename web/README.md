# Dashboard

Executive briefing for Transcript Intelligence. It reads `src/data/report.json`, which the pipeline writes.

From the repository root:

```bash
python -m src.pipeline.runner --data data --output output
cd web
npm install
npm run dev
```

The dev server listens on port 43123. Setup for the pipeline and the reasoning behind the briefing are in the root README.
