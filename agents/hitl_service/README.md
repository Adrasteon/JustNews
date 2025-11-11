# HITL Service

Human-in-the-loop ingestion service that stores annotator decisions in SQLite and integrates with the shared MCP Bus for ingest dispatch.

Run locally using your project Conda environment (recommended):

```bash
conda activate justnews-v2-py312
# install minimal runtime deps (conda-first, fallback to pip if needed)
conda install -c conda-forge fastapi uvicorn
# if a package is unavailable via conda, use pip inside the activated env:
pip install -r agents/hitl_service/requirements.txt

# run the service from the repository root (use an unused port; 8040 is open)
uvicorn agents.hitl_service.app:app --reload --port 8040
```

Open the annotator UI at http://localhost:8040/static/index.html

Notes:
- Set `MCP_BUS_URL` if the bus is not running on `http://localhost:8000`.
- Override `HITL_AGENT_NAME`/`HITL_SERVICE_ADDRESS` when deploying behind non-localhost addresses.
- Use `HITL_FORWARD_AGENT`/`HITL_FORWARD_TOOL` to define the downstream agent+tool that should receive ingest jobs. The target tool must accept a JSON payload shaped like `ingest_payload` from `/api/label`.
- Use `HITL_CANDIDATE_FORWARD_AGENT`/`HITL_CANDIDATE_FORWARD_TOOL` if candidates should also be echoed to another consumer immediately after creation.
- Provide `HITL_PRIORITY_SITES` as a comma-separated list to boost queue priority for high-value sources.
- Set `HITL_DB_PATH` to change the SQLite database location; defaults to `agents/hitl_service/hitl_staging.db`.
- Annotators must supply their ID in the UI; it is cached locally in the browser for convenience.
- QA reviewers can resolve samples via `POST /api/qa/review` with a `pass`/`fail` status to drain the QA queue.
- Enable training-forward dispatch by exporting `HITL_TRAINING_FORWARD_AGENT=training_system` and `HITL_TRAINING_FORWARD_TOOL=receive_hitl_label`; monitor `hitl_training_forward_success_total` together with the training system counter `justnews_training_examples_total{example_type="hitl_label"}` to confirm end-to-end flow.
