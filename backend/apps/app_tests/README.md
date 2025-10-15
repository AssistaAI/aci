# App Integration Testing Framework

Automated testing framework for all ACI.dev app integrations. Tests are automatically generated from `app.json` and `functions.json` files.

## Features

- **Auto-discovery**: Automatically finds and tests all functions in an app
- **Smart authentication**: Handles API keys, OAuth2, and Basic Auth automatically
- **Mock data generation**: Creates valid payloads from JSON schemas
- **Parallel execution**: Run tests concurrently for speed
- **Detailed reporting**: HTML reports with pass/fail status per function
- **Skip logic**: Automatically skips tests without credentials or that require write access

## Setup

### 1. Install Dependencies

The testing framework uses pytest and requests (already in your project):

```bash
cd backend
uv sync
```

### 2. Configure Credentials

Copy the `.env.test` template and add your API keys:

```bash
# Edit backend/.env.test and add your credentials
APOLLO_API_KEY=your_apollo_api_key_here
```

**IMPORTANT**: Never commit `.env.test` with real credentials! Add it to `.gitignore`:

```bash
echo ".env.test" >> backend/.gitignore
```

### 3. Get API Keys

For Apollo.io:
1. Sign up at https://app.apollo.io
2. Go to Settings → Integrations → API
3. Copy your API key to `.env.test`

## Running Tests

### Test Apollo.io (all read-only functions)

```bash
cd backend
docker compose exec test-runner pytest apps/app_tests/apollo/ -v
```

### Test with HTML Report

```bash
docker compose exec test-runner pytest apps/app_tests/apollo/ --html=report.html --self-contained-html
```

### Test Specific Function

```bash
docker compose exec test-runner pytest apps/app_tests/apollo/ -v -k "PEOPLE_SEARCH"
```

### Run All Tests in Parallel

```bash
docker compose exec test-runner pytest apps/app_tests/ -n auto
```

### Include Write Operations (will create data!)

```bash
docker compose exec test-runner pytest apps/app_tests/apollo/ -v -m "not skip"
```

## Test Structure

```
backend/apps/app_tests/
├── README.md                          # This file
├── conftest.py                        # Pytest configuration and fixtures
├── apollo/
│   ├── __init__.py
│   └── test_apollo_functions.py      # Auto-generated Apollo.io tests
└── [future apps]/
    └── test_[app]_functions.py       # Tests for other apps
```

## How It Works

### 1. Test Discovery

The framework automatically:
1. Reads `apps/apollo/app.json` for authentication config
2. Reads `apps/apollo/functions.json` for all function definitions
3. Generates a pytest test case for each function

### 2. Authentication

Based on `security_schemes` in `app.json`:
- **API Key**: Reads `{APP_NAME}_API_KEY` from `.env.test`
- **OAuth2**: Reads `{APP_NAME}_ACCESS_TOKEN` from `.env.test`
- **Basic Auth**: Reads `{APP_NAME}_USERNAME` and `{APP_NAME}_PASSWORD`

### 3. Mock Data Generation

For each function, the framework:
1. Analyzes the JSON schema in `parameters`
2. Generates minimal valid payloads for required fields
3. Uses default values when specified
4. Handles nested objects and arrays

### 4. Test Execution

Each test:
1. Builds the request URL from `protocol_data`
2. Adds authentication headers
3. Makes a real API call
4. Validates response status (200, 201, or 422 for validation errors)
5. Checks response structure

## Test Categories

### Read-Only Tests (Safe)
Run by default. These test:
- Search endpoints (people, organizations, contacts)
- List endpoints (deals, stages, labels)
- Enrichment lookups
- Usage stats

### Write Tests (Skipped by Default)
Create data in your account. To run:
```bash
pytest apps/app_tests/apollo/ --run-write-tests
```

These include:
- `CREATE_CONTACT`
- `CREATE_ACCOUNT`
- `CREATE_DEAL`
- `CREATE_TASK`
- `ADD_CONTACTS_TO_SEQUENCE`

### Credit-Consuming Tests (Skipped)
These use Apollo.io credits:
- `PEOPLE_ENRICHMENT`
- `BULK_PEOPLE_ENRICHMENT`

## Adding New Apps

To add tests for a new app (e.g., `github`):

### 1. Create Test Directory
```bash
mkdir -p backend/apps/app_tests/github
touch backend/apps/app_tests/github/__init__.py
```

### 2. Add Credentials to `.env.test`
```bash
echo "GITHUB_API_KEY=your_token" >> backend/.env.test
```

### 3. Add Fixture in `conftest.py`
```python
@pytest.fixture(scope="session")
def github_config(apps_dir: Path) -> AppTestConfig:
    """GitHub test configuration."""
    return AppTestConfig("github", apps_dir)

@pytest.fixture
def github_auth_headers(github_config: AppTestConfig) -> Dict[str, str]:
    """Get GitHub authentication headers."""
    return github_config.get_auth_headers()
```

### 4. Copy Test Template
```bash
cp backend/apps/app_tests/apollo/test_apollo_functions.py \
   backend/apps/app_tests/github/test_github_functions.py
```

### 5. Update Test File
Replace `apollo` with `github` in the test file.

## Customizing Tests

### Override Test Data

In your test file, define custom payloads:

```python
APP_TEST_DATA = {
    "FUNCTION_NAME": {
        "body": {
            "custom_field": "custom_value",
        },
        "query": {
            "param": "value",
        }
    }
}
```

### Skip Specific Functions

```python
SKIP_FUNCTIONS = [
    "FUNCTION_TO_SKIP",
]
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Run App Tests
  run: |
    cd backend
    docker compose exec test-runner pytest apps/app_tests/ --junitxml=junit.xml
  env:
    APOLLO_API_KEY: ${{ secrets.APOLLO_API_KEY }}
```

## Troubleshooting

### Tests are skipped
- Check that you've added the API key to `.env.test`
- Ensure the key name matches the pattern: `{APP_NAME}_API_KEY`

### Authentication errors (401/403)
- Verify your API key is valid
- Check that the API key has required permissions

### Validation errors (422)
- Normal for some mock data
- Override with real test data in `APP_TEST_DATA`

### Rate limiting (429)
- Add delays between tests
- Use `pytest-xdist` for parallel execution with limits

## Best Practices

1. **Never commit credentials**: Always use `.env.test` and add to `.gitignore`
2. **Use read-only tests by default**: Skip write operations unless necessary
3. **Test with sandbox accounts**: Use test/sandbox API keys when available
4. **Monitor API usage**: Track credit consumption for enrichment APIs
5. **Keep test data minimal**: Use `per_page=5` for list endpoints
6. **Add custom test data**: Override mock data for critical functions

## Examples

### Test Apollo.io People Search
```bash
docker compose exec test-runner pytest apps/app_tests/apollo/test_apollo_functions.py::TestApolloFunctions::test_apollo_function[APOLLO__PEOPLE_SEARCH] -v
```

### Generate HTML Report
```bash
docker compose exec test-runner pytest apps/app_tests/apollo/ --html=apollo_report.html
```

### Test Multiple Apps
```bash
docker compose exec test-runner pytest apps/app_tests/ -v
```

## Future Enhancements

- [ ] Rate limiting and retry logic
- [ ] Webhook testing support
- [ ] Response schema validation
- [ ] Performance benchmarking
- [ ] Automatic credential rotation
- [ ] Test data cleanup after write operations
- [ ] Integration with ACI backend (test via platform, not direct API)
