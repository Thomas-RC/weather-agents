.PHONY: up down logs ps clean infra admin smoke test fmt

# Core infra (Batch 1)
up:
	docker compose up -d qdrant minio mariadb

# All services (worker + app dodawane w późniejszych batchach)
up-all:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=200

# phpMyAdmin (profil admin) — http://localhost:8080
admin:
	docker compose --profile admin up -d phpmyadmin

clean:
	docker compose down -v
	rm -rf data/qdrant data/minio data/mariadb

# Smoke testy storage (po batch 2)
smoke:
	python -m scripts.smoke_storage

test:
	pytest -v

fmt:
	ruff check --fix src tests
	ruff format src tests
