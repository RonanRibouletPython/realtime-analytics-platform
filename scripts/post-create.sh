#!/bin/bash

# This script runs after the devcontainer is created
set -euo pipefail
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

# Create Kafka topics
KAFKA_CONTAINER="realtime-analytics-platform_devcontainer-kafka-1"
KAFKA="docker exec -it $KAFKA_CONTAINER /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092"

echo "Creating Kafka topics..."

$KAFKA --create --if-not-exists --topic metrics_ingestion --partitions 3 --replication-factor 1
echo "✅ metrics_ingestion"

$KAFKA --create --if-not-exists --topic metrics_dlq --partitions 1 --replication-factor 1
echo "✅ metrics_dlq"

echo ""
echo "All topics:"
$KAFKA --list

echo ""
echo "DevContainer setup complete!"
echo ""