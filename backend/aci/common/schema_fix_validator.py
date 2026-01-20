"""
Schema Fix Validator

Uses LLM (GPT-5 Codex) to validate if detected schema fixes are legitimate API parameters.
"""

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from aci.common.db.sql_models import Function, SchemaFix
from aci.common.enums import SchemaFixStatus
from aci.common.logging_setup import get_logger
from aci.common.schema_fix_detector import SchemaFixCandidate

logger = get_logger(__name__)

# Confidence thresholds
AUTO_APPROVE_THRESHOLD = 0.9  # >= 0.9 auto-approve
MANUAL_REVIEW_THRESHOLD = 0.7  # 0.7 - 0.9 manual review
AUTO_REJECT_THRESHOLD = 0.3  # < 0.3 auto-reject

# Default LLM model - GPT-5.2 as specified
DEFAULT_LLM_MODEL = "gpt-5.2"


@dataclass
class SchemaFixValidationResult:
    """Result of LLM validation for a schema fix."""

    decision: SchemaFixStatus  # APPROVED, REJECTED, or MANUAL_REVIEW
    confidence: float  # 0.0 to 1.0
    reasoning: str
    suggested_schema: dict[str, Any] | None = None


class SchemaFixValidator:
    """
    Validates schema fix candidates using LLM.

    Uses GPT-5 Codex (or fallback) to determine if a detected missing property
    is a legitimate API parameter that should be added to the schema.
    """

    def __init__(self, openai_client: OpenAI, model: str = DEFAULT_LLM_MODEL):
        """
        Initialize the validator.

        Args:
            openai_client: OpenAI client instance
            model: The LLM model to use for validation
        """
        self.openai_client = openai_client
        self.model = model

    def validate_fix(
        self,
        function: Function,
        fix: SchemaFix | SchemaFixCandidate,
    ) -> SchemaFixValidationResult:
        """
        Validate a schema fix candidate using LLM.

        Args:
            function: The function the fix is for
            fix: The schema fix to validate

        Returns:
            SchemaFixValidationResult with decision, confidence, and reasoning
        """
        logger.info(
            f"Validating schema fix, function={function.name}, "
            f"property={fix.property_name}, path={fix.property_path}"
        )

        prompt = self._build_validation_prompt(function, fix)

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for consistent results
            )

            response_text = response.choices[0].message.content
            if not response_text:
                logger.warning("Empty response from LLM")
                return SchemaFixValidationResult(
                    decision=SchemaFixStatus.MANUAL_REVIEW,
                    confidence=0.5,
                    reasoning="LLM returned empty response",
                )

            return self._parse_llm_response(response_text)

        except Exception as e:
            logger.exception(f"Error validating schema fix: {e}")
            return SchemaFixValidationResult(
                decision=SchemaFixStatus.MANUAL_REVIEW,
                confidence=0.5,
                reasoning=f"Error during LLM validation: {e!s}",
            )

    def _get_system_prompt(self) -> str:
        """Get the system prompt for schema fix validation."""
        return """You are an expert API schema validator. Your task is to determine if a detected
missing property in an API function schema is a legitimate API parameter that should be added.

You will be given:
1. Function name and description
2. Current function parameters schema
3. The missing property name and its location in the schema
4. The inferred schema for the missing property (based on the value that was passed)

Your job is to determine:
- Is this property a valid API parameter that the API likely accepts?
- Or is it likely a hallucination/mistake from an AI agent?

Consider:
- Does the property name make sense for this API?
- Does it follow common API naming conventions?
- Is there documentation evidence (in the description or existing params) suggesting this param exists?
- Is the inferred type reasonable for this parameter?

Respond with a JSON object containing:
{
    "decision": "APPROVE" | "REJECT" | "MANUAL_REVIEW",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation of your decision",
    "suggested_schema": { ... } | null  // Improved schema if you have suggestions
}

Guidelines:
- APPROVE (confidence >= 0.9): You are highly confident this is a valid API parameter
- MANUAL_REVIEW (confidence 0.7-0.9): Likely valid but needs human confirmation
- REJECT (confidence < 0.3): Almost certainly not a valid parameter
- For middle confidence (0.3-0.7), use MANUAL_REVIEW"""

    def _build_validation_prompt(
        self,
        function: Function,
        fix: SchemaFix | SchemaFixCandidate,
    ) -> str:
        """Build the validation prompt for the LLM."""
        # Get the property schema
        if isinstance(fix, SchemaFix):
            property_schema = fix.property_schema
        else:
            property_schema = fix.property_schema

        prompt = f"""Please validate if this missing property should be added to the function schema.

## Function Information
- **Name**: {function.name}
- **Description**: {function.description}

## Current Parameters Schema
```json
{json.dumps(function.parameters, indent=2)}
```

## Missing Property
- **Property Path**: {fix.property_path}
- **Property Name**: {fix.property_name}
- **Inferred Schema**:
```json
{json.dumps(property_schema, indent=2)}
```

## Context
This property was detected when an AI agent tried to call this function with this parameter.
The function rejected it because `additionalProperties: false` was set in the schema.

Please determine if this is a legitimate API parameter that should be added to the schema,
or if it's likely a hallucination from the AI agent."""

        return prompt

    def _parse_llm_response(self, response_text: str) -> SchemaFixValidationResult:
        """Parse the LLM response into a validation result."""
        try:
            data = json.loads(response_text)

            decision_str = data.get("decision", "MANUAL_REVIEW").upper()
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "No reasoning provided")
            suggested_schema = data.get("suggested_schema")

            # Map decision string to enum
            if decision_str == "APPROVE":
                decision = SchemaFixStatus.APPROVED
            elif decision_str == "REJECT":
                decision = SchemaFixStatus.REJECTED
            else:
                decision = SchemaFixStatus.MANUAL_REVIEW

            # Override decision based on confidence thresholds
            if confidence >= AUTO_APPROVE_THRESHOLD and decision != SchemaFixStatus.REJECTED:
                decision = SchemaFixStatus.APPROVED
            elif confidence < AUTO_REJECT_THRESHOLD and decision != SchemaFixStatus.APPROVED:
                decision = SchemaFixStatus.REJECTED
            elif AUTO_REJECT_THRESHOLD <= confidence < AUTO_APPROVE_THRESHOLD:
                if decision == SchemaFixStatus.APPROVED and confidence < MANUAL_REVIEW_THRESHOLD:
                    decision = SchemaFixStatus.MANUAL_REVIEW

            return SchemaFixValidationResult(
                decision=decision,
                confidence=confidence,
                reasoning=reasoning,
                suggested_schema=suggested_schema,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}, response={response_text}")
            return SchemaFixValidationResult(
                decision=SchemaFixStatus.MANUAL_REVIEW,
                confidence=0.5,
                reasoning=f"Failed to parse LLM response: {e!s}",
            )

    def validate_fixes_batch(
        self,
        function: Function,
        fixes: list[SchemaFix | SchemaFixCandidate],
    ) -> list[SchemaFixValidationResult]:
        """
        Validate multiple schema fixes for the same function.

        Args:
            function: The function the fixes are for
            fixes: List of schema fixes to validate

        Returns:
            List of validation results in the same order as input
        """
        results = []
        for fix in fixes:
            result = self.validate_fix(function, fix)
            results.append(result)
        return results


def determine_auto_action(confidence: float) -> SchemaFixStatus:
    """
    Determine the automatic action based on confidence score.

    Args:
        confidence: The LLM confidence score (0.0 to 1.0)

    Returns:
        SchemaFixStatus indicating the automatic action
    """
    if confidence >= AUTO_APPROVE_THRESHOLD:
        return SchemaFixStatus.APPROVED
    elif confidence < AUTO_REJECT_THRESHOLD:
        return SchemaFixStatus.REJECTED
    else:
        return SchemaFixStatus.MANUAL_REVIEW
