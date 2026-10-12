resource "google_cloud_run_v2_service" "app" {
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = var.runtime_service_account
    timeout                          = "300s" # long enough for multi-step agent turns + streaming
    max_instance_request_concurrency = var.concurrency
    session_affinity                 = true # keep a browser on the same instance (matters with SQLite)

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    labels = {
      app = var.service_name
      env = var.app_env
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "APP_ENV"
        value = var.app_env
      }
      env {
        name  = "LOG_JSON"
        value = "true"
      }
      env {
        name  = "ROOT_MODEL"
        value = var.root_model
      }
      env {
        name  = "SPECIALIST_MODEL"
        value = var.specialist_model
      }
      env {
        name  = "SESSION_DB_URL"
        value = var.session_db_url
      }
      env {
        name  = "RETAIL_DB_PATH"
        value = "/tmp/data/retail.db"
      }

      env {
        name = "OPENROUTER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.openrouter_secret_id
            version = "latest"
          }
        }
      }

      dynamic "env" {
        for_each = var.app_api_key_secret_id == "" ? [] : [var.app_api_key_secret_id]
        content {
          name = "APP_API_KEY"
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 2
        period_seconds        = 3
        timeout_seconds       = 2
        failure_threshold     = 20
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds    = 30
        timeout_seconds   = 3
        failure_threshold = 3
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.allow_unauthenticated ? 1 : 0
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
