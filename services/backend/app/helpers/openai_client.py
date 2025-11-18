"""
OpenAI API client with structured responses and error handling.
"""

import json
import logging
import time
from typing import Any, Optional

from openai import AsyncOpenAI, OpenAIError

from ..settings import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    """OpenAI API client with retry logic and structured response parsing."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"  # Cost-effective for MVP
        self.temperature = 0.4  # Per vision.md §6

    async def chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        response_format: Optional[dict[str, Any]] = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """
        Send a chat completion request with retry logic.

        Args:
            system_prompt: System message defining assistant behavior
            user_message: User message with the query
            response_format: Optional JSON schema for structured output
            max_retries: Number of retries on transient errors (per vision.md §6)

        Returns:
            Parsed response as dict

        Raises:
            OpenAIError: On non-transient errors or after max retries
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        request_params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        # Use JSON mode if schema provided
        if response_format:
            request_params["response_format"] = {"type": "json_object"}

        attempts = 0
        last_error = None
        start_time = time.time()

        while attempts <= max_retries:
            try:
                logger.info(
                    f"OpenAI request attempt {attempts + 1}/{max_retries + 1}",
                    extra={
                        "operation": "chat_completion",
                        "model": self.model,
                        "attempt": attempts + 1,
                        "max_attempts": max_retries + 1,
                    },
                )

                response = await self.client.chat.completions.create(**request_params)
                latency_ms = (time.time() - start_time) * 1000

                # Log metrics with structured data
                usage = response.usage
                if usage:
                    logger.info(
                        "OpenAI response successful",
                        extra={
                            "operation": "chat_completion",
                            "model": self.model,
                            "latency_ms": round(latency_ms, 2),
                            "total_tokens": usage.total_tokens,
                            "prompt_tokens": usage.prompt_tokens,
                            "completion_tokens": usage.completion_tokens,
                            "status": "success",
                        },
                    )

                # Extract content
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from OpenAI")

                # Parse JSON if structured format requested
                if response_format:
                    try:
                        parsed: dict[str, Any] = json.loads(content)
                        logger.info("Successfully parsed structured response")
                        return parsed
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        logger.error(f"Raw content: {content[:500]}")
                        raise ValueError(f"Invalid JSON response: {e}") from e

                # Return plain text response
                return {"content": content}

            except OpenAIError as e:
                last_error = e
                attempts += 1
                latency_ms = (time.time() - start_time) * 1000

                # Log with structured data
                logger.warning(
                    f"OpenAI error (attempt {attempts})",
                    extra={
                        "operation": "chat_completion",
                        "model": self.model,
                        "attempt": attempts,
                        "latency_ms": round(latency_ms, 2),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "status": "retry" if attempts <= max_retries else "failed",
                    },
                )

                # Don't retry on rate limit or invalid request
                if hasattr(e, "status_code") and e.status_code in [400, 401, 429]:
                    logger.error(
                        "Non-retryable OpenAI error",
                        extra={
                            "operation": "chat_completion",
                            "status_code": e.status_code,
                            "error": str(e),
                        },
                    )
                    raise

                if attempts > max_retries:
                    logger.error("Max retries exceeded for OpenAI request")
                    raise

        # Should not reach here, but handle gracefully
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected error in OpenAI client")

    async def moderate_content(self, text: str) -> bool:
        """
        Check if content passes OpenAI moderation with structured logging.

        Args:
            text: Content to moderate

        Returns:
            True if content is safe, False if flagged

        Raises:
            OpenAIError: On API errors
        """
        start_time = time.time()

        try:
            logger.info(
                "Running content moderation check",
                extra={"operation": "moderate_content", "text_length": len(text)},
            )
            response = await self.client.moderations.create(input=text)
            latency_ms = (time.time() - start_time) * 1000

            flagged = response.results[0].flagged
            if flagged:
                categories = response.results[0].categories
                logger.warning(
                    "Content flagged by moderation",
                    extra={
                        "operation": "moderate_content",
                        "latency_ms": round(latency_ms, 2),
                        "flagged": True,
                        "categories": str(categories),
                        "status": "flagged",
                    },
                )
            else:
                logger.info(
                    "Content passed moderation",
                    extra={
                        "operation": "moderate_content",
                        "latency_ms": round(latency_ms, 2),
                        "status": "passed",
                    },
                )

            return not flagged

        except OpenAIError as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Moderation check failed: {e}",
                extra={
                    "operation": "moderate_content",
                    "latency_ms": round(latency_ms, 2),
                    "error": str(e),
                    "status": "error",
                },
            )
            # Fail open - don't block on moderation errors
            return True


# Singleton instance
openai_client = OpenAIClient()
