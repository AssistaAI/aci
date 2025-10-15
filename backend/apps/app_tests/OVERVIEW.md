# App Testing Framework - Technical Overview

## Architecture

### Core Components

1. **conftest.py** - Pytest configuration and fixtures
   - `AppTestConfig` class - Loads app.json and functions.json
   - `generate_mock_payload()` - Auto-generates test data from JSON schemas
   - Authentication handling for API Key, OAuth2, Basic Auth
   - Fixtures for each app (apollo_config, apollo_auth_headers, etc.)

2. **run_tests.py** - Standalone test runner
   - Works without pytest
   - Direct API testing with requests library
   - Detailed console output with test results
   - Exit codes for CI/CD integration

3. **apollo/test_apollo_functions.py** - Dynamic test generation
   - Uses pytest parametrization
   - Generates one test per function from functions.json
   - Customizable test data via APOLLO_TEST_DATA dict
   - Skip logic for write/credit operations

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Execution Flow                       │
└─────────────────────────────────────────────────────────────┘

1. Load Configuration
   ├─ Read apps/apollo/app.json
   │  └─ Extract security_schemes (API key config)
   ├─ Read apps/apollo/functions.json
   │  └─ Get all 27 function definitions
   └─ Load .env.test for credentials

2. For Each Function
   ├─ Extract protocol_data (method, URL, path)
   ├─ Extract parameters schema (body, query, header)
   ├─ Generate mock payload from JSON schema
   │  ├─ Use test data override if provided
   │  ├─ Otherwise generate from schema
   │  └─ Handle required fields, defaults, types
   ├─ Build request
   │  ├─ Construct full URL with query params
   │  ├─ Add authentication headers
   │  └─ Prepare body payload
   └─ Execute & Validate
      ├─ Make HTTP request
      ├─ Check status code (200, 201, 422)
      ├─ Validate response structure
      └─ Report result

3. Generate Report
   └─ Summary with passed/failed/skipped counts
```

### File Structure

```
backend/apps/tests/
├── .env.test                    # API credentials (gitignored)
├── conftest.py                  # Pytest fixtures & utilities
├── run_tests.py                 # Standalone test runner
├── pytest.ini                   # Pytest configuration
├── README.md                    # Full documentation
├── QUICKSTART.md                # Quick start guide
├── OVERVIEW.md                  # This file
└── apollo/
    ├── __init__.py
    └── test_apollo_functions.py # Apollo.io tests

Future structure:
└── [app_name]/
    ├── __init__.py
    └── test_[app_name]_functions.py
```

## Key Features

### 1. Auto-Discovery
- Reads `app.json` to understand authentication
- Reads `functions.json` to discover all endpoints
- No manual test writing required

### 2. Schema-Based Mock Data
```python
# From this schema:
{
  "type": "object",
  "properties": {
    "name": {"type": "string"},
    "count": {"type": "integer", "default": 5}
  },
  "required": ["name"]
}

# Generates:
{"name": "test_value", "count": 5}
```

### 3. Smart Authentication
```python
# API Key (header)
security_schemes: {
  "api_key": {
    "location": "header",
    "name": "X-Api-Key"
  }
}
# Reads: APOLLO_API_KEY from .env.test
# Adds: {"X-Api-Key": "your_key"}

# OAuth2 (bearer token)
# Reads: APOLLO_ACCESS_TOKEN
# Adds: {"Authorization": "Bearer token"}

# Basic Auth
# Reads: APOLLO_USERNAME, APOLLO_PASSWORD
# Adds: {"Authorization": "Basic base64(user:pass)"}
```

### 4. Flexible Test Data
```python
# Override mock data for specific functions
APOLLO_TEST_DATA = {
    "APOLLO__PEOPLE_SEARCH": {
        "body": {
            "q_keywords": "software engineer",
            "per_page": 5,
        }
    }
}
```

### 5. Skip Logic
```python
# Skip write operations by default
SKIP_WRITE_FUNCTIONS = [
    "APOLLO__CREATE_CONTACT",
    "APOLLO__CREATE_ACCOUNT",
]

# Skip credit-consuming operations
# Skip functions needing specific IDs
```

## Extending to New Apps

### Step 1: Create Test Directory
```bash
mkdir -p backend/apps/tests/gmail
touch backend/apps/tests/gmail/__init__.py
```

### Step 2: Add Credentials
```bash
# In .env.test
GMAIL_API_KEY=your_gmail_api_key
```

### Step 3: Add Fixtures (conftest.py)
```python
@pytest.fixture(scope="session")
def gmail_config(apps_dir: Path) -> AppTestConfig:
    return AppTestConfig("gmail", apps_dir)

@pytest.fixture
def gmail_auth_headers(gmail_config: AppTestConfig) -> Dict[str, str]:
    return gmail_config.get_auth_headers()
```

### Step 4: Copy Test Template
```bash
cp backend/apps/tests/apollo/test_apollo_functions.py \
   backend/apps/tests/gmail/test_gmail_functions.py
```

### Step 5: Update Test File
- Replace "apollo" with "gmail"
- Update test data dict
- Define skip functions

### Done!
```bash
pytest apps/tests/gmail/ -v
```

## Testing Strategy

### Read-Only Tests (Safe)
- Search endpoints
- List endpoints
- Get/fetch endpoints
- Stats/analytics endpoints
- Run by default

### Write Tests (Careful)
- Create/POST endpoints
- Update/PUT endpoints
- Delete endpoints
- Skipped by default
- Require explicit enable

### Credit Tests (Expensive)
- Enrichment APIs
- Data purchasing
- Premium features
- Always skipped unless explicitly enabled

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run App Tests
  run: |
    cd backend
    pytest apps/tests/ --junitxml=results.xml
  env:
    APOLLO_API_KEY: ${{ secrets.APOLLO_API_KEY }}
```

### Docker Compose
```bash
docker compose exec test-runner pytest apps/tests/apollo/ -v
```

### Local Development
```bash
python apps/tests/run_tests.py
```

## Performance

### Test Execution Time
- Per function: ~1-3 seconds (API call latency)
- Apollo.io (16 tests): ~20-30 seconds
- Parallel execution: Use `pytest -n auto`

### Rate Limiting
- Framework respects API rate limits
- Add delays if needed: `time.sleep(0.5)`
- Use `pytest-xdist` for controlled parallelism

## Troubleshooting

### Common Issues

1. **Missing API Key**
   - Error: "Missing APOLLO_API_KEY in .env.test"
   - Solution: Add key to backend/.env.test

2. **Authentication Failed (401)**
   - Check API key is valid
   - Verify key has required permissions
   - Test key directly with curl

3. **Validation Error (422)**
   - Mock data may not match API requirements
   - Override with real data in TEST_DATA dict
   - Check API documentation for required fields

4. **Import Errors**
   - Run from correct directory: backend/apps/tests/
   - Ensure __init__.py files exist
   - Check Python path

5. **Rate Limited (429)**
   - Reduce parallel tests
   - Add delays between requests
   - Use test/sandbox API keys if available

## Best Practices

1. **Credentials Management**
   - Never commit .env.test
   - Use different keys for CI/CD
   - Rotate keys regularly
   - Use least privilege (read-only when possible)

2. **Test Data**
   - Keep payloads minimal
   - Use realistic but fake data
   - Clean up created resources
   - Don't test with production data

3. **Test Organization**
   - One directory per app
   - Group similar functions
   - Document special requirements
   - Keep tests independent

4. **Maintenance**
   - Update tests when app.json changes
   - Review test data periodically
   - Monitor for API changes
   - Track flaky tests

## Metrics & Reporting

### Console Output
```
Testing: APOLLO__PEOPLE_SEARCH
[PASSED] APOLLO__PEOPLE_SEARCH

TEST SUMMARY
Passed:  14
Failed:  0
Skipped: 11
```

### HTML Reports
```bash
pytest apps/tests/apollo/ --html=report.html
```

### JUnit XML (for CI)
```bash
pytest apps/tests/apollo/ --junitxml=results.xml
```

### Coverage
```bash
pytest apps/tests/ --cov=apps --cov-report=html
```

## Future Enhancements

- [ ] Response schema validation (validate against expected structure)
- [ ] Automatic retry with exponential backoff
- [ ] Webhook testing support
- [ ] Performance benchmarking
- [ ] Resource cleanup after tests
- [ ] Test via ACI platform (not direct API)
- [ ] Automatic API key rotation
- [ ] Cost tracking for credit-based APIs
- [ ] Contract testing (API spec validation)
- [ ] Mock server for local development

## Technical Details

### Dependencies
- pytest - Test framework
- requests - HTTP client
- python-dotenv - Environment variables
- Standard library (json, os, pathlib, typing)

### Python Version
- Python 3.12+ (as per project requirements)

### Compatibility
- Works with all REST APIs
- Supports JSON request/response
- Handles various auth schemes
- Compatible with Docker & local execution

---

**Framework Version:** 1.0.0
**Last Updated:** 2025-10-15
**Author:** ACI.dev Team
