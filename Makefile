.PHONY: dev backend frontend test migrate seed build

backend:
	cd backend && PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm run dev

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals, or use docker compose up --build"

test:
	cd backend && pytest -q

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && PYTHONPATH=. python -m scripts.seed

build:
	cd frontend && npm run build
