from typing import Optional

import requests

from app.config import get_settings


class TenorClient:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.tenor_api_key
        self.search_endpoint = "https://g.tenor.com/v1/search"
        self.content_filter = "low"
        self.media_filter = "minimal"

    async def search_gifs(self, search_term: str, limit: int = 10, media_filter: Optional[str] = None):
        params = {
            "q": search_term,
            "limit": limit,
            "key": self.api_key,
            "content_filter": self.content_filter,
            "media_filter": media_filter if media_filter else self.media_filter,
        }
        response = requests.get(self.search_endpoint, params=params)
        if not response.ok:
            raise Exception(f"problem fetching gifs. q:{search_term} {response.status_code} {response.text}")

        gifs = response.json().get("results")
        return gifs
