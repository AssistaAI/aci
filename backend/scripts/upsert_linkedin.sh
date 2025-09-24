#!/bin/bash

set -euo pipefail

echo "Upserting LinkedIn app with mock credentials..."

# Create temporary mock secrets file
TEMP_SECRETS=$(mktemp)

# Create mock OAuth2 credentials for LinkedIn
cat > "$TEMP_SECRETS" <<EOF
{
  "AIPOLABS_LINKEDIN_CLIENT_ID": "mock_client_id_linkedin",
  "AIPOLABS_LINKEDIN_CLIENT_SECRET": "mock_client_secret_linkedin"
}
EOF

# Upsert the LinkedIn app with mock secrets
python -m aci.cli upsert-app \
  --app-file "./apps/linkedin/app.json" \
  --secrets-file "$TEMP_SECRETS" \
  --skip-dry-run

# Clean up temporary file
rm -f "$TEMP_SECRETS"

echo "LinkedIn app upserted successfully with mock credentials!"
