-- Enable TimescaleDB extension (Required for the timescaledb image)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create Schema
CREATE SCHEMA IF NOT EXISTS analytics_schema;

-- Log success
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully with TimescaleDB';
END $$;