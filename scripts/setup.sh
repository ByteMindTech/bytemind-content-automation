#!/usr/bin/env bash
# Setup local development environment
set -euo pipefail

echo "▶ ByteMind Content Automation — Dev Setup"

# Check Python
python3 --version | grep -E "3\.(12|13)" || {
  echo "❌ Python 3.12+ required"
  exit 1
}

# Create venv if not exists
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "✓ Created .venv"
fi

source .venv/bin/activate
echo "✓ Activated .venv"

# Install dependencies
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet
echo "✓ Dependencies installed"

# Copy .env if not exists
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "✓ Created .env from .env.example — fill in your API keys!"
else
  echo "✓ .env already exists"
fi

# Install pre-commit hooks
if command -v pre-commit &>/dev/null; then
  pre-commit install
  echo "✓ pre-commit hooks installed"
fi

echo ""
echo "✅ Setup complete. Next steps:"
echo "   1. Edit .env with your API keys"
echo "   2. docker compose -f docker-compose.dev.yml up --build"
echo "   3. Visit http://localhost:8000/docs"
