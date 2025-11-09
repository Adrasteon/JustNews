JustNews DB exporter
=====================

This repository-level note documents the justnews DB exporter service we added to expose simple ChromaDB and MariaDB connectivity metrics for Prometheus.

What changed
------------
- A small exporter script lives at: /opt/justnews/monitoring/exporters/justnews_db_exporter.py
- A virtualenv is used by the service: /opt/justnews/monitoring/exporters/venv (owned by user justnews)
- Systemd unit: /etc/systemd/system/justnews-db-exporter.service
  - The unit includes an ExecStartPost health probe (waits ~5s for /metrics) and Restart/RestartSec/StartLimit* settings to prevent hot crash loops.

Operational notes
-----------------
- To update exporter dependencies:
  sudo -u justnews /opt/justnews/monitoring/exporters/venv/bin/pip install --upgrade prometheus_client requests

- To check metrics locally:
  curl -sS http://127.0.0.1:9127/metrics | head -n 40

- To inspect systemd unit and recent logs:
  sudo systemctl status justnews-db-exporter.service
  sudo journalctl -u justnews-db-exporter.service -n 200

Why this approach
-----------------
Using a venv under /opt avoids running the exporter under a human user's home directory and keeps the service isolated. The ExecStartPost probe gives a quick fail-fast behaviour so systemd will restart the service if it doesn't come up correctly.

Alerting (repo)
----------------
We added a simple Prometheus alerting rules file in the repository. Path:

  infrastructure/monitoring/alerts/justnews_db_alerts.yml

Rules included (high level):
- `ChromaDBDown`: fires when `justnews_chromadb_up == 0` for 1 minute (severity: critical)
- `MariaDBDown`: fires when `justnews_mariadb_up == 0` for 1 minute (severity: critical)

To enable these rules in the deployed Prometheus server, add the file (or a symlink) under `/etc/justnews/monitoring/rules/` and include it in Prometheus' `rule_files` or add the directory to the Prometheus configuration, then reload Prometheus:

  sudo mkdir -p /etc/justnews/monitoring/rules
  sudo cp infrastructure/monitoring/alerts/justnews_db_alerts.yml /etc/justnews/monitoring/rules/
  # then either reload or restart Prometheus
  sudo systemctl reload justnews-prometheus.service || sudo systemctl restart justnews-prometheus.service

Why this approach
-----------------
Using a venv under `/opt` avoids running the exporter under a human user's home directory and keeps the service isolated. The `ExecStartPost` probe gives a quick fail-fast behaviour so systemd will restart the service if it doesn't come up correctly.

Operational runbook snippet
--------------------------
- Check metrics:
  curl -sS http://127.0.0.1:9127/metrics

- Update deps:
  sudo -u justnews /opt/justnews/monitoring/exporters/venv/bin/pip install --upgrade prometheus_client requests

- Restart exporter service:
  sudo systemctl restart justnews-db-exporter.service

- Check Prometheus target status:
  curl -sS http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="justnews-db-exporter")'
