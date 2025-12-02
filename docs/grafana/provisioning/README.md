Grafana provisioning (docs)
---------------------------------

This folder contains example Grafana provisioning files that can be used to auto-provision
dashboards and datasources in a Grafana instance. These are documentation examples and must
be wired into your Grafana container or server (for example by copying them into /etc/grafana/provisioning/)

How to use
1. Copy `datasources.yml` to Grafana `/etc/grafana/provisioning/datasources/` and adjust Prometheus URL.
2. Copy `dashboards.yml` to `/etc/grafana/provisioning/dashboards/` and copy the `dashboards/` folder contents to the configured path.
3. Restart Grafana or reload provisioning to pick up the new dashboards & datasources.
