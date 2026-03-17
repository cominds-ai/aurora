import logging
from typing import Optional

import httpx

from app.domain.external.search import SearchEngine
from app.domain.models.app_config import SearchConfig
from app.domain.models.search import SearchResults, SearchResultItem
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class SerpAPIGoogleSearchEngine(SearchEngine):
    """基于SerpAPI的Google官方搜索"""

    def __init__(self, search_config: SearchConfig, max_results: int = 10) -> None:
        self._search_config = search_config
        self._max_results = max_results

    async def invoke(self, query: str, date_range: Optional[str] = None) -> ToolResult[SearchResults]:
        if not self._search_config.api_key.strip():
            return ToolResult(
                success=False,
                message="请先在设置中填写 SerpAPI API Key",
                data=SearchResults(query=query, date_range=date_range, total_results=0, results=[]),
            )

        params = {
            "engine": self._search_config.engine,
            "q": query,
            "api_key": self._search_config.api_key,
            "gl": self._search_config.gl,
            "hl": self._search_config.hl,
            "num": self._max_results,
        }
        if date_range and date_range != "all":
            params["tbs"] = {
                "past_hour": "qdr:h",
                "past_day": "qdr:d",
                "past_week": "qdr:w",
                "past_month": "qdr:m",
                "past_year": "qdr:y",
            }.get(date_range, "")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get("https://serpapi.com/search.json", params=params)
            response.raise_for_status()
            payload = response.json()

        items = [
            SearchResultItem(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in payload.get("organic_results", [])[:self._max_results]
        ]
        return ToolResult(
            success=True,
            data=SearchResults(
                query=query,
                date_range=date_range,
                total_results=len(items),
                results=items,
            ),
        )
