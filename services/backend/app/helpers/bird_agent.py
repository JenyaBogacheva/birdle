"""
Agentic bird identification using Anthropic Claude with tool calling.

Replaces the rigid OpenAI + MCP pipeline with a flexible agent loop where
Claude reasons about what data it needs and calls tools autonomously.
"""

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam, TextBlock, ToolParam, ToolUseBlock

from ..settings import settings
from .ebird_client import ebird_client
from .web_search import web_search_client

logger = logging.getLogger(__name__)

GUARDRAIL_MODEL = "claude-haiku-4-5"
AGENT_MODEL = "claude-sonnet-4-6"

GUARDRAIL_PROMPT = (
    "Is the following user message a request to identify a bird or "
    "about bird watching/ornithology? Answer only YES or NO."
)

SYSTEM_PROMPT = """\
You are Birdle, an expert bird identification assistant.
You help people identify birds from their descriptions.

You have tools to look up real-time eBird observation data and search the web.
Use them to ground your identification in evidence.

## How to identify

1. Read the description carefully — note colors, size, behavior, habitat, sounds.
2. Form initial hypotheses about what species this could be.
3. Call get_regional_birds to check what's common in the user's area.
4. If the description is unusual or doesn't match common regional birds,
   call web_search to investigate further.
5. Produce your final identification as JSON.

## Efficiency

Be efficient with tool calls. Typically one call to get_regional_birds is enough.
Only use web_search when the bird is truly unusual or doesn't match regional data.
Do NOT fetch images — the system handles that separately after your response.

## Confidence levels

- HIGH: Description matches distinctive features + species is common in region
  Example: "bright red bird with crest at feeder" in US-NY → Northern Cardinal
- MEDIUM: Description fits multiple species, or species is uncommon but plausible
  Example: "small brown bird hopping on ground" in US-CA → could be several sparrows
- LOW: Description is vague, species is rare/unlikely, or conflicting features
  Example: "dark bird flying overhead" → too many possibilities

## When confidence is LOW

Ask a specific clarifying question. Focus on the most distinguishing
feature that would narrow it down.

## Region codes

When calling get_regional_birds, convert the user's location to an eBird region code:
- Countries: ISO 3166-1 alpha-2 (AU, GB, RS, NZ, BR, IN, JP, FR, etc.)
- US states: US-XX (US-NY, US-CA)
- Canadian provinces: CA-XX (CA-ON, CA-BC)
- Australian states: AU-XX (AU-NSW, AU-VIC)

## Output format

Provide your final answer as JSON:

{
  "message": "Friendly explanation of your identification",
  "top_species": {
    "scientific_name": "Cardinalis cardinalis",
    "common_name": "Northern Cardinal",
    "species_code": "norcar",
    "confidence": "high",
    "reasoning": "Why this is your top match — reference eBird data and description"
  },
  "alternate_species": [
    {
      "scientific_name": "...",
      "common_name": "...",
      "species_code": "...",
      "confidence": "medium",
      "reasoning": "Why this is also possible"
    }
  ],
  "clarification": "Optional follow-up question if confidence is low"
}

Rules:
- Top 1-3 matches. Don't force 3 if only 1-2 are reasonable.
- Primary match should have highest confidence.
- Include species_code from eBird data when available (used for images).
- You CAN identify birds not in eBird data — just note it in reasoning.
- If you cannot identify at all, set top_species to null and ask a clarifying question.
- Be friendly, be honest about uncertainty, and show your reasoning.\
"""

TOOLS: list[ToolParam] = [
    {
        "name": "get_regional_birds",
        "description": (
            "Get recently observed bird species in a region from eBird. "
            "Returns species names, scientific names, species codes, and observation counts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": (
                        "eBird region code. Countries use ISO 3166-1 alpha-2 (e.g. US, GB, AU). "
                        "US states use US-XX (e.g. US-NY). Canadian provinces use CA-XX."
                    ),
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back for observations. Default 14.",
                    "default": 14,
                },
            },
            "required": ["region"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for bird identification information. "
            "Only use when the bird is truly unusual or doesn't match regional eBird data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query about bird identification.",
                },
            },
            "required": ["query"],
        },
    },
]

NOT_BIRD_RESPONSE: dict[str, Any] = {
    "message": (
        "I'm Birdle, a bird identification assistant! "
        "I can only help with identifying birds. "
        "Please describe a bird you've seen and I'll do my best to identify it."
    ),
    "top_species": None,
    "alternate_species": [],
    "clarification": "What did the bird look like? Include details like color, size, and behavior.",
}

FALLBACK_RESPONSE: dict[str, Any] = {
    "message": "I wasn't able to identify the bird. Could you provide more details?",
    "top_species": None,
    "alternate_species": [],
    "clarification": "Please describe the bird's size, colors, and behavior in more detail.",
}

MAX_ITERATIONS = 4


async def _execute_tool(name: str, input_data: dict[str, Any]) -> Any:
    """Execute a single tool call and return the result."""
    start_time = time.time()
    result: Any
    try:
        if name == "get_regional_birds":
            result = await ebird_client.get_regional_birds(
                region=input_data["region"],
                days=input_data.get("days", 14),
            )
        elif name == "web_search":
            result = await web_search_client.search(input_data["query"])
        else:
            result = {"error": f"Unknown tool: {name}"}

        latency_ms = (time.time() - start_time) * 1000
        logger.info(
            "Tool call executed",
            extra={
                "operation": "tool_call",
                "tool_name": name,
                "latency_ms": round(latency_ms, 2),
                "status": "success",
            },
        )
        return result

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.warning(
            f"Tool call failed: {e}",
            extra={
                "operation": "tool_call",
                "tool_name": name,
                "latency_ms": round(latency_ms, 2),
                "status": "error",
                "error_type": type(e).__name__,
            },
        )
        return {"error": str(e)}


def _tool_result_summary(tool_name: str, input_data: dict[str, Any], result: Any) -> str:
    """Generate a human-readable summary of a tool call result."""
    if isinstance(result, dict) and "error" in result:
        return f"Tool {tool_name} failed: {result['error']}"

    if tool_name == "get_regional_birds":
        species = result.get("species_observed", []) if isinstance(result, dict) else []
        region = input_data.get("region", "unknown region")
        return f"Found {len(species)} species in {region}"

    if tool_name == "web_search":
        count = len(result) if isinstance(result, list) else 0
        query = input_data.get("query", "")
        return f"Found {count} results for '{query}'"

    return f"Tool {tool_name} completed"


def _parse_response(response: anthropic.types.Message) -> dict[str, Any]:
    """Extract and parse the JSON identification result from Claude's response."""
    for block in response.content:
        if not isinstance(block, TextBlock):
            continue

        text = block.text

        # Try direct JSON parse
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fences
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

    logger.warning(
        "Failed to parse agent response as JSON",
        extra={"operation": "parse_response", "status": "fallback"},
    )
    return dict(FALLBACK_RESPONSE)


class BirdAgent:
    """Agentic bird identification using Claude with tool calling."""

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def _is_bird_related(self, description: str) -> bool:
        """Quick Haiku check: is this about birds? Returns True if yes."""
        try:
            response = await self._client.messages.create(
                model=GUARDRAIL_MODEL,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": f"{GUARDRAIL_PROMPT}\n\n{description}"},
                ],
            )
            text = next(
                (b.text for b in response.content if isinstance(b, TextBlock)),
                "YES",
            )
            return "YES" in text.upper()
        except Exception as e:
            logger.warning(f"Guardrail check failed, allowing request: {e}")
            return True  # fail open

    async def identify(
        self,
        description: str,
        location: str,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Run the bird identification agent loop."""
        start_time = time.time()

        logger.info(
            "Bird agent started",
            extra={
                "operation": "bird_agent_identify",
                "description_length": len(description),
                "location": location,
                "status": "started",
            },
        )

        # Guardrail: reject non-bird queries cheaply via Haiku
        if not await self._is_bird_related(description):
            logger.info(
                "Non-bird query rejected by guardrail",
                extra={"operation": "bird_agent_identify", "status": "rejected"},
            )
            return dict(NOT_BIRD_RESPONSE)

        # Build user message
        user_message = (
            f"I observed a bird...\n\n" f"Description: {description}\n" f"Location: {location}"
        )
        if observed_at:
            user_message += f"\nObserved at: {observed_at}"

        messages: list[MessageParam] = [
            {"role": "user", "content": user_message},
        ]

        try:
            response: anthropic.types.Message | None = None
            iterations = 0

            for iteration in range(MAX_ITERATIONS):
                iterations = iteration + 1

                response = await self._client.messages.create(
                    model=AGENT_MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    thinking={"type": "adaptive"},
                    messages=messages,
                )

                # If Claude is done (no more tool calls), break
                if response.stop_reason == "end_turn":
                    break

                # Extract tool use blocks
                tool_use_blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
                if not tool_use_blocks:
                    break

                # Append assistant response to conversation
                messages.append(
                    {"role": "assistant", "content": cast(Any, response.content)},
                )

                # Execute tools and collect results
                tool_results: list[dict[str, Any]] = []
                for tool_block in tool_use_blocks:
                    result = await _execute_tool(
                        tool_block.name,
                        tool_block.input,
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": (
                                json.dumps(result)
                                if isinstance(result, (dict, list))
                                else str(result)
                            ),
                        }
                    )

                messages.append({"role": "user", "content": cast(Any, tool_results)})

            latency_ms = (time.time() - start_time) * 1000
            usage = response.usage if response else None
            logger.info(
                "Bird agent completed",
                extra={
                    "operation": "bird_agent_identify",
                    "total_latency_ms": round(latency_ms, 2),
                    "iterations": iterations,
                    "input_tokens": usage.input_tokens if usage else 0,
                    "output_tokens": usage.output_tokens if usage else 0,
                    "status": "success",
                },
            )

            if response is None:
                return dict(FALLBACK_RESPONSE)

            return _parse_response(response)

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Bird agent failed: {e}",
                extra={
                    "operation": "bird_agent_identify",
                    "total_latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return dict(FALLBACK_RESPONSE)

    async def identify_stream(
        self,
        description: str,
        location: str,
        observed_at: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run bird identification with streaming events.

        Yields event dicts with a 'type' field:
        - status: {"type": "status", "message": str}
        - thinking: {"type": "thinking", "content": str}
        - tool_call: {"type": "tool_call", "tool": str, "input": dict}
        - tool_result: {"type": "tool_result", "tool": str, "summary": str}
        - result: {"type": "result", "data": dict}
        - error: {"type": "error", "message": str}
        """
        start_time = time.time()

        try:
            # Step 1: Guardrail
            yield {"type": "status", "message": "Checking your description..."}

            if not await self._is_bird_related(description):
                logger.info(
                    "Non-bird query rejected by guardrail (streaming)",
                    extra={"operation": "bird_agent_stream", "status": "rejected"},
                )
                yield {"type": "result", "data": dict(NOT_BIRD_RESPONSE)}
                return

            # Step 2: Build user message
            yield {"type": "status", "message": "Looking up birds in your area..."}

            user_message = (
                f"I observed a bird...\n\n" f"Description: {description}\n" f"Location: {location}"
            )
            if observed_at:
                user_message += f"\nObserved at: {observed_at}"

            messages: list[MessageParam] = [
                {"role": "user", "content": user_message},
            ]

            # Step 3: Agent loop with streaming
            final_message = None
            iterations = 0

            for iteration in range(MAX_ITERATIONS):
                iterations = iteration + 1

                async with self._client.messages.stream(
                    model=AGENT_MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    thinking={"type": "adaptive"},
                    messages=messages,
                ) as stream:
                    # Process streaming events
                    async for event in stream:
                        if hasattr(event, "type") and event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "thinking_delta":
                                yield {"type": "thinking", "content": delta.thinking}
                            # Text deltas are part of the final JSON — don't stream

                    final_message = await stream.get_final_message()

                # Check if done
                if final_message.stop_reason == "end_turn":
                    break

                # Extract tool use blocks
                tool_use_blocks = [b for b in final_message.content if isinstance(b, ToolUseBlock)]
                if not tool_use_blocks:
                    break

                # Append assistant response to conversation
                messages.append(
                    {"role": "assistant", "content": cast(Any, final_message.content)},
                )

                # Execute tools and yield events
                tool_results: list[dict[str, Any]] = []
                for tool_block in tool_use_blocks:
                    yield {
                        "type": "tool_call",
                        "tool": tool_block.name,
                        "input": tool_block.input,
                    }

                    result = await _execute_tool(tool_block.name, tool_block.input)

                    summary = _tool_result_summary(tool_block.name, tool_block.input, result)
                    yield {
                        "type": "tool_result",
                        "tool": tool_block.name,
                        "summary": summary,
                    }

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": (
                                json.dumps(result)
                                if isinstance(result, (dict, list))
                                else str(result)
                            ),
                        }
                    )

                messages.append({"role": "user", "content": cast(Any, tool_results)})

                if iteration < MAX_ITERATIONS - 1:
                    yield {"type": "status", "message": "Narrowing it down..."}

            latency_ms = (time.time() - start_time) * 1000
            usage = final_message.usage if final_message else None
            logger.info(
                "Bird agent stream completed",
                extra={
                    "operation": "bird_agent_stream",
                    "total_latency_ms": round(latency_ms, 2),
                    "iterations": iterations,
                    "input_tokens": usage.input_tokens if usage else 0,
                    "output_tokens": usage.output_tokens if usage else 0,
                    "status": "success",
                },
            )

            if final_message is None:
                yield {"type": "result", "data": dict(FALLBACK_RESPONSE)}
                return

            parsed = _parse_response(final_message)

            # Yield parsed result — images are fetched by the route handler
            # before constructing the final RecommendationResponse
            yield {"type": "result", "data": parsed}

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Bird agent stream failed: {e}",
                extra={
                    "operation": "bird_agent_stream",
                    "total_latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            yield {
                "type": "error",
                "message": "An unexpected error occurred. Please try again.",
            }


# Module-level singleton
bird_agent = BirdAgent()
