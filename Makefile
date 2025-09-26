SHELL := /bin/zsh

.PHONY: up down restart logs ps rebuild clean health metrics

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

