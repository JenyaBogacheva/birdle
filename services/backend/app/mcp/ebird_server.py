#!/usr/bin/env python3
"""
eBird MCP Server for bird identification.

Provides tools to query eBird API for recent observations and species sightings.
"""

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

# eBird API configuration
EBIRD_API_BASE = "https://api.ebird.org/v2"

# Get eBird token from environment (standalone script doesn't use settings module)
EBIRD_TOKEN = os.getenv("EBIRD_TOKEN", "cqlorenascpl")

server = Server("bird-id-ebird")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """List available eBird tools."""
    return [
        types.Tool(
            name="get_recent_observations",
            description="Get recent bird observations for a region to help identify birds",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Region code like 'US', 'US-NY', 'US-CA'",
                        "default": "US",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Days back to search (1-30)",
                        "default": 14,
                        "minimum": 1,
                        "maximum": 30,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
            },
        ),
        types.Tool(
            name="get_species_sightings",
            description="Get recent sightings for a specific bird species",
            inputSchema={
                "type": "object",
                "properties": {
                    "species_code": {
                        "type": "string",
                        "description": "eBird species code (e.g. 'norcar' for Northern Cardinal)",
                    },
                    "region": {
                        "type": "string",
                        "description": "Region code",
                        "default": "US",
                    },
                },
                "required": ["species_code"],
            },
        ),
        types.Tool(
            name="search_species_by_name",
            description="Search for bird species by common or scientific name",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (common or scientific name)",
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls."""
    headers = {
        "Accept": "application/json",
        "X-eBirdApiToken": EBIRD_TOKEN,
    }

    try:
        if name == "get_recent_observations":
            region = arguments.get("region", "US")
            days = arguments.get("days", 14)
            max_results = arguments.get("max_results", 50)

            url = f"{EBIRD_API_BASE}/data/obs/{region}/recent"
            params = {"back": days}

            logger.info(f"Fetching recent observations for region={region}, days={days}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                # Format results
                result: dict[str, Any] = {
                    "region": region,
                    "days_searched": days,
                    "total_observations": len(data),
                    "species_observed": [],
                }

                # Group by species and show top results
                species_seen = {}
                for obs in data:
                    species_name = obs.get("comName", "Unknown")
                    if species_name not in species_seen:
                        species_seen[species_name] = {
                            "common_name": species_name,
                            "scientific_name": obs.get("sciName", ""),
                            "species_code": obs.get("speciesCode", ""),
                            "observation_count": 0,
                        }
                    species_seen[species_name]["observation_count"] += 1

                # Sort by observation count and limit results
                sorted_species = sorted(
                    species_seen.values(),
                    key=lambda x: x["observation_count"],
                    reverse=True,
                )
                result["species_observed"] = sorted_species[:max_results]

                logger.info(f"Found {len(result['species_observed'])} unique species")
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_species_sightings":
            species_code = arguments["species_code"]
            region = arguments.get("region", "US")

            url = f"{EBIRD_API_BASE}/data/obs/{region}/recent/{species_code}"

            logger.info(f"Fetching sightings for species={species_code}, region={region}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                species_result: dict[str, Any] = {
                    "species_code": species_code,
                    "species_name": data[0].get("comName", "") if data else "Not found",
                    "scientific_name": data[0].get("sciName", "") if data else "",
                    "region": region,
                    "total_sightings": len(data),
                    "recent_locations": [],
                }

                # Show recent sighting locations
                for obs in data[:10]:
                    species_result["recent_locations"].append(
                        {
                            "location": obs.get("locName", ""),
                            "date": obs.get("obsDt", ""),
                            "count": obs.get("howMany", "X"),
                            "latitude": obs.get("lat", 0),
                            "longitude": obs.get("lng", 0),
                        }
                    )

                logger.info(f"Found {len(data)} sightings for {species_code}")
                return [types.TextContent(type="text", text=json.dumps(species_result, indent=2))]

        elif name == "search_species_by_name":
            query = arguments["query"]

            # Use eBird taxonomy API
            url = f"{EBIRD_API_BASE}/ref/taxonomy/ebird"
            params = {"species": query, "fmt": "json"}

            logger.info(f"Searching species by name: {query}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                search_result: dict[str, Any] = {
                    "query": query,
                    "matches": [],
                }

                # Return matching species
                for species in data[:20]:  # Limit to 20 matches
                    search_result["matches"].append(
                        {
                            "common_name": species.get("comName", ""),
                            "scientific_name": species.get("sciName", ""),
                            "species_code": species.get("speciesCode", ""),
                            "category": species.get("category", ""),
                        }
                    )

                logger.info(f"Found {len(search_result['matches'])} species matches for: {query}")
                return [types.TextContent(type="text", text=json.dumps(search_result, indent=2))]

        else:
            logger.warning(f"Unknown tool requested: {name}")
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling eBird API: {e}")
        return [types.TextContent(type="text", text=f"eBird API error: {str(e)}")]
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the eBird MCP server."""
    from mcp.server import InitializationOptions, NotificationOptions

    logger.info("Starting eBird MCP server")

    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            InitializationOptions(
                server_name="bird-id-ebird",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(), experimental_capabilities={}
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
