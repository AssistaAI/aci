from abc import abstractmethod
from base64 import b64decode
from io import BytesIO
from typing import Any, Generic, override

import httpx
from httpx import HTTPStatusError

from aci.common.db.sql_models import Function
from aci.common.logging_setup import get_logger
from aci.common.schemas.function import FunctionExecutionResult, RestMetadata
from aci.common.schemas.security_scheme import (
    TCred,
    TScheme,
)
from aci.server.function_executors.base_executor import FunctionExecutor

logger = get_logger(__name__)


class RestFunctionExecutor(FunctionExecutor[TScheme, TCred], Generic[TScheme, TCred]):
    """
    Function executor for REST functions.
    """

    @abstractmethod
    def _inject_credentials(
        self,
        security_scheme: TScheme,
        security_credentials: TCred,
        headers: dict,
        query: dict,
        body: dict,
        cookies: dict,
    ) -> None:
        pass

    def _prepare_multipart_files(self, body: dict) -> dict:
        """
        Prepare multipart file upload data from body dict.
        Handles base64-encoded file data and converts it to the format expected by httpx.

        Expected body format:
        {
            "attachment": "base64_encoded_data",
            "filename": "example.txt"
        }

        Returns format expected by httpx files parameter:
        {
            "attachment": ("filename", file_bytes)
        }
        """
        files = {}
        filename = body.get("filename", "file")

        for key, value in body.items():
            # Skip the filename field - it will be used in the file tuple
            if key == "filename":
                continue

            # Check if this looks like a file field (has format: binary or is named attachment/file)
            if key in ["attachment", "file"] or (isinstance(value, str) and len(value) > 100):
                try:
                    # Try to decode as base64
                    file_bytes = b64decode(value)
                    # httpx expects: (filename, file_content)
                    files[key] = (filename, BytesIO(file_bytes))
                    logger.info(
                        f"Prepared file upload: key='{key}', filename='{filename}', size={len(file_bytes)} bytes"
                    )
                except Exception as e:
                    logger.warning(f"Failed to decode base64 file data for key '{key}': {e}")
                    # If not base64, pass as-is (might be a string field)
                    files[key] = (None, str(value))
            else:
                # Regular form field (not a file)
                files[key] = (None, str(value))

        return files

    @override
    def _execute(
        self,
        function: Function,
        function_input: dict,
        security_scheme: TScheme,
        security_credentials: TCred,
    ) -> FunctionExecutionResult:
        # Extract parameters by location
        path: dict = function_input.get("path", {})
        query: dict = function_input.get("query", {})
        headers: dict = function_input.get("header", {})
        cookies: dict = function_input.get("cookie", {})
        body: dict = function_input.get("body", {})

        logger.debug(
            f"Function input extracted: path={path}, query={query}, headers={headers}, "
            f"cookies={cookies}, body_keys={list(body.keys()) if body else []}"
        )

        protocol_data = RestMetadata.model_validate(function.protocol_data)
        # Construct URL with path parameters
        url = f"{protocol_data.server_url}{protocol_data.path}"
        if path:
            # Replace path parameters in URL
            for path_param_name, path_param_value in path.items():
                url = url.replace(f"{{{path_param_name}}}", str(path_param_value))

        # Merge protocol_data headers with function_input headers (function_input headers take precedence)
        if protocol_data.headers:
            headers = {**protocol_data.headers, **headers}

        self._inject_credentials(
            security_scheme, security_credentials, headers, query, body, cookies
        )

        # Check Content-Type to determine how to send body data
        content_type = headers.get("Content-Type", "") if headers else ""
        is_form_encoded = "application/x-www-form-urlencoded" in content_type.lower()
        is_multipart = "multipart/form-data" in content_type.lower()

        # Auto-detect file uploads: if body has attachment/file fields, assume multipart
        if not is_multipart and not is_form_encoded and body:
            has_file_field = any(key in body for key in ["attachment", "file", "upload"])
            if has_file_field:
                logger.info(
                    f"Auto-detecting multipart upload based on body fields: {list(body.keys())}"
                )
                is_multipart = True

        logger.info(
            f"Request encoding check: content_type='{content_type}', "
            f"is_multipart={is_multipart}, is_form_encoded={is_form_encoded}, "
            f"headers={headers}"
        )

        # For multipart/form-data, we need to let httpx handle the Content-Type header
        # (it will add the boundary parameter automatically)
        if is_multipart and headers:
            headers.pop("Content-Type", None)

        # Prepare files for multipart upload
        files = self._prepare_multipart_files(body) if body and is_multipart else None

        logger.info(
            f"Request preparation: is_multipart={is_multipart}, files={files is not None}, "
            f"body_size={len(body) if body else 0}"
        )

        request = httpx.Request(
            method=protocol_data.method,
            url=url,
            params=query if query else None,
            headers=headers if headers else None,
            cookies=cookies if cookies else None,
            data=body if body and is_form_encoded else None,
            files=files if is_multipart else None,
            json=body if body and not is_form_encoded and not is_multipart else None,
        )

        logger.info(
            f"Executing function via raw http request, function_name={function.name}, "
            f"method={request.method} url={request.url} "
        )

        return self._send_request(request)

    def _send_request(self, request: httpx.Request) -> FunctionExecutionResult:
        # TODO: one client for all requests? cache the client? concurrency control? async client?
        # TODO: add retry
        timeout = httpx.Timeout(10.0, read=30.0)
        with httpx.Client(timeout=timeout) as client:
            try:
                response = client.send(request)
            except Exception as e:
                logger.exception(f"Failed to send function execution http request, error={e}")
                return FunctionExecutionResult(success=False, error=str(e))

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.exception(f"HTTP error occurred for function execution, error={e}")
                return FunctionExecutionResult(
                    success=False, error=self._get_error_message(response, e)
                )

            return FunctionExecutionResult(success=True, data=self._get_response_data(response))

    def _get_response_data(self, response: httpx.Response) -> Any:
        """Get the response data from the response.
        If the response is json, return the json data, otherwise fallback to the text.
        """
        try:
            response_data = response.json() if response.content else {}
        except Exception as e:
            logger.exception(f"Error parsing function execution http response, error={e}")
            response_data = response.text

        return response_data

    def _get_error_message(self, response: httpx.Response, error: HTTPStatusError) -> str:
        """Get the error message from the response or fallback to the error message from the HTTPStatusError.
        Usually the response json contains more details about the error.
        """
        try:
            return str(response.json())
        except Exception:
            return str(error)
