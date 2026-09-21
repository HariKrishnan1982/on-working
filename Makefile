.PHONY: test test-audit lint up down clean build run-gateway

test:
	pytest tests/ -v --tb=short

test-audit:
	pytest tests/test_audit.py -v --tb=short

lint:
	python -m compileall -q .

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

run-gateway:
	uvicorn gateway.app:app --host 127.0.0.1 --port 8000 --reload

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
