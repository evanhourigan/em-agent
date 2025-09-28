SHELL := /bin/zsh

.PHONY: up down restart logs ps rebuild clean health metrics dbt.debug dbt.run seed.events seed.reset purge.events

up:
	docker-compose up -d --build db gateway

down:
	docker-compose down -v

restart:
	$(MAKE) down && $(MAKE) up

logs:
	docker-compose logs -f --tail=200 gateway db

ps:
	docker-compose ps

rebuild:
	docker-compose build --no-cache gateway

health:
	@until curl -sf http://localhost:8000/health >/dev/null; do echo "waiting for gateway..."; sleep 1; done; echo READY && curl -sS http://localhost:8000/health

metrics:
	curl -sS http://localhost:8000/metrics | head -50

clean:
	git clean -xdf -e .venv

# --- Migrations (gateway) ---
.PHONY: mig.up mig.revision mig.history

mig.up:
	docker-compose exec -T gateway alembic -c /app/alembic.ini upgrade head

mig.revision:
	@read -p "Message: " MSG; \
	docker-compose exec -T gateway alembic -c /app/alembic.ini revision -m "$$MSG"

mig.history:
	docker-compose exec -T gateway alembic -c /app/alembic.ini history | tail -50

# --- Metrics / dbt ---
DBT := DBT_PROFILES_DIR=$(PWD)/services/metrics dbt

.dbt.ensure:
	@command -v dbt >/dev/null 2>&1 || pipx install dbt-postgres >/dev/null 2>&1 || pip install dbt-postgres >/dev/null 2>&1

.PHONY: dbt.debug dbt.run

dbt.debug: .dbt.ensure
	cd services/metrics && $(DBT) debug

dbt.run: .dbt.ensure
	cd services/metrics && $(DBT) run

# --- Demo data seeding ---
seed.events:
	python3 services/metrics/scripts/backfill_events.py

seed.reset:
	psql postgresql://postgres:postgres@localhost:5432/postgres -c "truncate table events_raw restart identity;"

purge.events:
	RETENTION_DAYS?=30; services/metrics/.venv/bin/python services/metrics/scripts/purge_old_events.py

