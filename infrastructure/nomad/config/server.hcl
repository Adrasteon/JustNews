# Nomad Server Configuration
# This configuration is for Nomad servers in the cluster

datacenter = "dc1"
data_dir = "/opt/nomad/data"
bind_addr = "0.0.0.0"

# Enable server mode
server {
  enabled = true
  bootstrap_expect = 3  # Number of server nodes

  # Server to server communication
  server_join {
    retry_join = ["nomad-server-01", "nomad-server-02", "nomad-server-03"]
    retry_max = 3
    retry_interval = "15s"
  }
}

# Consul integration for service discovery
consul {
  address = "127.0.0.1:8500"

  # Auto-register Nomad services/tasks with Consul
  auto_advertise = true

  # Use Consul for service discovery
  server_service_name = "nomad"
  client_service_name = "nomad-client"

  # Enable Consul Connect (optional)
  connect {
    enabled = false
  }
}

# TLS configuration (recommended for production)
# tls {
#   http = true
#   rpc = true
#   ca_file = "/opt/nomad/tls/ca.pem"
#   cert_file = "/opt/nomad/tls/server.pem"
#   key_file = "/opt/nomad/tls/server-key.pem"
#   verify_server_hostname = true
# }

# ACL configuration (recommended for production)
# acl {
#   enabled = true
#   token_ttl = "30s"
#   policy_ttl = "60s"
#   replication_token = "your-replication-token"
# }

# Telemetry for monitoring
telemetry {
  collection_interval = "1s"
  disable_hostname = false
  prometheus_metrics = true
  publish_allocation_metrics = true
  publish_node_metrics = true
}

# Limits
limits {
  http_max_conns_per_client = 100
  rpc_max_conns_per_client = 100
}

# Logging
log_level = "INFO"
log_json = true

# Plugin directory
plugin_dir = "/opt/nomad/plugins"