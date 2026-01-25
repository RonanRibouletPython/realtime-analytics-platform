#!/bin/bash

# This script runs after the devcontainer is created

echo "Setting up development environment..."

# Verify Python installation
echo "Python version:"
python --version

# Verify uv installation
echo "uv version:"
uv --version

# Verify database connection
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h localhost -p 5432 -U analytics; do
  echo "Waiting for postgres..."
  sleep 2
done
echo "PostgreSQL is ready!"

# Verify Redis connection
echo "Checking Redis..."
until redis-cli ping; do
  echo "Waiting for Redis..."
  sleep 2
done
echo "Redis is ready!"

# Set git config (optional, customize with your info)
git config --global core.autocrlf input
git config --global init.defaultBranch main

echo ""
echo "DevContainer setup complete!"
echo ""
echo "Next steps:"
echo "  1. cd services/ingestion"
echo "  2. uv sync --dev"
echo "  3. uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""