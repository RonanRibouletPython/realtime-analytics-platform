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

# Verify Kafka connection
echo "Checking Kafka..."
until python -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('localhost', 9092))" > /dev/null 2>&1; do
  echo "Waiting for Kafka at localhost:9092..."
  sleep 2
done
echo "Kafka is ready!"

echo ""
echo "DevContainer setup complete!"
echo ""
echo "Next steps:"
echo "  1. cd services/ingestion"
echo "  2. uv sync --dev"
echo "  3. uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""