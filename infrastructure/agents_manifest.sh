#!/usr/bin/env bash
# Canonical agents manifest — single source of truth for agent names, modules and ports
# Format per-entry: name|python_module_or_placeholder|port
# - name: instance name used for systemd unit and logs
# - python_module_or_placeholder: module path used by uvicorn for dev start; placeholder for systemd-only agents
# - port: TCP port the agent listens on

AGENTS_MANIFEST=(
  "mcp_bus|agents.mcp_bus.main:app|8000"
  "chief_editor|agents.chief_editor.main:app|8001"
  "scout|agents.scout.main:app|8002"
  "fact_checker|agents.fact_checker.main:app|8003"
  "analyst|agents.analyst.main:app|8004"
  "synthesizer|agents.synthesizer.main:app|8005"
  "critic|agents.critic.main:app|8006"
  "memory|agents.memory.main:app|8007"
  "reasoning|agents.reasoning.main:app|8008"
  "newsreader|agents.newsreader.main:app|8009"
  "db_worker|agents.db_worker.worker:app|8010"
  "analytics|agents.analytics.main:app|8011"
  "archive|agents.archive.main:app|8012"
  "dashboard|agents.dashboard.main:app|8013"
  "gpu_orchestrator|agents.gpu_orchestrator.main:app|8014"
  "crawler|agents.crawler.main:app|8015"
  "crawler_control|agents.crawler_control.main:app|8016"
  "archive_graphql|agents.archive.archive_graphql:app|8020"
  "archive_api|agents.archive.archive_api:app|8021"

)

export AGENTS_MANIFEST

## Infrastructure ports (single source of truth for infra services)
# Format per-entry: name|service_description|port
# This is intentionally an independent list so tooling can read infra services
# from the same place as the agents, and scripts can source this manifest for
# extra checks without impacting agent functionality.
INFRA_MANIFEST=(
  "grafana|Grafana UI|3000"
  "prometheus|Prometheus|9090"
  "node_exporter|Node Exporter|9100"
  "dcgm_exporter|DCGM Exporter|9400"
  "mariadb|MariaDB|3306"
  "chromadb|ChromaDB|3307"
  "crawl4ai|Crawl4AI|3308"
)

# Also export single variables for convenience in scripts that prefer env vars
GRAFANA_PORT=3000
PROMETHEUS_PORT=9090
NODE_EXPORTER_PORT=9100
DCGM_EXPORTER_PORT=9400
MARIADB_PORT=3306
CHROMADB_PORT=3307
CRAWL4AI_PORT=3308

export INFRA_MANIFEST
export GRAFANA_PORT PROMETHEUS_PORT NODE_EXPORTER_PORT DCGM_EXPORTER_PORT MARIADB_PORT CHROMADB_PORT CRAWL4AI_PORT
