.PHONY: up down build test lint format migrate makemigrations seed schema api-client logs timers

COMPOSE = docker compose
BACKEND = $(COMPOSE) run --rm backend

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

migrate:
	$(BACKEND) python manage.py migrate

makemigrations:
	$(BACKEND) python manage.py makemigrations

seed:
	$(BACKEND) python manage.py seed

test:
	$(BACKEND) pytest
	$(COMPOSE) run --rm frontend npm run test

lint:
	$(BACKEND) sh -c "ruff check . && ruff format --check . && mypy"
	$(COMPOSE) run --rm frontend sh -c "npm run lint && npm run format:check && npm run typecheck"

format:
	$(BACKEND) sh -c "ruff check --fix . && ruff format ."
	$(COMPOSE) run --rm frontend npm run format

# Export OpenAPI schema and regenerate the typed frontend client.
schema:
	$(BACKEND) python manage.py spectacular --file schema.yml --validate
	$(COMPOSE) run --rm frontend npm run gen:api

logs:
	$(COMPOSE) logs -f

# Periodic jobs (no-show timer, waiting calls, pending SMS) without Celery beat: local development.
timers:
	$(BACKEND) python manage.py run_timers
