# ACI Triggers Module

The ACI Triggers module is an inbound webhook processing system that receives events from Slack, HubSpot, and Gmail (via Google Pub/Sub push), verifies their authenticity, normalizes payloads, stores them for idempotency and audit purposes, and enqueues jobs to call existing ACI actions.

## Architecture Overview

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│   Slack Events  │    │   HubSpot    │    │ Gmail Pub/Sub   │
│      API        │    │  Webhooks    │    │     Push        │
└─────────┬───────┘    └──────┬───────┘    └─────────┬───────┘
          │                   │                      │
          │ HMAC verify       │ v3 HMAC verify       │ OIDC JWT verify
          │                   │                      │
          └───────────────────┼──────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   FastAPI Routes  │
                    │   - /slack/events │
                    │   - /hubspot      │
                    │   - /gmail/pubsub │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Event Storage    │
                    │  (PostgreSQL)     │
                    │ - Deduplication   │
                    │ - Audit Trail     │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │ Event Normalization│
                    │ - Unified Schema   │
                    │ - Provider Mapping │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   RQ Job Queue    │
                    │     (Redis)       │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Background       │
                    │   Workers         │
                    │ - Process Events  │
                    │ - Call ACI Actions│
                    └───────────────────┘
```

## Features

- ✅ **Production-Grade Security**: Strict signature verification with replay protection
- ✅ **Idempotency Protection**: Automatic deduplication using provider event IDs
- ✅ **Event Normalization**: Unified schema across all webhook providers
- ✅ **Background Processing**: Async job processing with RQ/Redis
- ✅ **Comprehensive Logging**: Structured JSON logging for monitoring
- ✅ **Health Monitoring**: Health check endpoints and job monitoring
- ✅ **Docker Support**: Complete Docker Compose setup for local development

## Webhook Endpoints

All endpoints are prefixed with `/v1/webhooks/`:

### Slack Events API
- **Endpoint**: `POST /v1/webhooks/slack/events`
- **Authentication**: HMAC SHA256 signature verification
- **Headers**: 
  - `X-Slack-Signature`: HMAC signature (format: `v0=<signature>`)
  - `X-Slack-Request-Timestamp`: Unix timestamp
- **Features**:
  - URL verification challenge support
  - 5-minute replay protection
  - Message and channel event processing

### HubSpot Webhooks v3
- **Endpoint**: `POST /v1/webhooks/hubspot`
- **Authentication**: HubSpot v3 HMAC signature verification
- **Headers**:
  - `X-HubSpot-Signature-V3`: HMAC signature
  - `X-HubSpot-Request-Timestamp`: Millisecond timestamp
- **Features**:
  - Batched event processing
  - Contact, company, and deal events
  - Canonical string verification

### Gmail Pub/Sub Push
- **Endpoint**: `POST /v1/webhooks/gmail/pubsub`
- **Authentication**: OIDC JWT token verification
- **Headers**:
  - `Authorization`: `Bearer <jwt_token>`
- **Features**:
  - OIDC token validation (audience & issuer)
  - Base64 message decoding
  - History ID tracking

### Health Check
- **Endpoint**: `GET /v1/webhooks/health`
- **Response**: Service health status and queue statistics

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TRIGGERS_SLACK_SIGNING_SECRET` | Slack app signing secret | Yes | - |
| `TRIGGERS_HUBSPOT_APP_SECRET` | HubSpot app secret | Yes | - |
| `TRIGGERS_PUBSUB_OIDC_AUDIENCE` | Expected OIDC audience URL | Yes | - |
| `TRIGGERS_GOOGLE_ISSUER` | Google OIDC issuer | No | `https://accounts.google.com` |
| `TRIGGERS_REDIS_URL` | Redis connection URL | No | `redis://localhost:6379/0` |
| `TRIGGERS_DATABASE_URL` | PostgreSQL connection URL | Yes | - |
| `TRIGGERS_MAX_TIMESTAMP_AGE_SECONDS` | Replay protection window | No | `300` (5 minutes) |

## Local Development Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- uv package manager

### Quick Start

1. **Start the triggers module services:**
   ```bash
   make up-triggers
   ```

2. **Run database migrations:**
   ```bash
   make migrate-triggers
   ```

3. **Run tests:**
   ```bash
   make test-triggers
   ```

4. **View logs:**
   ```bash
   make logs-triggers
   ```

### Services Started

- **API Server**: http://localhost:8000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **RQ Workers**: Background job processors

### Optional: Start with monitoring dashboard

```bash
make dashboard-triggers
```

This starts an additional RQ Dashboard at http://localhost:9181 for monitoring job queues.

## Webhook Provider Setup

### Slack App Setup

1. Create a Slack app at https://api.slack.com/apps
2. Enable Event Subscriptions
3. Set Request URL: `https://yourdomain.com/v1/webhooks/slack/events`
4. Subscribe to bot events: `message.channels`, `channel_created`, etc.
5. Copy the Signing Secret and set `TRIGGERS_SLACK_SIGNING_SECRET`

**Sample curl test:**
```bash
# URL verification challenge
curl -X POST http://localhost:8000/v1/webhooks/slack/events \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test123"}'
```

### HubSpot App Setup

1. Create a HubSpot app at https://developers.hubspot.com/
2. Configure Webhooks v3
3. Set Webhook URL: `https://yourdomain.com/v1/webhooks/hubspot`
4. Subscribe to events: `contact.propertyChange`, `deal.creation`, etc.
5. Copy the Client Secret and set `TRIGGERS_HUBSPOT_APP_SECRET`

**Sample curl test:**
```bash
# Test with valid signature
curl -X POST http://localhost:8000/v1/webhooks/hubspot \
  -H "Content-Type: application/json" \
  -H "X-HubSpot-Signature-V3: <computed_signature>" \
  -H "X-HubSpot-Request-Timestamp: $(date +%s)000" \
  -d '[{"eventId": "test123", "subscriptionType": "contact.propertyChange", "objectId": "12345", "occurredAt": '$(date +%s)'000}]'
```

### Gmail Pub/Sub Setup

1. Create a Google Cloud Project
2. Enable Gmail API and Pub/Sub API
3. Create a Pub/Sub topic and push subscription
4. Set push endpoint: `https://yourdomain.com/v1/webhooks/gmail/pubsub`
5. Configure OIDC authentication with proper audience
6. Use Gmail API `watch` to enable push notifications

**Environment setup:**
```bash
export TRIGGERS_PUBSUB_OIDC_AUDIENCE="https://yourdomain.com/v1/webhooks/gmail/pubsub"
export TRIGGERS_GOOGLE_ISSUER="https://accounts.google.com"
```

## Local Testing with ngrok

For testing webhooks locally, use ngrok to expose your local server:

1. **Install ngrok:**
   ```bash
   # Download from https://ngrok.com/
   # Or via package manager:
   brew install ngrok  # macOS
   ```

2. **Start your local services:**
   ```bash
   make up-triggers
   ```

3. **Expose your local server:**
   ```bash
   ngrok http 8000
   ```

4. **Configure webhook URLs:**
   - Slack: `https://abc123.ngrok.io/v1/webhooks/slack/events`
   - HubSpot: `https://abc123.ngrok.io/v1/webhooks/hubspot`
   - Gmail: `https://abc123.ngrok.io/v1/webhooks/gmail/pubsub`

5. **Test the endpoints:**
   ```bash
   # Health check
   curl https://abc123.ngrok.io/v1/webhooks/health
   
   # Slack URL verification
   curl -X POST https://abc123.ngrok.io/v1/webhooks/slack/events \
     -H "Content-Type: application/json" \
     -d '{"type": "url_verification", "challenge": "test"}'
   ```

## Database Schema

### incoming_events Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `provider` | ENUM | Webhook provider (slack, hubspot, gmail) |
| `event_id` | TEXT | Provider-specific event ID |
| `received_at` | TIMESTAMPTZ | When event was received |
| `signature_valid` | BOOLEAN | Whether signature verification passed |
| `payload` | JSONB | Raw webhook payload |
| `processed` | BOOLEAN | Whether event was processed by worker |

**Constraints:**
- Unique constraint on `(provider, event_id)` for idempotency
- Indexes on `(provider, processed)` and `received_at`

## Event Normalization

All incoming events are normalized to a unified schema:

```python
@dataclass
class NormalizedEvent:
    provider: str      # "slack", "hubspot", "gmail"
    type: str         # "slack.message", "hubspot.contact.propertyChange", etc.
    subject_id: str   # Unique identifier for the event subject
    ts: datetime      # Event timestamp
    data: dict        # Provider-specific event data
```

### Normalization Examples

**Slack Message:**
- `type`: `"slack.message"`
- `subject_id`: `"C1234567890:U1234567890"` (channel:user)
- `data`: Channel ID, user ID, message text, etc.

**HubSpot Contact Change:**
- `type`: `"hubspot.contact.propertyChange"`
- `subject_id`: `"987654321"` (object ID)
- `data`: Property name, new value, portal ID, etc.

**Gmail History:**
- `type`: `"gmail.history"`
- `subject_id`: `"user@example.com"` (email address)
- `data`: History ID, email address, etc.

## Background Job Processing

Events are processed asynchronously using RQ (Redis Queue):

1. **Job Enqueueing**: Normalized events are queued for processing
2. **Worker Processing**: Background workers pick up jobs and process them
3. **ACI Integration**: Workers call appropriate ACI actions based on event type
4. **Error Handling**: Failed jobs are retried with exponential backoff
5. **Monitoring**: Job status and queue stats available via health endpoint

### Monitoring Jobs

- **Queue Stats**: `GET /v1/webhooks/health`
- **RQ Dashboard**: http://localhost:9181 (when started with `make dashboard-triggers`)
- **Manual Inspection**: Connect to Redis and inspect queues

## Testing

### Running Tests

```bash
# Run all triggers tests
make test-triggers

# Run specific test files
uv run pytest aci/triggers/tests/test_triggers_slack.py -v
uv run pytest aci/triggers/tests/test_triggers_hubspot.py -v
uv run pytest aci/triggers/tests/test_triggers_gmail.py -v
uv run pytest aci/triggers/tests/test_models.py -v
```

### Test Coverage

- ✅ Signature verification (valid/invalid/expired)
- ✅ Payload normalization
- ✅ Database idempotency constraints
- ✅ HTTP endpoint responses
- ✅ Error handling and edge cases
- ✅ Webhook payload fixtures

### Test Fixtures

Sample payloads are available in `aci/triggers/tests/fixtures/`:
- `slack_message_event.json`
- `slack_url_verification.json`
- `hubspot_contact_event.json`
- `hubspot_batched_events.json`
- `gmail_pubsub_envelope.json`
- `gmail_message_decoded.json`

## Production Deployment

### Security Considerations

1. **Secret Management**: Use secure secret management (AWS Secrets Manager, etc.)
2. **Network Security**: Deploy behind load balancer with WAF
3. **Rate Limiting**: Configure appropriate rate limits
4. **Monitoring**: Set up alerts for webhook failures
5. **Logging**: Ensure structured logging is properly configured

### Environment Setup

```bash
# Required production environment variables
export TRIGGERS_SLACK_SIGNING_SECRET="your_actual_slack_secret"
export TRIGGERS_HUBSPOT_APP_SECRET="your_actual_hubspot_secret"
export TRIGGERS_PUBSUB_OIDC_AUDIENCE="https://yourproductiondomain.com/v1/webhooks/gmail/pubsub"
export TRIGGERS_DATABASE_URL="postgresql://user:pass@host:5432/aci_prod"
export TRIGGERS_REDIS_URL="redis://redis-host:6379/0"
```

### Scaling

- **Horizontal Scaling**: Run multiple worker instances
- **Redis Clustering**: Use Redis cluster for high availability
- **Database**: Use managed PostgreSQL with read replicas
- **Load Balancing**: Use ALB/nginx for webhook endpoint distribution

## Troubleshooting

### Common Issues

1. **Webhook verification failures**:
   - Check signing secrets are correctly set
   - Verify timestamp is within allowed window
   - Ensure payload encoding matches expectations

2. **Database connection errors**:
   - Verify database is running and accessible
   - Check database URL format and credentials
   - Run migrations: `make migrate-triggers`

3. **Redis connection errors**:
   - Ensure Redis is running
   - Check Redis URL format
   - Verify network connectivity

4. **Worker processing failures**:
   - Check worker logs: `make logs-triggers`
   - Monitor failed job queue in RQ dashboard
   - Review job error messages and stack traces

### Debugging

```bash
# View service logs
make logs-triggers

# Check service health
curl http://localhost:8000/v1/webhooks/health

# Inspect database
docker-compose -f docker/docker-compose.triggers.yml exec db psql -U postgres -d aci_triggers

# Monitor Redis queues
docker-compose -f docker/docker-compose.triggers.yml exec redis redis-cli
```

### Performance Monitoring

- **Response Times**: Monitor webhook endpoint response times (should be <1s)
- **Queue Depth**: Monitor RQ queue depth and processing rates
- **Error Rates**: Track webhook verification failures and job failures
- **Database Performance**: Monitor query performance and connection usage

## API Reference

### Response Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid payload, missing data) |
| 401 | Unauthorized (invalid signature) |
| 500 | Internal Server Error |

### Error Response Format

```json
{
  "error": "Detailed error message"
}
```

### Success Response Examples

**Slack URL Verification:**
```json
{
  "challenge": "3eZbrw1aBm2rZhg4vNwuGxG9"
}
```

**Standard Success:**
```json
{
  "status": "ok"
}
```

**HubSpot Batch Processing:**
```json
{
  "status": "ok",
  "events_processed": 3,
  "events_skipped": 0
}
```

## Contributing

1. Follow existing code patterns and type hints
2. Add tests for new functionality
3. Update documentation for API changes
4. Run linting: `ruff format . && ruff check .`
5. Ensure all tests pass: `make test-triggers`

## Support

For issues and questions:
- Check the troubleshooting section above
- Review logs for error details
- Test with sample payloads from fixtures
- Verify environment variable configuration