"""
Tavily web search client for supplementary bird identification info.
"""

import logging
import time

from tavily import AsyncTavilyClient

from ..settings import settings

logger = logging.getLogger(__name__)


class WebSearchClient:
    """Thin wrapper around Tavily SDK with graceful error handling."""

    def __init__(self) -> None:
        self._client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search the web for bird identification information.

        Returns a list of {"title": str, "url": str, "content": str} dicts.
        Returns empty list on any error — web search is supplementary, not critical.
        """
        start_time = time.time()
        try:
            response = await self._client.search(query=query, max_results=max_results)
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in response.get("results", [])
            ]
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "Web search completed",
                extra={
                    "operation": "web_search",
                    "query_length": len(query),
                    "result_count": len(results),
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                },
            )
            return results
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"Web search failed: {e}",
                extra={
                    "operation": "web_search",
                    "latency_ms": round(latency_ms, 2),
                    "error_type": type(e).__name__,
                    "status": "error",
                },
            )
            return []


# Module-level singleton
web_search_client = WebSearchClient()
