# Nomad Client Configuration
# This configuration is for Nomad client nodes that run workloads

datacenter = "dc1"
data_dir = "/opt/nomad/data"
bind_addr = "0.0.0.0"

# Enable client mode
client {
  enabled = true

  # Server addresses for joining the cluster
  servers = ["nomad-server-01:4647", "nomad-server-02:4647", "nomad-server-03:4647"]

  # Node class for GPU nodes
  node_class = "cpu-worker"  # Override to "gpu-worker" on GPU nodes

  # Meta attributes for scheduling
  meta {
    "node_type" = "worker"
    "gpu_enabled" = "false"  # Set to "true" on GPU nodes
  }

  # Host volumes for persistent data
  host_volume "postgres_data" {
    path = "/opt/nomad/data/postgres"
    read_only = false
  }

  host_volume "redis_data" {
    path = "/opt/nomad/data/redis"
    read_only = false
  }

  host_volume "grafana_data" {
    path = "/opt/nomad/data/grafana"
    read_only = false
  }

  host_volume "prometheus_data" {
    path = "/opt/nomad/data/prometheus"
    read_only = false
  }
}

# Consul integration
consul {
  address = "127.0.0.1:8500"
  auto_advertise = true
  client_service_name = "nomad-client"
}

# Docker driver configuration
plugin "docker" {
  config {
    # Allow privileged containers (required for GPU access)
    allow_privileged = true

    # GPU configuration
    volumes {
      enabled = true
    }

    # NVIDIA runtime for GPU support
    extra_labels = ["job_name", "task_group_name", "task_name", "node_name"]

    # Docker daemon configuration
    docker_api_version = "1.40"
  }
}

# Raw exec driver (for system tasks)
plugin "raw_exec" {
  config {
    enabled = true
  }
}

# Telemetry
telemetry {
  collection_interval = "1s"
  disable_hostname = false
  prometheus_metrics = true
  publish_allocation_metrics = true
  publish_node_metrics = true
}

# Logging
log_level = "INFO"
log_json = true