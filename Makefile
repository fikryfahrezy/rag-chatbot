.PHONY: install dev backend frontend test

install:
	cd backend && uv sync --python 3.13.15 --frozen
	cd frontend && npm ci

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals"

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest
	cd frontend && npm run type-check
