output "service_url" {
  value = google_cloud_run_v2_service.app.uri
}

output "latest_revision" {
  value = google_cloud_run_v2_service.app.latest_ready_revision
}

output "image" {
  value = var.image
}
