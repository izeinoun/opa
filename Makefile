.PHONY: setup seed dev verify test clean

# ── Setup ──────────────────────────────────────────────────────────────────────
setup:
	@echo "==> Installing Python dependencies..."
	pip install -r server/requirements.txt
	@echo "==> Installing Node dependencies..."
	cd client && npm install
	@echo "==> Running DB migrations..."
	cd server && alembic upgrade head
	@echo "==> Setup complete."

# ── Seed ───────────────────────────────────────────────────────────────────────
seed:
	@echo "==> Seeding database..."
	cd server && python -m seed.seed_all
	@echo "==> Seeding complete."

# ── Dev ────────────────────────────────────────────────────────────────────────
dev:
	@echo "==> Starting OPA (backend + frontend)..."
	@(cd server && uvicorn app.main:app --reload --reload-exclude "ml_models/*" --reload-exclude "*.db" --port 8001) &
	@(cd client && npm run dev) &
	@echo "==> Backend:  http://localhost:8001"
	@echo "==> Frontend: http://localhost:5174"
	@wait

# ── Individual servers ────────────────────────────────────────────────────────
backend:
	cd server && uvicorn app.main:app --reload --port 8001

frontend:
	cd client && npm run dev

# ── Verify ─────────────────────────────────────────────────────────────────────
verify:
	@echo "==> Verifying environment..."
	cd server && python verify_env.py

# ── Test ───────────────────────────────────────────────────────────────────────
test:
	@echo "==> Running tests..."
	cd server && pytest tests/ -v

# ── Health check ───────────────────────────────────────────────────────────────
health:
	curl -s http://localhost:8001/health | python -m json.tool

# ── Clean ──────────────────────────────────────────────────────────────────────
clean:
	rm -f server/opa.db
	rm -rf server/ml_models/
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
