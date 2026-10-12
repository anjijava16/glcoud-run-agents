.PHONY: install run test lint fmt docker-build docker-run dockerhub-push tf-fmt tf-validate

# Docker Hub repo for manual pushes:  make dockerhub-push DOCKERHUB_REPO=anjaiahspr/retail-adk-agents
DOCKERHUB_REPO ?= anjaiahspr/retail-adk-agents
TAG ?= $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo local)

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --port 8080

test:
	pytest -q

lint:
	ruff check app tests && ruff format --check app tests

fmt:
	ruff format app tests && ruff check --fix app tests

docker-build:
	docker build -t retail-adk-agents:local .

docker-run:
	docker run --rm -p 8080:8080 --env-file .env retail-adk-agents:local

# Build for linux/amd64 (what Cloud Run runs, also correct from an Apple Silicon Mac) and push.
# Run `docker login -u anjaiahspr` once first.
dockerhub-push:
	docker buildx build --platform linux/amd64 \
		-t $(DOCKERHUB_REPO):$(TAG) -t $(DOCKERHUB_REPO):latest --push .

tf-fmt:
	terraform -chdir=infra/bootstrap fmt && terraform -chdir=infra/cloudrun fmt

tf-validate:
	terraform -chdir=infra/bootstrap init -backend=false && terraform -chdir=infra/bootstrap validate
	terraform -chdir=infra/cloudrun init -backend=false && terraform -chdir=infra/cloudrun validate
