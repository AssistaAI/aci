#!/bin/bash

# Integration Test & Heal Script
# Usage: ./scripts/test_integration.sh APP_NAME [API_KEY] [OPTIONS]

set -e

APP_NAME=$1
ACI_API_KEY=${2:-$(cat .aci_api_key 2>/dev/null || echo "")}
LINKED_ACCOUNT_OWNER=${3:-"test"}

if [ -z "$APP_NAME" ]; then
    echo "Usage: ./scripts/test_integration.sh APP_NAME [ACI_API_KEY] [LINKED_ACCOUNT_OWNER]"
    echo ""
    echo "Examples:"
    echo "  ./scripts/test_integration.sh ARXIV                    # No auth app"
    echo "  ./scripts/test_integration.sh BRAVE_SEARCH my-key      # With API key"
    echo "  ./scripts/test_integration.sh GMAIL my-key test        # OAuth app"
    echo ""
    echo "Set ACI_API_KEY in .aci_api_key file or pass as second argument"
    exit 1
fi

if [ -z "$ACI_API_KEY" ]; then
    echo "❌ Error: ACI API key not provided"
    echo ""
    echo "Option 1: Create .aci_api_key file with your key"
    echo "Option 2: Pass key as second argument"
    echo "Option 3: Generate new key:"
    echo "  docker compose exec runner python -m aci.cli create-random-api-key --visibility-access private"
    exit 1
fi

echo "🧪 Testing integration: $APP_NAME"
echo "🔑 Using ACI API key: ${ACI_API_KEY:0:10}..."
echo "👤 Linked account owner: $LINKED_ACCOUNT_OWNER"
echo ""

# Run the test command
docker compose exec runner python -m aci.cli test-app-functions \
    --app-name "$APP_NAME" \
    --aci-api-key "$ACI_API_KEY" \
    --linked-account-owner-id "$LINKED_ACCOUNT_OWNER" \
    --auto-fix \
    --report-dir ./test_reports

echo ""
echo "✅ Test complete! Check ./test_reports/ for detailed results"
