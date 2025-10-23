
### DEPRECATED: Dockerfiles are deprecated for core deployments. Prefer native Ubuntu deployment. See markdown_docs/development_reports/DEPRECATE_DOCKER.md
FROM python:3.11-slim

WORKDIR /app

COPY agents/memory/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY agents/memory/main.py .
COPY agents/memory/tools.py .
COPY agents/memory/db_migrations ./db_migrations

ENV PYTHONPATH="/app"

EXPOSE 8007
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007"]
