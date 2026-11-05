# One-command workflows. `make` lists them.
.DEFAULT_GOAL := help
VENV := backend/.venv

.PHONY: help install dev start check clean image demo release

help: ## List commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -e "backend[dev]"
	cd frontend && bun install

dev: ## Run API (:8000) and web app with hot reload (:5173)
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && PULSE_CORS_ORIGINS=$${PULSE_CORS_ORIGINS:-'["http://localhost:5173"]'} \
		.venv/bin/pulse serve --reload) & \
	(cd frontend && bun run dev) & \
	wait

start: ## Build the web app and serve everything from one process (:8000)
	cd frontend && bun run build
	cd backend && PULSE_STATIC_DIR=../frontend/dist .venv/bin/pulse serve --host 0.0.0.0

check: ## Lint, type-check and test both packages
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src && .venv/bin/pytest -q
	cd frontend && bun run lint && bun run typecheck && bun run test

image: ## Build the Docker image (pulse:local)
	docker build -t pulse:local .

demo: image ## Run the image with a simulated cluster on http://localhost:8000
	docker run --rm -p 8000:8000 -e PULSE_SLURM_BACKEND=mock pulse:local

release: ## Publish VERSION=x.y.z from this machine (image, tag, GitHub release)
	@scripts/release.sh "$(VERSION)" "$(NOTES)"

clean: ## Remove build output and local data
	rm -rf frontend/dist backend/data
