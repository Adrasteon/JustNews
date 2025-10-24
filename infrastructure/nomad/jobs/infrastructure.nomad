job "justnews-infrastructure" {
  datacenters = ["dc1"]
  type = "service"

  group "database" {
    count = 1

    network {
      port "postgres" {
        to = 5432
      }
    }

    service {
      name = "postgres"
      port = "postgres"

      check {
        type     = "tcp"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "postgres" {
      driver = "docker"

      config {
        image = "postgres:15-alpine"
        ports = ["postgres"]

        volumes = [
          "/opt/nomad/data/postgres:/var/lib/postgresql/data"
        ]
      }

      env {
        POSTGRES_DB = "justnews"
        POSTGRES_USER = "justnews"
        POSTGRES_PASSWORD = "change_me_secure_postgres_password"
      }

      resources {
        cpu    = 500
        memory = 1024
      }
    }
  }

  group "cache" {
    count = 1

    network {
      port "redis" {
        to = 6379
      }
    }

    service {
      name = "redis"
      port = "redis"

      check {
        type     = "tcp"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "redis" {
      driver = "docker"

      config {
        image = "redis:7-alpine"
        ports = ["redis"]

        volumes = [
          "/opt/nomad/data/redis:/data"
        ]
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  group "monitoring" {
    count = 1

    network {
      port "prometheus" {
        to = 9090
      }

      port "grafana" {
        to = 3000
      }
    }

    service {
      name = "prometheus"
      port = "prometheus"

      check {
        type     = "http"
        path     = "/-/healthy"
        interval = "30s"
        timeout  = "2s"
      }
    }

    service {
      name = "grafana"
      port = "grafana"

      check {
        type     = "http"
        path     = "/api/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "prometheus" {
      driver = "docker"

      config {
        image = "prom/prometheus:latest"
        ports = ["prometheus"]

        volumes = [
          "local/prometheus.yml:/etc/prometheus/prometheus.yml:ro",
          "/opt/nomad/data/prometheus:/prometheus"
        ]

        args = [
          "--config.file=/etc/prometheus/prometheus.yml",
          "--storage.tsdb.path=/prometheus",
          "--web.console.libraries=/etc/prometheus/console_libraries",
          "--web.console.templates=/etc/prometheus/consoles",
          "--storage.tsdb.retention.time=200h",
          "--web.enable-lifecycle"
        ]
      }

      template {
        data = <<EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'nomad-metrics'
    consul_sd_configs:
      - server: '{{ env "NOMAD_IP_prometheus" }}:8500'
    relabel_configs:
      - source_labels: ['__meta_consul_tags']
        regex: '(.*)http(.*)'
        action: keep

  - job_name: 'nomad'
    metrics_path: '/v1/metrics'
    params:
      format: ['prometheus']
    consul_sd_configs:
      - server: '{{ env "NOMAD_IP_prometheus" }}:8500'
        services: ['nomad']
    relabel_configs:
      - source_labels: ['__address__']
        regex: '(.*):(.*)'
        replacement: '${1}:4646'
        target_label: '__address__'

  - job_name: 'consul'
    metrics_path: '/v1/agent/metrics'
    params:
      format: ['prometheus']
    consul_sd_configs:
      - server: '{{ env "NOMAD_IP_prometheus" }}:8500'
        services: ['consul']
    relabel_configs:
      - source_labels: ['__address__']
        regex: '(.*):(.*)'
        replacement: '${1}:8500'
        target_label: '__address__'
EOF

        destination = "local/prometheus.yml"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }

    task "grafana" {
      driver = "docker"

      config {
        image = "grafana/grafana:latest"
        ports = ["grafana"]

        volumes = [
          "/opt/nomad/data/grafana:/var/lib/grafana"
        ]
      }

      env {
        GF_SECURITY_ADMIN_USER = "admin"
        GF_SECURITY_ADMIN_PASSWORD = "change_me_secure_grafana_password"
        GF_USERS_ALLOW_SIGN_UP = "false"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }
}