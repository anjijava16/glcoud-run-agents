# Copy these into GitHub (Settings -> Secrets and variables -> Actions -> Variables).
output "GCP_PROJECT_ID" {
  value = var.project_id
}

output "GCP_REGION" {
  value = var.region
}

output "GCP_WIF_PROVIDER" {
  description = "Full resource name of the WIF provider."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "GCP_DEPLOYER_SA" {
  value = google_service_account.deployer.email
}

output "GCP_RUNTIME_SA" {
  value = google_service_account.runtime.email
}

output "TF_STATE_BUCKET" {
  value = google_storage_bucket.tf_state.name
}

output "GAR_REPOSITORY" {
  value = google_artifact_registry_repository.docker.repository_id
}

output "image_base" {
  description = "Images are pushed here by CD."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}/${var.service_name}"
}

output "next_steps" {
  value = <<-EOT
    1) Add the OpenRouter key:
       printf '%s' "$OPENROUTER_API_KEY" | gcloud secrets versions add openrouter-api-key --data-file=- --project ${var.project_id}
    2) Add an app API key (or any random string if you'll leave auth off):
       openssl rand -hex 24 | tr -d '\n' | gcloud secrets versions add retail-app-api-key --data-file=- --project ${var.project_id}
    3) Put the outputs above into GitHub repository variables, then push to ${var.github_branch}.
  EOT
}
