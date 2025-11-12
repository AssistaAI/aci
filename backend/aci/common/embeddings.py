from typing import Any

from openai import OpenAI

from aci.common.schemas.app import AppEmbeddingFields
from aci.common.schemas.function import FunctionEmbeddingFields


def generate_app_embedding(
    app: AppEmbeddingFields,
    openai_client: OpenAI,
    embedding_model: str,
    embedding_dimension: int,
) -> list[float]:
    """Generate embedding for app using clean, semantic text representation."""
    return generate_embedding(
        openai_client, embedding_model, embedding_dimension, _build_app_embedding_text(app)
    )


def _build_app_embedding_text(app: AppEmbeddingFields) -> str:
    """Build a clean, human-readable text representation of an app for embedding."""
    parts = [f"App: {app.name}"]

    # Add optional fields if present
    _add_field_if_exists(parts, app, "display_name", "Display")
    _add_field_if_exists(parts, app, "description", "Description")

    if hasattr(app, "categories") and app.categories:
        parts.append(f"Categories: {', '.join(app.categories)}")

    _add_field_if_exists(parts, app, "provider", "Provider")

    return " | ".join(parts)


# TODO: batch generate function embeddings
# TODO: update app embedding to include function embeddings whenever functions are added/updated?
def generate_function_embeddings(
    functions: list[FunctionEmbeddingFields],
    openai_client: OpenAI,
    embedding_model: str,
    embedding_dimension: int,
) -> list[list[float]]:
    # Generate embeddings for functions
    function_embeddings: list[list[float]] = []
    for function in functions:
        function_embeddings.append(
            generate_function_embedding(
                function, openai_client, embedding_model, embedding_dimension
            )
        )

    return function_embeddings


def generate_function_embedding(
    function: FunctionEmbeddingFields,
    openai_client: OpenAI,
    embedding_model: str,
    embedding_dimension: int,
) -> list[float]:
    """Generate embedding for function using clean, semantic text representation."""
    return generate_embedding(
        openai_client, embedding_model, embedding_dimension, _build_function_embedding_text(function)
    )


def _build_function_embedding_text(function: FunctionEmbeddingFields) -> str:
    """Build a clean, human-readable text representation of a function for embedding."""
    parts = []

    # Clean function name
    clean_name = function.name.split("__")[-1] if "__" in function.name else function.name
    parts.append(f"Function: {clean_name}")
    parts.append(f"Description: {function.description}")

    # Add parameters if available
    _add_function_parameters(parts, function.parameters)

    # Add service name if present
    if "__" in function.name:
        parts.append(f"Service: {function.name.split('__')[0]}")

    return " | ".join(parts)


def _add_field_if_exists(parts: list[str], obj: Any, field: str, label: str) -> None:
    """Helper to add field to parts list if it exists and has value."""
    if hasattr(obj, field) and getattr(obj, field):
        parts.append(f"{label}: {getattr(obj, field)}")


def _add_function_parameters(parts: list[str], parameters: dict) -> None:
    """Helper to add function parameters to parts list."""
    if not parameters or "properties" not in parameters:
        return

    param_descriptions = [
        f"{name}: {schema.get('description', '')}" if "description" in schema else name
        for name, schema in list(parameters["properties"].items())[:10]  # Limit to 10
    ]

    if param_descriptions:
        parts.append(f"Parameters: {', '.join(param_descriptions)}")


# TODO: allow different inference providers
# TODO: exponential backoff?
def generate_embedding(
    openai_client: OpenAI, embedding_model: str, embedding_dimension: int, text: str
) -> list[float]:
    """
    Generate an embedding for the given text using OpenAI's model.
    """
    # Generate embedding for text
    try:
        response = openai_client.embeddings.create(
            input=[text],
            model=embedding_model,
            dimensions=embedding_dimension,
        )
        embedding: list[float] = response.data[0].embedding
        return embedding
    except Exception:
        # Error generating embedding
        raise
