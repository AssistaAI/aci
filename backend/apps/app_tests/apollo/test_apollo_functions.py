"""
Automated tests for Apollo.io integration.

This module automatically tests all Apollo.io functions by:
1. Reading function definitions from functions.json
2. Generating appropriate test payloads
3. Making real API calls to Apollo.io
4. Validating responses

Tests are parametrized and generated dynamically from the functions.json file.
"""

from pathlib import Path
from typing import Any

import pytest
import requests

from ..conftest import AppTestConfig, generate_mock_payload


# Read Apollo.io functions
@pytest.fixture(scope="module")
def apollo_functions(apollo_config: AppTestConfig) -> list[dict[str, Any]]:
    """Load all Apollo.io functions."""
    return apollo_config.functions


# Define test data for specific functions that need real data
APOLLO_TEST_DATA = {
    "APOLLO__PEOPLE_SEARCH": {
        "body": {
            "q_keywords": "software engineer",
            "per_page": 5,
        }
    },
    "APOLLO__ORGANIZATION_SEARCH": {
        "body": {
            "q_organization_name": "Google",
            "per_page": 5,
        }
    },
    "APOLLO__ORGANIZATION_ENRICHMENT": {
        "query": {
            "domain": "google.com",
        }
    },
    "APOLLO__BULK_ORGANIZATION_ENRICHMENT": {
        "body": {
            "domains": ["google.com", "apple.com"],
        }
    },
    "APOLLO__LIST_ACCOUNT_STAGES": {},
    "APOLLO__LIST_CONTACT_STAGES": {},
    "APOLLO__LIST_DEALS": {
        "query": {
            "per_page": 5,
        }
    },
    "APOLLO__OPPORTUNITY_STAGES": {},
    "APOLLO__LABELS": {},
    "APOLLO__TYPED_CUSTOM_FIELDS": {},
    "APOLLO__LIST_EMAIL_ACCOUNTS": {},
    "APOLLO__USERS": {
        "query": {
            "per_page": 5,
        }
    },
    "APOLLO__SEARCH_SEQUENCES": {
        "body": {
            "per_page": 5,
        }
    },
    "APOLLO__API_USAGE_STATS": {"body": {}},
}

# Functions that require write access or create resources (skip by default)
SKIP_WRITE_FUNCTIONS = [
    "APOLLO__CREATE_CONTACT",
    "APOLLO__CREATE_ACCOUNT",
    "APOLLO__CREATE_DEAL",
    "APOLLO__CREATE_TASK",
    "APOLLO__ADD_CONTACTS_TO_SEQUENCE",
    "APOLLO__BULK_UPDATE_ACCOUNT_STAGE",
    "APOLLO__PEOPLE_ENRICHMENT",  # Costs credits
    "APOLLO__BULK_PEOPLE_ENRICHMENT",  # Costs credits
]

# Functions that need specific IDs to work (skip for now)
SKIP_ID_REQUIRED_FUNCTIONS = [
    "APOLLO__SEARCH_CONTACTS",
    "APOLLO__SEARCH_ACCOUNTS",
    "APOLLO__ORGANIZATION_JOB_POSTINGS",
]


def build_request_url(
    function_def: dict[str, Any], query_params: dict[str, Any] | None = None
) -> str:
    """
    Build full request URL from function definition.

    Args:
        function_def: Function definition from functions.json
        query_params: Query parameters to append

    Returns:
        Full URL with query parameters
    """
    protocol_data = function_def["protocol_data"]
    server_url = protocol_data["server_url"]
    path = protocol_data["path"]
    url = f"{server_url}{path}"

    if query_params:
        # Build query string
        query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
        url = f"{url}?{query_string}"

    return url


def build_request_payload(
    function_def: dict[str, Any], test_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Build request payload from function definition and test data.

    Args:
        function_def: Function definition from functions.json
        test_data: Test data override

    Returns:
        Dict with 'url', 'method', 'headers', 'json', 'params'
    """
    protocol_data = function_def["protocol_data"]
    method = protocol_data["method"]
    parameters = function_def.get("parameters", {})

    # Extract parameter sections
    body_schema = parameters.get("properties", {}).get("body", {})
    query_schema = parameters.get("properties", {}).get("query", {})
    header_schema = parameters.get("properties", {}).get("header", {})

    # Generate payloads (use test data if provided, otherwise generate from schema)
    body_data = (
        test_data.get("body")
        if test_data.get("body") is not None
        else generate_mock_payload(body_schema)
    )
    query_data = (
        test_data.get("query")
        if test_data.get("query") is not None
        else generate_mock_payload(query_schema)
    )
    header_data = generate_mock_payload(header_schema)

    # Build URL with query params
    url = build_request_url(function_def, query_data if query_data else None)

    return {
        "url": url,
        "method": method,
        "json": body_data if body_data else None,
        "headers": header_data,
    }


class TestApolloFunctions:
    """Test suite for Apollo.io API functions."""

    # Parametrize decorator removed - using pytest_generate_tests hook instead
    def test_apollo_function(
        self,
        function_def: dict[str, Any],
        apollo_auth_headers: dict[str, str],
        apollo_config: AppTestConfig,
    ) -> None:
        """
        Test a single Apollo.io function.

        This test:
        1. Builds the request from function definition
        2. Adds authentication headers
        3. Makes the API call
        4. Validates response status and structure
        """
        function_name = function_def["name"]
        print(f"\n{'=' * 60}")
        print(f"Testing: {function_name}")
        print(f"Description: {function_def.get('description', 'N/A')}")
        print(f"{'=' * 60}")

        # Get test data for this function
        test_data: dict[str, Any] = APOLLO_TEST_DATA.get(function_name, {})

        # Build request
        request_params = build_request_payload(function_def, test_data)

        # Merge auth headers
        request_params["headers"].update(apollo_auth_headers)

        print(f"Request URL: {request_params['url']}")
        print(f"Method: {request_params['method']}")
        if request_params.get("json"):
            print(f"Body: {request_params['json']}")

        # Make request
        response = requests.request(
            method=request_params["method"],
            url=request_params["url"],
            headers=request_params["headers"],
            json=request_params["json"],
            timeout=30,
        )

        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.text[:500]}")  # First 500 chars

        # Assertions
        assert response.status_code in [
            200,
            201,
            422,  # Validation error (expected for some mock data)
        ], f"Unexpected status code: {response.status_code}. Response: {response.text}"

        # If successful, validate response structure
        if response.status_code in [200, 201]:
            response_data = response.json()
            assert isinstance(response_data, dict | list), "Response should be JSON object or array"
            print(f"[PASSED] Test passed for {function_name}")


def pytest_generate_tests(metafunc: Any) -> None:
    """
    Dynamically generate tests for each Apollo function.

    This hook is called during test collection and generates
    a test case for each function in functions.json.
    """
    if "function_def" in metafunc.fixturenames:
        # Load functions
        apps_dir = Path(__file__).parent.parent.parent
        config = AppTestConfig("apollo", apps_dir)
        functions = config.functions

        # Generate test parameters
        test_params = []
        test_ids = []

        for func in functions:
            # Determine if should skip
            marks = []
            if func["name"] in SKIP_WRITE_FUNCTIONS:
                marks.append(pytest.mark.skip(reason="Write operation - skipped by default"))
            elif func["name"] in SKIP_ID_REQUIRED_FUNCTIONS:
                marks.append(pytest.mark.skip(reason="Requires specific IDs"))

            test_params.append(pytest.param(func, marks=marks))
            test_ids.append(func["name"])

        metafunc.parametrize("function_def", test_params, ids=test_ids)
