variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "service_name" {
  type    = string
  default = "retail-adk-agents"
}

variable "image" {
  description = "Full image reference, e.g. us-central1-docker.pkg.dev/<p>/retail-agents/retail-adk-agents:<sha>. Set by CD."
  type        = string
}

variable "runtime_service_account" {
  description = "Email of the runtime SA created by infra/bootstrap."
  type        = string
}

variable "app_env" {
  type    = string
  default = "prod"
}

variable "root_model" {
  type    = string
  default = "openrouter/meta-llama/llama-3.3-70b-instruct"
}

variable "specialist_model" {
  type    = string
  default = "openrouter/mistralai/mistral-nemo"
}

variable "openrouter_secret_id" {
  type    = string
  default = "openrouter-api-key"
}

variable "app_api_key_secret_id" {
  description = "Secret holding the X-API-Key value. Set to \"\" to run without API-key auth."
  type        = string
  default     = ""
}

variable "allow_unauthenticated" {
  description = "Grant roles/run.invoker to allUsers so the UI is reachable from a browser."
  type        = bool
  default     = true
}

# SQLite lives on the container's in-memory disk, so it is per-instance. Keep one
# instance (plus session affinity) while you use SQLite; raise this only after
# pointing SESSION_DB_URL at Cloud SQL / Postgres.
variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 1
}

variable "concurrency" {
  description = "Concurrent requests per instance. Agent calls are I/O bound, so this can be high."
  type        = number
  default     = 40
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "1Gi"
}

variable "session_db_url" {
  description = "ADK session DB. Default is container-local SQLite."
  type        = string
  default     = "sqlite+aiosqlite:////tmp/data/sessions.db"
}
