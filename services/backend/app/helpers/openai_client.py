"""
OpenAI API client with structured responses and error handling.
"""

import json
import logging
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

        while attempts <= max_retries:
            try:
                logger.info(
                    f"OpenAI request attempt {attempts + 1}/{max_retries + 1}, "
                    f"model={self.model}"
                )

                response = await self.client.chat.completions.create(**request_params)

                # Log metrics
                usage = response.usage
                if usage:
                    logger.info(
                        f"OpenAI response: tokens={usage.total_tokens} "
                        f"(prompt={usage.prompt_tokens}, "
                        f"completion={usage.completion_tokens})"
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
                logger.warning(f"OpenAI error (attempt {attempts}): {e}")

                # Don't retry on rate limit or invalid request
                if hasattr(e, "status_code") and e.status_code in [400, 401, 429]:
                    logger.error(f"Non-retryable OpenAI error: {e}")
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
        Check if content passes OpenAI moderation.

        Args:
            text: Content to moderate

        Returns:
            True if content is safe, False if flagged

        Raises:
            OpenAIError: On API errors
        """
        try:
            logger.info("Running content moderation check")
            response = await self.client.moderations.create(input=text)

            flagged = response.results[0].flagged
            if flagged:
                categories = response.results[0].categories
                logger.warning(f"Content flagged by moderation: {categories}")

            return not flagged

        except OpenAIError as e:
            logger.error(f"Moderation check failed: {e}")
            # Fail open - don't block on moderation errors
            return True


# Singleton instance
openai_client = OpenAIClient()
