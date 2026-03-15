"""
Agentic bird identification using Anthropic Claude with tool calling.

Replaces the rigid OpenAI + MCP pipeline with a flexible agent loop where
Claude reasons about what data it needs and calls tools autonomously.
"""

import json
import logging
import re
import time
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam, TextBlock, ToolParam, ToolUseBlock

from ..settings import settings
from .ebird_client import ebird_client
from .web_search import web_search_client

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are Birdle, an expert bird identification assistant.
You help people identify birds from their descriptions.

You have tools to look up real-time eBird observation data and search the web.
Use them to ground your identification in evidence.

## How to identify

1. Read the description carefully — note colors, size, behavior, habitat, sounds.
2. Form initial hypotheses about what species this could be.
3. Use get_regional_birds to check what's common in the user's area.
4. If the description is unusual or doesn't match common regional birds,
   use web_search to investigate further.
5. Rank your candidates by likelihood. Consider:
   - How well the description matches the species' appearance/behavior
   - Whether the species is present in the region (eBird data)
   - Season and habitat appropriateness
6. Fetch images for your top 1-3 matches so the user can compare visually.

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

After reasoning and using tools, provide your final answer as JSON:

{
  "message": "Friendly explanation of your identification",
  "top_species": {
    "scientific_name": "Cardinalis cardinalis",
    "common_name": "Northern Cardinal",
    "confidence": "high",
    "reasoning": "Why this is your top match — reference eBird data and description"
  },
  "alternate_species": [
    {
      "scientific_name": "...",
      "common_name": "...",
      "confidence": "medium",
      "reasoning": "Why this is also possible"
    }
  ],
  "clarification": "Optional follow-up question if confidence is low"
}

Rules:
- Top 1-3 matches. Don't force 3 if only 1-2 are reasonable.
- Primary match should have highest confidence.
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
        "name": "get_species_image",
        "description": (
            "Get a photo of a bird species from Macaulay Library. "
            "Returns image URL and photographer credit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "species_code": {
                    "type": "string",
                    "description": "eBird species code (e.g. 'norcar' for Northern Cardinal).",
                },
            },
            "required": ["species_code"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for bird identification information. "
            "Useful when the description doesn't match common regional birds "
            "or you need more details about a species."
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

FALLBACK_RESPONSE: dict[str, Any] = {
    "message": "I wasn't able to identify the bird. Could you provide more details?",
    "top_species": None,
    "alternate_species": [],
    "clarification": "Please describe the bird's size, colors, and behavior in more detail.",
}

MAX_ITERATIONS = 8


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
        elif name == "get_species_image":
            image = await ebird_client.get_species_image(
                input_data["species_code"],
            )
            result = image if image is not None else {"error": "No image found"}
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
                    model=MODEL,
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
            logger.info(
                "Bird agent completed",
                extra={
                    "operation": "bird_agent_identify",
                    "total_latency_ms": round(latency_ms, 2),
                    "iterations": iterations,
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


# Module-level singleton
bird_agent = BirdAgent()
