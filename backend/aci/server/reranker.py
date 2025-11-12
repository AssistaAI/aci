"""
LLM-based reranker for improving function search results.
"""
import hashlib
import json
import threading
import time
from typing import Any

from openai import OpenAI

from aci.common.db.sql_models import Function

# Thread-safe cache for reranking results with TTL
_rerank_cache: dict[str, tuple[list[int], float]] = {}  # (indices, timestamp)
_cache_lock = threading.Lock()
MAX_CACHE_SIZE = 100
CACHE_TTL_SECONDS = 3600  # 1 hour


class FunctionReranker:
    """Rerank functions based on user intent using an LLM."""

    def __init__(self, openai_client: OpenAI):
        self.openai_client = openai_client

    def rerank_functions(
        self,
        functions: list[Function],
        intent: str,
        max_results: int | None = None,
        use_cache: bool = True,
    ) -> list[Function]:
        """
        Rerank functions based on how well they match the user's intent.

        Args:
            functions: List of functions to rerank
            intent: User's intent/query
            max_results: Maximum number of results to return (if None, return all)
            use_cache: Whether to use cached results

        Returns:
            Reranked list of functions
        """
        if not functions or not intent:
            return functions

        # Check cache first (thread-safe)
        cache_key = None
        if use_cache:
            cache_key = self._get_cache_key(intent, [f.name for f in functions[:20]])
            with _cache_lock:
                if cache_key in _rerank_cache:
                    cached_indices, timestamp = _rerank_cache[cache_key]
                    # Check if cache entry is still valid
                    if time.time() - timestamp < CACHE_TTL_SECONDS:
                        return self._apply_cached_ranking(functions, cached_indices, max_results)
                    else:
                        # Remove expired entry
                        del _rerank_cache[cache_key]

        try:
            # Prepare function metadata for the LLM
            function_metadata = [
                self._create_function_metadata(i, func)
                for i, func in enumerate(functions[:20])  # Limit to top 20 for efficiency
            ]

            # Create the reranking prompt
            prompt = self._create_reranking_prompt(intent, function_metadata)

            # Call the LLM for reranking with timeout and retry
            try:
                response = self.openai_client.with_options(
                    timeout=2.0,  # 2 second timeout
                    max_retries=1,  # One retry
                ).chat.completions.create(
                    model="gpt-4o-mini",  # Using a fast, efficient model for reranking
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a function matching expert. Analyze the user's intent and rank functions by relevance.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=500,
                )
            except Exception:
                # If LLM fails, return original order
                return functions[:max_results] if max_results else functions

            # Parse the response to get reranked indices
            reranked_indices = self._parse_reranking_response(
                response.choices[0].message.content, len(function_metadata)
            )

            # Cache the result if caching is enabled
            if use_cache:
                self._update_cache(cache_key, reranked_indices)

            # Reorder functions based on the reranked indices
            reranked_functions = []
            for idx in reranked_indices:
                if idx < len(functions):
                    reranked_functions.append(functions[idx])

            # Add any remaining functions not included in reranking
            for i, func in enumerate(functions):
                if i >= 20 or func not in reranked_functions:
                    reranked_functions.append(func)

            # Apply max_results limit if specified
            if max_results:
                reranked_functions = reranked_functions[:max_results]

            # Successfully reranked functions

            return reranked_functions

        except Exception as e:
            # Failed to rerank, fall back to original order
            # Fall back to original order if reranking fails
            return functions[:max_results] if max_results else functions

    def _create_function_metadata(self, index: int, func: Function) -> dict:
        """Create metadata dict for a function."""
        return {
            "index": index,
            "name": func.name,
            "description": func.description,
            "app_name": func.name.split("__")[0] if "__" in func.name else "unknown",
            "required_params": self._get_required_params(func.parameters),
        }

    def _get_required_params(self, parameters: dict) -> list[str]:
        """Extract required parameters from a function's parameter schema."""
        if not parameters or "properties" not in parameters:
            return []
        return parameters.get("required", [])[:5]  # Limit to first 5 for brevity

    def _create_reranking_prompt(self, intent: str, function_metadata: list[dict]) -> str:
        """Create a prompt for the LLM to rerank functions."""
        functions_str = json.dumps(function_metadata, indent=2)

        return f"""User Intent: "{intent}"

Functions to rank:
{functions_str}

Task: Analyze the user's intent and rank these functions by relevance. Consider:
1. Direct name/description match to the intent
2. Whether the function can fulfill the user's goal
3. Required parameters - penalize functions requiring data not mentioned by the user
4. Prefer functions from relevant services mentioned in the intent

Return ONLY a JSON array of indices in order of relevance (most relevant first).
Example: [2, 0, 5, 1, 3, 4]

Your response:"""

    def _parse_reranking_response(self, response: str, num_functions: int) -> list[int]:
        """Parse the LLM's reranking response to get ordered indices."""
        try:
            # Extract JSON array from response
            response = response.strip()
            if response.startswith("```"):
                # Handle markdown code blocks
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            # Parse the JSON array
            indices = json.loads(response.strip())

            # Validate indices
            if not isinstance(indices, list):
                raise ValueError("Response is not a list")

            # Filter out invalid indices and ensure uniqueness
            valid_indices = []
            seen = set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < num_functions and idx not in seen:
                    valid_indices.append(idx)
                    seen.add(idx)

            return valid_indices

        except Exception as e:
            # Failed to parse response, return original order
            # Return original order if parsing fails
            return list(range(num_functions))

    def _get_cache_key(self, intent: str, function_names: list[str]) -> str:
        """Generate a cache key for the reranking request."""
        content = f"{intent}|{'|'.join(function_names)}"
        return hashlib.md5(content.encode()).hexdigest()

    def _update_cache(self, key: str, indices: list[int]) -> None:
        """Update the cache with reranking results (thread-safe)."""
        with _cache_lock:
            # Remove expired entries first
            current_time = time.time()
            expired_keys = [
                k for k, (_, ts) in _rerank_cache.items()
                if current_time - ts > CACHE_TTL_SECONDS
            ]
            for k in expired_keys:
                del _rerank_cache[k]

            # LRU: if cache is still full, remove oldest entry
            if len(_rerank_cache) >= MAX_CACHE_SIZE:
                oldest_key = min(_rerank_cache.keys(), key=lambda k: _rerank_cache[k][1])
                del _rerank_cache[oldest_key]

            _rerank_cache[key] = (indices, current_time)

    def _apply_cached_ranking(
        self, functions: list[Function], cached_indices: list[int], max_results: int | None
    ) -> list[Function]:
        """Apply cached ranking indices to functions."""
        reranked = []
        for idx in cached_indices:
            if idx < len(functions):
                reranked.append(functions[idx])

        # Add any remaining functions
        for func in functions:
            if func not in reranked:
                reranked.append(func)

        return reranked[:max_results] if max_results else reranked


def rerank_with_context(
    functions: list[Function],
    intent: str,
    openai_client: OpenAI,
    agent_context: dict[str, Any] | None = None,
) -> list[Function]:
    """
    Convenience function to rerank functions with optional agent context.

    Args:
        functions: List of functions to rerank
        intent: User's intent
        openai_client: OpenAI client for LLM calls
        agent_context: Optional context about the agent's capabilities

    Returns:
        Reranked list of functions
    """
    reranker = FunctionReranker(openai_client)

    # Enhance intent with agent context if available
    enhanced_intent = intent
    if agent_context and agent_context.get("allowed_apps"):
        # This information can help the reranker prioritize functions from allowed apps
        # but for now we just use the basic reranking
        pass

    return reranker.rerank_functions(functions, enhanced_intent)