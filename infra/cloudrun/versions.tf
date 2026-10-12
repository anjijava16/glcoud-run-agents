terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }

  # Partial config: the bucket is passed at init time
  #   terraform init -backend-config="bucket=<project>-tfstate"
  backend "gcs" {
    prefix = "retail-adk-agents/cloudrun"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
