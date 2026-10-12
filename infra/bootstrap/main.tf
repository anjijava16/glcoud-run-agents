locals {
  apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
  ]
}

data "google_project" "this" {
  project_id = var.project_id
}

# ---------------------------------------------------------------- APIs
resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- Terraform state bucket (used by infra/cloudrun)
resource "google_storage_bucket" "tf_state" {
  name                        = "${var.project_id}-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 20
    }
    action {
      type = "Delete"
    }
  }
}

# ---------------------------------------------------------------- Artifact Registry
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = var.artifact_repo_id
  description   = "Container images for ${var.service_name}"
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 15
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------- Secrets (containers only — values are added with gcloud so they never sit in tf state)
resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "openrouter-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "app_api_key" {
  secret_id = "retail-app-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------- Runtime identity (what the Cloud Run container runs as)
resource "google_service_account" "runtime" {
  account_id   = "${substr(var.service_name, 0, 20)}-run"
  display_name = "Cloud Run runtime SA for ${var.service_name}"
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_openrouter" {
  secret_id = google_secret_manager_secret.openrouter_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_app_key" {
  secret_id = google_secret_manager_secret.app_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# ---------------------------------------------------------------- Deployer identity (what GitHub Actions impersonates)
resource "google_service_account" "deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions deployer for ${var.service_name}"
}

resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/run.admin",               # create/update the Cloud Run service + its IAM
    "roles/artifactregistry.writer", # push images
    "roles/secretmanager.viewer",    # read secret metadata during plan
    "roles/serviceusage.serviceUsageConsumer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Deployer must be allowed to "act as" the runtime SA to attach it to the service.
resource "google_service_account_iam_member" "deployer_actas_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Read/write Terraform state.
resource "google_storage_bucket_iam_member" "deployer_state" {
  bucket = google_storage_bucket.tf_state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

# ---------------------------------------------------------------- Workload Identity Federation (keyless GitHub -> GCP auth)
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.actor"      = "assertion.actor"
  }

  # Hard gate: tokens from any other repo or branch are rejected before IAM is even checked.
  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.ref == \"refs/heads/${var.github_branch}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Only this repo, and only the deploy branch, can become the deployer SA.
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
