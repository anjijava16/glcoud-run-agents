variable "project_id" {
  description = "GCP project ID to deploy into."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "GitHub repo allowed to deploy, as owner/name (e.g. anjijava16/retail-adk-agents)."
  type        = string
}

variable "github_branch" {
  description = "Only workflows running on this branch can impersonate the deployer."
  type        = string
  default     = "main"
}

variable "service_name" {
  description = "Cloud Run service name (also used to name related resources)."
  type        = string
  default     = "retail-adk-agents"
}

variable "artifact_repo_id" {
  description = "Artifact Registry Docker repository id."
  type        = string
  default     = "retail-agents"
}
