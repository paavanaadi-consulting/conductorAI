.PHONY: install test lint type-check format clean docker-build help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package with dev dependencies
	pip install -e ".[dev]"

test: ## Run tests with coverage
	pytest --cov=conductor -q

test-unit: ## Run unit tests only
	pytest -m unit -q

test-integration: ## Run integration tests only
	pytest -m integration -q

lint: ## Run linter
	ruff check src/ tests/

type-check: ## Run type checker
	mypy src/conductor/

format: ## Format code
	ruff format src/ tests/
	ruff check --fix src/ tests/

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

docker-build: ## Build Docker image
	docker build -t conductorai:latest .

docker-run: ## Run Docker container
	docker run --rm -it conductorai:latest
