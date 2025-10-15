"""
Pytest configuration and fixtures for app integration testing.

This module provides:
- Automatic test discovery from app.json and functions.json
- Authentication handling for different security schemes
- Mock data generation from JSON schemas
- Test fixtures for API testing
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

# Load test environment variables
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env.test")


class AppTestConfig:
    """Configuration for testing a specific app."""

    def __init__(self, app_name: str, apps_dir: Path):
        self.app_name = app_name.upper()
        self.app_dir = apps_dir / app_name.lower()
        self.app_json_path = self.app_dir / "app.json"
        self.functions_json_path = self.app_dir / "functions.json"

        # Load app configuration
        with open(self.app_json_path) as f:
            self.app_config = json.load(f)

        # Load functions
        with open(self.functions_json_path) as f:
            self.functions = json.load(f)

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get authentication headers based on app's security scheme.

        Returns:
            Dict with headers required for authentication
        """
        headers = {"Content-Type": "application/json"}
        security_schemes = self.app_config.get("security_schemes", {})

        if "api_key" in security_schemes:
            scheme = security_schemes["api_key"]
            location = scheme.get("location", "header")
            name = scheme.get("name", "Authorization")
            prefix = scheme.get("prefix")

            if location == "header":
                # Get API key from environment
                env_key = f"{self.app_name}_API_KEY"
                api_key = os.getenv(env_key)

                if not api_key:
                    pytest.skip(f"Missing {env_key} in .env.test - skipping tests")

                # Add prefix if specified
                value = f"{prefix} {api_key}" if prefix else api_key
                headers[name] = value

        elif "oauth2" in security_schemes:
            # OAuth2 handling
            env_key = f"{self.app_name}_ACCESS_TOKEN"
            access_token = os.getenv(env_key)

            if not access_token:
                pytest.skip(f"Missing {env_key} in .env.test - skipping tests")

            headers["Authorization"] = f"Bearer {access_token}"

        elif "basic" in security_schemes:
            # Basic auth handling
            import base64

            username = os.getenv(f"{self.app_name}_USERNAME")
            password = os.getenv(f"{self.app_name}_PASSWORD")

            if not username or not password:
                pytest.skip(f"Missing credentials for {self.app_name} - skipping tests")

            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers


def generate_mock_payload(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Generate mock data from JSON schema.

    Args:
        schema: JSON schema definition

    Returns:
        Dict with mock data matching the schema
    """
    if schema.get("type") != "object":
        return {}

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    mock_data = {}

    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type")
        default = prop_schema.get("default")

        # Use default if available
        if default is not None:
            mock_data[prop_name] = default
            continue

        # Only include required fields for minimal payload
        if prop_name not in required:
            continue

        # Generate mock data based on type
        if prop_type == "string":
            # Check for enums
            if "enum" in prop_schema:
                mock_data[prop_name] = prop_schema["enum"][0]
            else:
                mock_data[prop_name] = "test_value"

        elif prop_type == "integer":
            mock_data[prop_name] = prop_schema.get("default", 1)

        elif prop_type == "number":
            mock_data[prop_name] = prop_schema.get("default", 1.0)

        elif prop_type == "boolean":
            mock_data[prop_name] = False

        elif prop_type == "array":
            items_schema = prop_schema.get("items", {})
            if items_schema.get("type") == "string":
                mock_data[prop_name] = ["test_item"]
            elif items_schema.get("type") == "object":
                mock_data[prop_name] = [generate_mock_payload(items_schema)]
            else:
                mock_data[prop_name] = []

        elif prop_type == "object":
            mock_data[prop_name] = generate_mock_payload(prop_schema)

    return mock_data


@pytest.fixture(scope="session")
def apps_dir() -> Path:
    """Get the apps directory path."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def apollo_config(apps_dir: Path) -> AppTestConfig:
    """Apollo.io test configuration."""
    return AppTestConfig("apollo", apps_dir)


@pytest.fixture
def apollo_auth_headers(apollo_config: AppTestConfig) -> dict[str, str]:
    """Get Apollo.io authentication headers."""
    return apollo_config.get_auth_headers()
