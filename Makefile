.PHONY: up down logs migrate test lint format

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:
	docker compose run --rm api alembic -c backend/alembic.ini upgrade head

test:
	pytest

lint:
	ruff check backend

format:
	ruff format backend

