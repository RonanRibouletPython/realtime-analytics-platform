#!/bin/bash

# Configuration
CONTAINER_NAME="realtime-analytics-platform_devcontainer-db-1"
DB_USER="analytics"
DB_NAME="analytics"

# Uselful commands
echo "------------------------------------------------"
echo "Useful commands:"
echo "  \dt       -> List all tables"
echo "  \d metrics -> Show table structure"
echo "  select * from metrics order by timestamp desc limit 5; -> See latest data"
echo "  \q        -> Quit"
echo "------------------------------------------------"

docker exec -it "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME"