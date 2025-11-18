"""
Simple MCP client for communicating with the eBird MCP server.
Uses direct stdio communication like the original working example.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Timeout configurations for resilience
TOOL_CALL_TIMEOUT = 30.0  # Timeout for individual tool calls
INIT_TIMEOUT = 5.0  # Timeout for MCP initialization


class eBirdMCPHelper:  # noqa: N801 - eBird is a proper brand name
    """Helper for interacting with eBird data via MCP using direct stdio."""

    def __init__(self):
        """Initialize eBird MCP helper."""
        # Path to the eBird MCP server script
        server_path = Path(__file__).parent.parent / "mcp" / "ebird_server.py"
        self.server_path = str(server_path)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._started = False

    async def ensure_started(self):
        """Ensure the MCP server is started and initialized."""
        if self._started and self.process:
            return

        logger.info(f"Starting eBird MCP server: {self.server_path}")

        # Start the MCP server as subprocess with stdio
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            self.server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        logger.info(f"eBird MCP server started with PID: {self.process.pid}")

        # Send initialization handshake
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bird-id-backend", "version": "0.1.0"},
            },
            "id": 0,
        }

        logger.info("Sending MCP initialization")
        init_line = json.dumps(init_request) + "\n"
        self.process.stdin.write(init_line.encode())
        await self.process.stdin.drain()

        # Read initialization response
        init_response = await asyncio.wait_for(self.process.stdout.readline(), timeout=INIT_TIMEOUT)

        if init_response:
            response_data = json.loads(init_response.decode())
            server_info = response_data.get("result", {}).get("serverInfo", {})
            server_name = server_info.get("name", "unknown")
            logger.info(f"MCP initialized: {server_name}")

        # Send initialized notification
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        notif_line = json.dumps(initialized_notification) + "\n"
        self.process.stdin.write(notif_line.encode())
        await self.process.stdin.drain()

        self._started = True
        logger.info("eBird MCP server fully initialized")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call an MCP tool directly via JSON-RPC with structured logging.

        This uses the simple approach from the working example.
        """
        await self.ensure_started()

        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("MCP server not running")

        # Simple JSON-RPC call (not using full SDK initialization)
        # Just send tool call directly to the server
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": 1,
        }

        start_time = time.time()
        logger.info(
            "MCP tool call started",
            extra={
                "tool": tool_name,
                "operation": "call_tool",
                "arguments": arguments,
            },
        )

        try:
            # Send request
            request_line = json.dumps(request) + "\n"
            self.process.stdin.write(request_line.encode())
            await self.process.stdin.drain()

            # Read response with timeout
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=TOOL_CALL_TIMEOUT
            )

            if not response_line:
                raise RuntimeError("MCP server closed connection")

            response = json.loads(response_line.decode())
            latency_ms = (time.time() - start_time) * 1000

            logger.info(
                "MCP tool call succeeded",
                extra={
                    "tool": tool_name,
                    "operation": "call_tool",
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                },
            )

            return response.get("result", {})

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                "MCP tool call timeout",
                extra={
                    "tool": tool_name,
                    "operation": "call_tool",
                    "latency_ms": round(latency_ms, 2),
                    "status": "timeout",
                    "timeout_seconds": TOOL_CALL_TIMEOUT,
                },
            )
            raise RuntimeError(f"Timeout calling MCP tool '{tool_name}' after {TOOL_CALL_TIMEOUT}s")
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"MCP tool call failed: {e}",
                extra={
                    "tool": tool_name,
                    "operation": "call_tool",
                    "latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    def _empty_observations_fallback(self, region: str, days: int) -> dict[str, Any]:
        """
        Return empty observations fallback response.

        Args:
            region: Region code
            days: Days searched

        Returns:
            Empty observations structure
        """
        return {
            "region": region,
            "days_searched": days,
            "total_observations": 0,
            "species_observed": [],
        }

    async def get_recent_observations(
        self, region: str = "US", days: int = 14, max_results: int = 50
    ) -> dict[str, Any]:
        """
        Get recent bird observations for a region with graceful fallbacks.

        Args:
            region: Region code (e.g., 'US', 'US-NY')
            days: Days back to search (1-30)
            max_results: Maximum results to return

        Returns:
            Dictionary with observation data (empty structure on errors)
        """
        start_time = time.time()

        try:
            result = await self.call_tool(
                "get_recent_observations",
                {"region": region, "days": days, "max_results": max_results},
            )

            # The MCP server returns TextContent in result.content
            if result and "content" in result:
                content_list = result["content"]
                if isinstance(content_list, list) and len(content_list) > 0:
                    # First content item should have the text
                    text_data = content_list[0].get("text", "{}")
                    parsed: dict[str, Any] = json.loads(text_data)
                    species_count = len(parsed.get("species_observed", []))
                    latency_ms = (time.time() - start_time) * 1000

                    logger.info(
                        f"Retrieved {species_count} species observations",
                        extra={
                            "operation": "get_recent_observations",
                            "region": region,
                            "species_count": species_count,
                            "latency_ms": round(latency_ms, 2),
                            "status": "success",
                        },
                    )
                    return parsed

            # Empty or unexpected format - return fallback
            logger.warning(
                "MCP returned unexpected format, using empty fallback",
                extra={"operation": "get_recent_observations", "region": region},
            )
            return self._empty_observations_fallback(region, days)

        except RuntimeError as e:
            # Timeout or connection error - return fallback
            logger.warning(
                f"MCP call failed, using empty fallback: {e}",
                extra={"operation": "get_recent_observations", "region": region, "error": str(e)},
            )
            return self._empty_observations_fallback(region, days)

        except Exception as e:
            # Unexpected error - return fallback
            logger.error(
                f"Unexpected error getting observations: {e}",
                extra={"operation": "get_recent_observations", "region": region},
                exc_info=True,
            )
            return self._empty_observations_fallback(region, days)

    async def get_species_image(self, species_code: str) -> Optional[dict[str, Any]]:
        """
        Get top-rated image for a species from Macaulay Library with graceful fallbacks.

        Args:
            species_code: eBird species code (e.g., 'norcar')

        Returns:
            Dictionary with image_url and photographer, or None if not found/on error
        """
        if not species_code:
            logger.warning("No species code provided for image fetch")
            return None

        start_time = time.time()

        try:
            result = await self.call_tool("get_species_image", {"species_code": species_code})

            # Parse the MCP response
            if result and "content" in result:
                content_list = result["content"]
                if isinstance(content_list, list) and len(content_list) > 0:
                    text_data = content_list[0].get("text", "{}")
                    parsed: dict[str, Any] = json.loads(text_data)

                    # Return None if no image found
                    if parsed.get("image_url"):
                        latency_ms = (time.time() - start_time) * 1000
                        logger.info(
                            "Retrieved image for species",
                            extra={
                                "operation": "get_species_image",
                                "species_code": species_code,
                                "latency_ms": round(latency_ms, 2),
                                "status": "success",
                            },
                        )
                        return {
                            "image_url": parsed["image_url"],
                            "photographer": parsed.get("photographer", "Unknown"),
                        }
                    else:
                        logger.info(
                            "No image available for species",
                            extra={
                                "operation": "get_species_image",
                                "species_code": species_code,
                                "status": "not_found",
                            },
                        )
                        return None

            logger.warning(
                "MCP returned unexpected format for image",
                extra={"operation": "get_species_image", "species_code": species_code},
            )
            return None

        except RuntimeError as e:
            # Timeout or connection error - return None (image is optional)
            logger.warning(
                f"MCP call failed for image, continuing without image: {e}",
                extra={
                    "operation": "get_species_image",
                    "species_code": species_code,
                    "error": str(e),
                },
            )
            return None

        except Exception as e:
            # Unexpected error - return None (image is optional)
            logger.warning(
                f"Error fetching image, continuing without image: {e}",
                extra={"operation": "get_species_image", "species_code": species_code},
            )
            return None

    async def close(self):
        """Close the MCP server."""
        if self._started and self.process:
            logger.info("Stopping eBird MCP server")
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("MCP server didn't stop gracefully, killing")
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")
            finally:
                self.process = None
                self._started = False


# Singleton instance
ebird_helper = eBirdMCPHelper()
