# One-time foundation, applied by a human with Owner (or equivalent) on the project.
# Local state is fine here; it holds no secrets. Optionally migrate it into the
# bucket this stack creates (see README "Bootstrap").
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
