# Systemd Monitoring Stack

This guide explains how to install and operate the JustNews monitoring stack (Prometheus, Grafana, and node_exporter) when running the platform with native systemd services.

## Components

| Component       | Purpose                                               | Service name                     |
|-----------------|--------------------------------------------------------|----------------------------------|
| node_exporter   | Exposes host metrics and textfile collectors           | `justnews-node-exporter.service` |
| Prometheus      | Scrapes agent endpoints and textfile collectors        | `justnews-prometheus.service`    |
| Grafana         | Renders dashboards and surfaces alerts (if enabled)    | `justnews-grafana.service`       |

Dashboards are provisioned automatically from `monitoring/dashboards/generated/` and appear in Grafana after installation.

## Prerequisites

- `justnews` system user (created during systemd setup)
- Internet access to download official release archives
- `curl` and `tar` installed on the host

## First-time installation

Run the installer script as root:

```bash
sudo ./infrastructure/systemd/scripts/install_monitoring_stack.sh \
  --install-binaries \
  --enable \
  --start
```

This performs the following actions:

1. Downloads Prometheus, Grafana, and node_exporter into `/opt/justnews/monitoring`
2. Creates `/etc/justnews/monitoring.env` (with sensible defaults)
3. Copies Prometheus/Grafana configs and dashboards to `/etc/justnews/monitoring/`
4. Installs systemd units under `/etc/systemd/system/`
5. Enables and starts `justnews-node-exporter`, `justnews-prometheus`, and `justnews-grafana`

> **Note:** If binaries already exist, omit `--install-binaries`. Use `--force` to overwrite config files with timestamped backups.

## Configuration

All runtime settings live in `/etc/justnews/monitoring.env`. Key entries include:

```ini
PROMETHEUS_BIN=/opt/justnews/monitoring/prometheus/prometheus
PROMETHEUS_CONFIG_FILE=/etc/justnews/monitoring/prometheus.yml
PROMETHEUS_DATA_DIR=/var/lib/justnews/prometheus
GF_SERVER_HTTP_PORT=3000
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=change_me
NODE_EXPORTER_TEXTFILE_DIR=/var/lib/node_exporter/textfile_collector
```

After editing the file, reload services:

```bash
sudo systemctl restart justnews-node-exporter.service
sudo systemctl restart justnews-prometheus.service
sudo systemctl restart justnews-grafana.service
```

## Dashboards

Dashboards are placed under `/etc/justnews/monitoring/grafana/dashboards/` and are automatically picked up by Grafana. The generated bundle currently includes:

- **System Overview** – Agent health, request volume, scheduler status
- **Agent Performance** – Per-agent latency, error rates, queue depth
- **Business Metrics** – Article throughput, fact-check counts, synthesis output

To add custom dashboards, drop JSON exports into the same directory and restart Grafana.

## Verification

1. Confirm services are active:
   ```bash
   systemctl status justnews-node-exporter.service justnews-prometheus.service justnews-grafana.service
   ```
2. Check Prometheus targets at `http://localhost:9090/targets`
3. Log into Grafana at `http://localhost:3000/` (change the default password immediately)
4. Validate crawl scheduler metrics appear under **JustNews System Overview → Scheduler**

## Maintenance

- **Upgrade binaries:** re-run the installer with `--install-binaries --force` to download newer versions. Adjust `--prometheus-version`, `--grafana-version`, or `--node-exporter-version` if needed.
- **Rotate data:** adjust `PROMETHEUS_RETENTION` in `monitoring.env` to control TSDB retention (default: 30 days).
- **Backups:** include `/var/lib/justnews/prometheus` and `/var/lib/justnews/grafana` in your backup plan.
- **Textfile metrics:** scheduler metrics are exported to `/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom`. Additional custom exporters can drop Prometheus-formatted files into this directory.

## Troubleshooting

| Symptom                                      | Resolution |
|---------------------------------------------|------------|
| Services fail with exit code 127            | Binaries missing/not executable. Re-run installer with `--install-binaries` or update paths in `monitoring.env` |
| Grafana shows provisioning errors           | Ensure files under `/etc/justnews/monitoring/grafana/provisioning` are readable by the `justnews` user |
| Prometheus target down for an agent         | Check the agent’s `/metrics` endpoint and confirm it is running (`systemctl status justnews@<agent>`) |
| node_exporter permission denied on textfile | Verify `/var/lib/node_exporter/textfile_collector` owner is `justnews:justnews` and mode `0775` |

For full context, see `infrastructure/systemd/README.md` and `infrastructure/systemd/QUICK_REFERENCE.md`.
