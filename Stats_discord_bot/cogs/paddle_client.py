import os
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("paddle_client")

PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_ENV = os.getenv("PADDLE_ENV", "sandbox")

BASE_URL = (
    "https://sandbox-api.paddle.com"
    if PADDLE_ENV == "sandbox"
    else "https://api.paddle.com"
)

HEADERS = {
    "Authorization": f"Bearer {PADDLE_API_KEY}",
    "Content-Type": "application/json",
}


class PaddleAPIError(Exception):
    def __init__(self, status: int, body: Dict):
        self.status = status
        self.body = body
        super().__init__(f"Paddle API {status}: {body}")


async def _request(
    method: str,
    path: str,
    payload: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Dict:
    url = f"{BASE_URL}{path}"
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            url,
            headers=HEADERS,
            json=payload,
            params=params,
        ) as resp:
            body = await resp.json()
            if resp.status >= 400:
                logger.error("Paddle API error %s %s -> %d %s", method, path, resp.status, body)
                raise PaddleAPIError(resp.status, body)
            return body


async def create_customer(email: str, name: Optional[str] = None) -> Dict:
    payload: Dict[str, Any] = {"email": email}
    if name:
        payload["name"] = name
    return await _request("POST", "/customers", payload)


async def get_customer(paddle_customer_id: str) -> Dict:
    return await _request("GET", f"/customers/{paddle_customer_id}")


async def get_subscription(paddle_subscription_id: str) -> Dict:
    return await _request("GET", f"/subscriptions/{paddle_subscription_id}")


async def cancel_subscription(
    paddle_subscription_id: str,
    effective_from: str = "immediately"
) -> Dict:
    return await _request(
        "POST",
        f"/subscriptions/{paddle_subscription_id}/cancel",
        {"effective_from": effective_from},
    )


async def pause_subscription(paddle_subscription_id: str) -> Dict:
    return await _request("POST", f"/subscriptions/{paddle_subscription_id}/pause", {})


async def resume_subscription(paddle_subscription_id: str) -> Dict:
    return await _request("POST", f"/subscriptions/{paddle_subscription_id}/resume", {})


async def update_subscription(paddle_subscription_id: str, payload: Dict) -> Dict:
    return await _request("PATCH", f"/subscriptions/{paddle_subscription_id}", payload)


async def preview_update_subscription(paddle_subscription_id: str, payload: Dict) -> Dict:
    return await _request("PATCH", f"/subscriptions/{paddle_subscription_id}/preview", payload)


async def list_subscriptions(
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    after: Optional[str] = None,
    per_page: int = 50,
) -> Dict:
    params: Dict[str, Any] = {"per_page": per_page}
    if status:
        params["status"] = status
    if customer_id:
        params["customer_id"] = customer_id
    if after:
        params["after"] = after
    return await _request("GET", "/subscriptions", params=params)


async def get_transaction(paddle_transaction_id: str) -> Dict:
    return await _request("GET", f"/transactions/{paddle_transaction_id}")


async def list_transactions(
    subscription_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    per_page: int = 50,
    after: Optional[str] = None,
) -> Dict:
    params: Dict[str, Any] = {"per_page": per_page}
    if subscription_id:
        params["subscription_id"] = subscription_id
    if customer_id:
        params["customer_id"] = customer_id
    if after:
        params["after"] = after
    return await _request("GET", "/transactions", params=params)


async def get_transaction_invoice(paddle_transaction_id: str) -> Dict:
    return await _request("GET", f"/transactions/{paddle_transaction_id}/invoice")


async def create_refund(
    transaction_id: str,
    reason: str,
    amount: Optional[str] = None,
    items: Optional[List[Dict]] = None,
) -> Dict:
    payload: Dict[str, Any] = {
        "action": "refund",
        "transaction_id": transaction_id,
        "reason": reason,
    }
    if amount:
        payload["amount"] = amount
    if items:
        payload["items"] = items
    return await _request("POST", "/adjustments", payload)


async def list_adjustments(
    transaction_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    per_page: int = 50,
) -> Dict:
    params: Dict[str, Any] = {"per_page": per_page}
    if transaction_id:
        params["transaction_id"] = transaction_id
    if subscription_id:
        params["subscription_id"] = subscription_id
    return await _request("GET", "/adjustments", params=params)


async def generate_checkout_url(
    price_id: str,
    quantity: int = 1,
    discount_id: Optional[str] = None,
    customer_email: Optional[str] = None,
    customer_id: Optional[str] = None,
    custom_data: Optional[Dict] = None,
) -> str:
    payload: Dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": quantity}],
    }
    if discount_id:
        payload["discount_id"] = discount_id
    if customer_id:
        payload["customer"] = {"id": customer_id}
    elif customer_email:
        payload["customer"] = {"email": customer_email}
    if custom_data:
        payload["custom_data"] = custom_data

    resp = await _request("POST", "/transactions", payload)
    logger.info(f"Paddle full transaction response: {resp}")           # ← add this
    checkout = resp.get("data", {}).get("checkout", {})
    logger.info(f"Paddle checkout object: {checkout}")                 # ← and this
    return checkout.get("url", "")


async def preview_prices(
    price_ids: List[str],
    customer_ip_address: str,
    discount_id: Optional[str] = None,
) -> Dict:
    payload: Dict[str, Any] = {
        "items": [{"price_id": pid, "quantity": 1} for pid in price_ids],
        "customer_ip_address": customer_ip_address,
    }
    if discount_id:
        payload["discount_id"] = discount_id
    return await _request("POST", "/pricing-preview", payload)