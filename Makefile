PYTHON=python

.PHONY: demo
demo:
	@echo "Running reviewer demo (this will run evaluation, baseline, replay validation, comparison, adversarial summary, SSE demo)"
	$(PYTHON) scripts/run_evaluation.py --dataset data/evaluation_dataset.json --output results/ -v
	$(PYTHON) scripts/run_baseline.py --dataset data/evaluation_dataset.json --output results/
	$(PYTHON) scripts/validate_replays.py
	$(PYTHON) scripts/compare_baseline.py --baseline results/ --orchestrated results/ --out results/
	$(PYTHON) scripts/generate_adversarial_summary.py
	$(PYTHON) scripts/sse_demo.py
	@echo "Demo complete. See results/ for artifacts."
# Developer Makefile - convenience commands for local development

.PHONY: up down rebuild logs migrate lint format test

up:
	@echo "Starting services (detached)..."
	docker compose up -d --build

down:
	@echo "Stopping services..."
	docker compose down --volumes --remove-orphans

rebuild: down up
	@echo "Rebuilt and started services."

logs:
	@echo "Tailing logs (api). Press Ctrl-C to exit."
	docker compose logs -f api

migrate:
	@echo "Running alembic migrations (inside api container)."
	# Run migrations inside the api container to use the same environment
	docker compose run --rm api sh -c "alembic upgrade head"

lint:
	@echo "Lint (requires ruff installed locally)."
	ruff check .

format:
	@echo "Format (requires black and ruff)."
	black .
	ruff check --fix .

test:
	@echo "Run tests (uses pytest)."
	pytest -q
