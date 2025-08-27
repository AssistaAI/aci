# ACI Backend Makefile
# Makefile for managing the ACI backend services, including triggers module

.PHONY: help up-triggers down-triggers test-triggers logs-triggers clean-triggers restart-triggers

# Default target
help:
	@echo "Available targets:"
	@echo "  up-triggers       - Start triggers module services (API, worker, Redis, DB)"
	@echo "  down-triggers     - Stop triggers module services"  
	@echo "  test-triggers     - Run triggers module tests"
	@echo "  logs-triggers     - View logs from triggers services"
	@echo "  clean-triggers    - Clean up triggers volumes and containers"
	@echo "  restart-triggers  - Restart triggers module services"
	@echo "  migrate-triggers  - Run database migrations for triggers"
	@echo "  dashboard-triggers- Start with RQ dashboard for monitoring jobs"

# Start triggers module services
up-triggers:
	@echo "🚀 Starting ACI triggers module..."
	docker-compose -f docker/docker-compose.triggers.yml up -d
	@echo "✅ Triggers module started!"
	@echo "🌐 API available at: http://localhost:8000"
	@echo "💾 Redis available at: localhost:6379"  
	@echo "🗄️  PostgreSQL available at: localhost:5432"
	@echo ""
	@echo "📊 To start with monitoring dashboard, run: make dashboard-triggers"
	@echo "📋 To view logs, run: make logs-triggers"

# Stop triggers module services
down-triggers:
	@echo "🛑 Stopping ACI triggers module..."
	docker-compose -f docker/docker-compose.triggers.yml down
	@echo "✅ Triggers module stopped!"

# Start with RQ dashboard for job monitoring
dashboard-triggers:
	@echo "🚀 Starting ACI triggers module with monitoring dashboard..."
	docker-compose -f docker/docker-compose.triggers.yml --profile dashboard up -d
	@echo "✅ Triggers module started with dashboard!"
	@echo "🌐 API available at: http://localhost:8000"
	@echo "📊 RQ Dashboard available at: http://localhost:9181"
	@echo "💾 Redis available at: localhost:6379"
	@echo "🗄️  PostgreSQL available at: localhost:5432"

# Run triggers module tests (local)
test-triggers:
	@echo "🧪 Running triggers module tests locally..."
	@echo "📦 Installing test dependencies..."
	uv sync --group dev
	@echo "🔧 Setting up test environment..."
	@# Export test environment variables
	export TRIGGERS_SLACK_SIGNING_SECRET=test_secret_123 && \
	export TRIGGERS_HUBSPOT_APP_SECRET=test_hubspot_secret && \
	export TRIGGERS_PUBSUB_OIDC_AUDIENCE=https://test.com/webhooks/gmail/pubsub && \
	export TRIGGERS_GOOGLE_ISSUER=https://accounts.google.com && \
	export TRIGGERS_REDIS_URL=redis://localhost:6379/0 && \
	export TRIGGERS_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/aci_triggers_test && \
	uv run pytest aci/triggers/tests/ -v --tb=short
	@echo "✅ Tests completed!"

# Run triggers module tests in isolated Docker environment
test-triggers-docker:
	@echo "🐳 Running triggers module tests in Docker..."
	@echo "🧪 This will create isolated test database and Redis instances"
	docker-compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test-runner
	@echo "🧹 Cleaning up test containers..."
	docker-compose -f docker/docker-compose.test.yml down -v
	@echo "✅ Docker tests completed!"

# Run triggers module tests with detailed output
test-triggers-verbose:
	@echo "🐳 Running triggers module tests in Docker with verbose output..."
	docker-compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test-runner test-runner
	docker-compose -f docker/docker-compose.test.yml down -v

# View logs from triggers services
logs-triggers:
	@echo "📋 Viewing triggers module logs..."
	docker-compose -f docker/docker-compose.triggers.yml logs -f

# Clean up triggers volumes and containers
clean-triggers:
	@echo "🧹 Cleaning up triggers module..."
	docker-compose -f docker/docker-compose.triggers.yml down -v --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup completed!"

# Restart triggers module services
restart-triggers: down-triggers up-triggers
	@echo "🔄 Triggers module restarted!"

# Run database migrations for triggers
migrate-triggers:
	@echo "📊 Running database migrations for triggers..."
	@echo "⚠️  Make sure triggers services are running (make up-triggers)"
	docker-compose -f docker/docker-compose.triggers.yml exec api alembic upgrade head
	@echo "✅ Migrations completed!"

# Check health of triggers services
health-triggers:
	@echo "🏥 Checking health of triggers services..."
	@echo "API Health:"
	@curl -f http://localhost:8000/webhooks/health || echo "❌ API unhealthy"
	@echo ""
	@echo "Redis Health:"
	@docker-compose -f docker/docker-compose.triggers.yml exec redis redis-cli ping || echo "❌ Redis unhealthy"
	@echo ""
	@echo "Database Health:"
	@docker-compose -f docker/docker-compose.triggers.yml exec db pg_isready -U postgres || echo "❌ Database unhealthy"

# Development setup
dev-triggers:
	@echo "🛠️  Setting up triggers module for development..."
	@echo "📦 Installing dependencies..."
	uv sync --group dev
	@echo "🚀 Starting services..."
	$(MAKE) up-triggers
	@echo "⏳ Waiting for services to be ready..."
	sleep 10
	@echo "📊 Running migrations..."
	$(MAKE) migrate-triggers
	@echo "✅ Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Test webhooks: curl -X POST http://localhost:8000/webhooks/health"
	@echo "  2. Run tests: make test-triggers"  
	@echo "  3. View logs: make logs-triggers"
	@echo "  4. Monitor jobs: make dashboard-triggers"

# Production deployment commands
deploy-triggers:
	@echo "🚀 Deploying triggers module to production..."
	@echo "⚠️  This should only be run in production environments!"
	docker-compose -f docker/docker-compose.triggers.yml -f docker/docker-compose.prod.yml up -d --build
	@echo "✅ Production deployment completed!"

# Backup database
backup-triggers:
	@echo "💾 Backing up triggers database..."
	docker-compose -f docker/docker-compose.triggers.yml exec db pg_dump -U postgres -d aci_triggers > backup_triggers_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup completed!"

# Show webhook URLs for external configuration
show-webhook-urls:
	@echo "🔗 Webhook URLs for external services:"
	@echo ""
	@echo "Slack Events API:"
	@echo "  URL: https://yourdomain.com/webhooks/slack/events"
	@echo "  Method: POST"
	@echo "  Required Headers: X-Slack-Signature, X-Slack-Request-Timestamp"
	@echo ""
	@echo "HubSpot Webhooks:"
	@echo "  URL: https://yourdomain.com/webhooks/hubspot"
	@echo "  Method: POST"
	@echo "  Required Headers: X-HubSpot-Signature-V3, X-HubSpot-Request-Timestamp"
	@echo ""
	@echo "Gmail Pub/Sub Push:"
	@echo "  URL: https://yourdomain.com/webhooks/gmail/pubsub"
	@echo "  Method: POST"
	@echo "  Required Headers: Authorization (Bearer JWT)"
	@echo ""
	@echo "For local development with ngrok:"
	@echo "  1. Install ngrok: https://ngrok.com/"
	@echo "  2. Run: ngrok http 8000"
	@echo "  3. Use the ngrok URL as your webhook endpoint"