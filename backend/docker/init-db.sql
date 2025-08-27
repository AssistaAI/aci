-- Initialize database for triggers module
-- This file is executed automatically when the PostgreSQL container starts

-- Create the main database (already created by POSTGRES_DB env var)
-- CREATE DATABASE aci_triggers;

-- Connect to the triggers database
\c aci_triggers;

-- Create the pgvector extension if needed (for compatibility with main ACI schema)
-- Note: This might not be available in all PostgreSQL images
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Create the webhook provider enum type
CREATE TYPE webhookprovider AS ENUM ('slack', 'hubspot', 'gmail');

-- Create the incoming_events table
CREATE TABLE IF NOT EXISTS incoming_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider webhookprovider NOT NULL,
    event_id TEXT NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    signature_valid BOOLEAN DEFAULT FALSE NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE NOT NULL,
    CONSTRAINT uq_incoming_events_provider_event_id UNIQUE (provider, event_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_incoming_events_provider_processed 
ON incoming_events (provider, processed);

CREATE INDEX IF NOT EXISTS ix_incoming_events_received_at 
ON incoming_events (received_at);

-- Create a user for the application (optional, for better security)
-- In production, you would create a specific user with limited privileges
-- CREATE USER triggers_app WITH PASSWORD 'triggers_app_password';
-- GRANT CONNECT ON DATABASE aci_triggers TO triggers_app;
-- GRANT USAGE ON SCHEMA public TO triggers_app;
-- GRANT ALL PRIVILEGES ON TABLE incoming_events TO triggers_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO triggers_app;