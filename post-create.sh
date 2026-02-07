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

# Verify Kafka UI connection
echo "Checking Kafka UI..."
until curl -s http://localhost:8080; do
  echo "Waiting for Kafka UI at http://localhost:8080..."
  sleep 2
done
echo "Kafka UI is ready!"

# Verify AVRO schema registry connection
echo "Checking Schema Registry..."
until curl -s http://localhost:8081; do
  echo "Waiting for Schema Registry at http://localhost:8081..."
  sleep 2
done
echo
echo "Schema Registry is ready!"

echo ""
echo "DevContainer setup complete!"
echo ""
echo "Next steps:"
echo "  1. cd services/ingestion"
echo "  2. uv sync --dev"
echo "  3. bash run.sh"
echo "  4. bash worker.sh"
echo ""