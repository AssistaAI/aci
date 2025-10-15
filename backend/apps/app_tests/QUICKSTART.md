# Quick Start Guide - App Testing Framework

## 🚀 Get Started in 3 Steps

### Step 1: Add Your Apollo.io API Key

Edit `backend/.env.test` and add your API key:

```bash
APOLLO_API_KEY=your_actual_api_key_here
```

Get your API key from: https://app.apollo.io/#/settings/integrations/api

### Step 2: Run Tests

**Option A: Using Docker (Recommended)**
```bash
cd backend
docker compose up -d
docker compose exec test-runner pytest apps/app_tests/apollo/ -v
```

**Option B: Using Local Python**
```bash
cd backend
source .venv/bin/activate  # or activate your virtualenv
python apps/app_tests/run_tests.py
```

**Option C: Direct pytest**
```bash
cd backend/apps/app_tests
pytest apollo/ -v
```

### Step 3: View Results

Tests will show:
- ✓ Passed tests (green)
- ✗ Failed tests (red)
- ⊘ Skipped tests (yellow)

## 📊 What Gets Tested?

### Automatic Tests (27 functions total)

**✓ Read-Only Tests (Safe - Run by Default)**
- People Search
- Organization Search
- Organization Enrichment
- List Account Stages
- List Contact Stages
- List Deals
- List Opportunity Stages
- List Labels
- List Custom Fields
- List Email Accounts
- List Users
- Search Sequences
- API Usage Stats
- And more...

**⊘ Skipped by Default**
- Write operations (create contacts, accounts, deals)
- Credit-consuming operations (enrichment)
- Functions requiring specific IDs

## 🎯 Common Commands

### Test specific function
```bash
pytest apps/app_tests/apollo/ -v -k "PEOPLE_SEARCH"
```

### Generate HTML report
```bash
pytest apps/app_tests/apollo/ --html=report.html --self-contained-html
open report.html  # macOS
```

### Run with verbose output
```bash
python apps/app_tests/run_tests.py
```

### Test in parallel (faster)
```bash
pytest apps/app_tests/apollo/ -n auto
```

## 🔍 Example Output

```
Testing: APOLLO__PEOPLE_SEARCH
Description: Search for people in Apollo's database of 210M+ contacts
================================================================================
Request URL: https://api.apollo.io/api/v1/mixed_people/search
Method: POST
Body: {"q_keywords": "software engineer", "per_page": 5}
Response Status: 200
✓ PASSED: APOLLO__PEOPLE_SEARCH

Testing: APOLLO__ORGANIZATION_ENRICHMENT
Description: Enrich organization data with additional company information
================================================================================
Request URL: https://api.apollo.io/api/v1/organizations/enrich?domain=google.com
Method: GET
Response Status: 200
✓ PASSED: APOLLO__ORGANIZATION_ENRICHMENT

================================================================================
TEST SUMMARY
================================================================================
Total:   16
✓ Passed:  14
✗ Failed:  0
⊘ Skipped: 11
================================================================================
```

## 🛠️ Troubleshooting

### "Missing APOLLO_API_KEY in .env.test"
→ Add your API key to `backend/.env.test`

### "401 Unauthorized"
→ Check that your API key is valid and active

### "422 Validation Error"
→ This is normal for some mock data. Override with real data in test file.

### "429 Rate Limited"
→ Apollo.io has rate limits. Add delays or reduce parallel tests.

## 📈 Next Steps

### Add More Apps

Want to test Gmail, Slack, GitHub, etc.?

1. Copy the Apollo test structure:
```bash
cp -r backend/apps/app_tests/apollo backend/apps/app_tests/gmail
```

2. Update the test file to use `gmail` instead of `apollo`

3. Add credentials to `.env.test`:
```bash
GMAIL_API_KEY=your_key
```

4. Run tests:
```bash
pytest apps/app_tests/gmail/ -v
```

The framework automatically discovers all functions from `app.json` and `functions.json`!

### Customize Test Data

Edit `apps/app_tests/apollo/test_apollo_functions.py`:

```python
APOLLO_TEST_DATA = {
    "APOLLO__PEOPLE_SEARCH": {
        "body": {
            "q_keywords": "your custom search",
            "person_titles": ["CEO", "CTO"],
            "per_page": 10,
        }
    }
}
```

### Enable Write Tests

To test functions that create data:

1. Use a test/sandbox Apollo account
2. Remove function from `SKIP_WRITE_FUNCTIONS` list
3. Add cleanup logic after tests

## 🎓 How It Works

```
1. Framework reads apps/apollo/app.json → Gets auth config
2. Framework reads apps/apollo/functions.json → Gets all functions
3. For each function:
   - Builds request from protocol_data
   - Generates payload from JSON schema
   - Adds auth headers
   - Makes API call
   - Validates response
4. Reports results
```

**Zero manual work needed!** Just add new apps and their credentials.

## 📚 More Info

- Full documentation: `backend/apps/app_tests/README.md`
- Test framework code: `backend/apps/app_tests/conftest.py`
- Apollo tests: `backend/apps/app_tests/apollo/test_apollo_functions.py`

---

**Ready to test all 600+ integrations automatically?** 🚀
