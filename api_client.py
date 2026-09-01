import httpx
import logging
import asyncio
from typing import Dict, Any, List, Optional
from config import AIVERSE_API_KEY, AIVERSE_BASE_URL
from rate_limiter import api_rate_limiter

logger = logging.getLogger(__name__)

class AIVerseAPIClient:
    """Async API Client for AIVerse Hub (https://aiversehub.store) with Rate Limiting."""

    def __init__(self, base_url: str = AIVERSE_BASE_URL, api_key: str = AIVERSE_API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute rate-limited HTTP request with exponential backoff on HTTP 429."""
        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            await api_rate_limiter.acquire()

            async with httpx.AsyncClient(timeout=25.0) as client:
                try:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=self._headers(), params=params)
                    elif method.upper() == "POST":
                        response = await client.post(url, headers=self._headers(), json=json_data)
                    else:
                        raise ValueError(f"Unsupported HTTP method {method}")

                    if response.status_code == 429:
                        logger.warning(f"AIVerse API 429 Rate Limit hit. Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff *= 2.0
                        continue

                    data = response.json()
                    if response.status_code in (200, 201):
                        return data
                    else:
                        err_msg = data.get("error", f"HTTP {response.status_code}") if isinstance(data, dict) else f"HTTP {response.status_code}"
                        return {"success": False, "error": err_msg}

                except Exception as e:
                    logger.error(f"AIVerse API request error ({method} {endpoint}): {e}")
                    if attempt == max_retries - 1:
                        return {"success": False, "error": str(e)}
                    await asyncio.sleep(backoff)
                    backoff *= 1.5

        return {"success": False, "error": "Max retries exceeded"}

    async def get_me(self) -> Dict[str, Any]:
        """Fetch reseller account info & wallet_balance."""
        return await self._request("GET", "/api/v1/me")

    async def get_products(self) -> List[Dict[str, Any]]:
        """Fetch live product catalog, costs, and stock."""
        res = await self._request("GET", "/api/v1/products")
        if isinstance(res, dict) and "services" in res:
            return res["services"]
        elif isinstance(res, list):
            return res
        return []

    async def place_order(self, service_id: str, quantity: int = 1) -> Dict[str, Any]:
        """Place automated order with AIVerse Hub."""
        payload = {"service_id": service_id, "quantity": quantity}
        return await self._request("POST", "/api/v1/order", json_data=payload)

    async def get_orders(self, page: int = 1, limit: int = 50) -> Dict[str, Any]:
        """Fetch order history from reseller API."""
        return await self._request("GET", "/api/v1/orders", params={"page": page, "limit": limit})

    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Fetch specific order details by ID."""
        return await self._request("GET", f"/api/v1/order/{order_id}")

    async def get_stats(self) -> Dict[str, Any]:
        """Fetch reseller API statistics."""
        return await self._request("GET", "/api/v1/stats")

api_client = AIVerseAPIClient()
