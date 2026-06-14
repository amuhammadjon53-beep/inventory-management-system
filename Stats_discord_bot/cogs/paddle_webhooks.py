from __future__ import annotations

import os
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("paddle.webhook")

PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return None


async def _resolve_discord_id_from_sub(
    db,
    paddle_subscription_id: str,
    custom_data: Optional[Dict],
) -> Optional[str]:
    if custom_data and custom_data.get("discord_id"):
        return str(custom_data["discord_id"])
    sub = await db.get_subscription(paddle_subscription_id)
    return sub["discord_id"] if sub else None


async def _resolve_guild_id(
    db,
    paddle_subscription_id: str,
    custom_data: Optional[Dict],
) -> Optional[int]:
    if custom_data and custom_data.get("guild_id"):
        return int(custom_data["guild_id"])
    sub = await db.get_subscription(paddle_subscription_id)
    return sub["guild_id"] if sub else None


def verify_webhook_signature(raw_body: bytes, paddle_signature_header: str) -> bool:
    if not PADDLE_WEBHOOK_SECRET:
        return True

    try:
        parts = dict(p.split("=", 1)
                     for p in paddle_signature_header.split(";"))
        ts = parts.get("ts", "")
        h1 = parts.get("h1", "")
        signed_payload = f"{ts}:{raw_body.decode()}"
        expected = hmac.new(
            PADDLE_WEBHOOK_SECRET.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, h1)
    except Exception as exc:
        logger.error("Signature verification error: %s", exc)
        return False


async def process_event(db, event: Dict) -> None:
    event_type = event.get("event_type", "")
    data = event.get("data", {})
    event_id = event.get("notification_id") or event.get("event_id", "unknown")

    logger.info("Processing Paddle event %s id=%s", event_type, event_id)

    handlers = {
        "subscription.created":       _handle_subscription_created,
        "subscription.updated":       _handle_subscription_updated,
        "subscription.activated":     _handle_subscription_activated,
        "subscription.canceled":      _handle_subscription_canceled,
        "subscription.paused":        _handle_subscription_paused,
        "subscription.resumed":       _handle_subscription_resumed,
        "subscription.past_due":      _handle_subscription_past_due,
        "subscription.trialing":      _handle_subscription_trialing,
        "transaction.completed":      _handle_transaction_completed,
        "transaction.payment_failed": _handle_transaction_payment_failed,
        "transaction.updated":        _handle_transaction_updated,
        "transaction.billed":         _handle_transaction_billed,
        "transaction.ready":          _handle_transaction_noop,
        "transaction.created":        _handle_transaction_noop,
        "adjustment.created":         _handle_adjustment_created,
        "adjustment.updated":         _handle_adjustment_updated,
        "customer.created":           _handle_customer_created,
        "customer.updated":           _handle_customer_updated,
    }

    handler = handlers.get(event_type, _handle_unknown)
    await handler(db, data, event)


async def _handle_subscription_created(db, data: Dict, raw: Dict) -> None:
    custom_data = data.get("custom_data") or {}
    discord_id = custom_data.get("discord_id")
    guild_id = custom_data.get("guild_id")

    if not discord_id or not guild_id:
        logger.warning(
            "subscription.created missing discord_id or guild_id in custom_data")
        return

    guild_id = int(guild_id)
    billing_cycle = (
        data.get("billing_cycle", {}).get("interval", "month")
        .replace("month", "monthly")
        .replace("year", "yearly")
    )

    cust_id = data.get("customer_id")
    await db.upsert_paddle_customer(str(discord_id), paddle_customer_id=cust_id)

    items = data.get("items", [])
    module = None
    if items:
        price_id = items[0].get("price", {}).get("id")
        if price_id:
            module = await db.get_module_by_paddle_price(price_id)

    base_price = float(custom_data.get("base_price_usd", 0))
    discount_pct = float(custom_data.get("discount_pct", 0))
    final_price = float(custom_data.get("final_price_usd", base_price))
    server_count = int(custom_data.get("server_count", 1))
    period = data.get("current_billing_period") or {}

    sub = await db.create_subscription({
        "discord_id": str(discord_id),
        "guild_id": guild_id,
        "paddle_subscription_id": data["id"],
        "paddle_transaction_id": data.get("transaction_id"),
        "paddle_customer_id": cust_id,
        "module_id": module["id"] if module else None,
        "tier_id": None,
        "billing_cycle": billing_cycle,
        "base_price_usd": base_price,
        "discount_pct": discount_pct,
        "final_price_usd": final_price,
        "server_count_at_purchase": server_count,
        "status": data.get("status", "active"),
        "current_period_start": _parse_dt(period.get("starts_at")),
        "current_period_end": _parse_dt(period.get("ends_at")),
    })

    if module:
        await db.grant_module_access(guild_id, module["id"], sub["id"], str(discord_id))
        logger.info(
            "Granted %s to guild %s for user %s (sub %s)",
            module["module_key"], guild_id, discord_id, sub["id"],
        )


async def _handle_subscription_activated(db, data: Dict, raw: Dict) -> None:
    period = data.get("current_billing_period") or {}
    await db.update_subscription_status(
        data["id"],
        status="active",
        current_period_start=_parse_dt(period.get("starts_at")),
        current_period_end=_parse_dt(period.get("ends_at")),
    )


async def _handle_subscription_updated(db, data: Dict, raw: Dict) -> None:
    period = data.get("current_billing_period") or {}
    status = data.get("status", "active")

    sub = await db.update_subscription_status(
        data["id"],
        status=status,
        current_period_start=_parse_dt(period.get("starts_at")),
        current_period_end=_parse_dt(period.get("ends_at")),
    )

    if sub and status in ("canceled", "paused"):
        await db.revoke_module_access(sub["id"])


async def _handle_subscription_canceled(db, data: Dict, raw: Dict) -> None:
    sub = await db.update_subscription_status(
        data["id"],
        status="canceled",
        canceled_at=_parse_dt(data.get("canceled_at")),
        cancel_at_period_end=False,
    )
    if sub:
        revoked = await db.revoke_module_access(sub["id"])
        logger.info(
            "Subscription %s canceled — revoked %d access rows", data["id"], revoked)

    discord_id = await _resolve_discord_id_from_sub(db, data["id"], data.get("custom_data"))
    guild_id = await _resolve_guild_id(db, data["id"], data.get("custom_data"))

    await db.log_transaction({
        "paddle_transaction_id": f"cancel_{data['id']}",
        "paddle_subscription_id": data["id"],
        "paddle_customer_id": data.get("customer_id"),
        "discord_id": discord_id,
        "guild_id": guild_id,
        "amount_usd": 0,
        "status": "canceled",
        "transaction_type": "cancellation",
        "raw_payload": raw,
    })


async def _handle_subscription_paused(db, data: Dict, raw: Dict) -> None:
    sub = await db.update_subscription_status(data["id"], status="paused")
    if sub:
        await db.revoke_module_access(sub["id"])
        logger.info("Subscription %s paused — access revoked", data["id"])


async def _handle_subscription_resumed(db, data: Dict, raw: Dict) -> None:
    period = data.get("current_billing_period") or {}
    sub = await db.update_subscription_status(
        data["id"],
        status="active",
        current_period_start=_parse_dt(period.get("starts_at")),
        current_period_end=_parse_dt(period.get("ends_at")),
    )
    if sub and sub.get("module_id"):
        discord_id = await _resolve_discord_id_from_sub(db, data["id"], data.get("custom_data"))
        guild_id = await _resolve_guild_id(db, data["id"], data.get("custom_data"))
        if discord_id and guild_id:
            await db.grant_module_access(int(guild_id), sub["module_id"], sub["id"], discord_id)
            logger.info(
                "Subscription %s resumed — access restored", data["id"])


async def _handle_subscription_past_due(db, data: Dict, raw: Dict) -> None:
    await db.update_subscription_status(data["id"], status="past_due")
    logger.info("Subscription %s is past due", data["id"])


async def _handle_subscription_trialing(db, data: Dict, raw: Dict) -> None:
    period = data.get("current_billing_period") or {}
    await db.update_subscription_status(
        data["id"],
        status="trialing",
        current_period_start=_parse_dt(period.get("starts_at")),
        current_period_end=_parse_dt(period.get("ends_at")),
    )


async def _handle_transaction_completed(db, data: Dict, raw: Dict) -> None:
    custom_data = data.get("custom_data") or {}
    discord_id = custom_data.get("discord_id") or (
        await _resolve_discord_id_from_sub(db, data.get("subscription_id", ""), custom_data)
    )
    guild_id = custom_data.get("guild_id") or (
        await _resolve_guild_id(db, data.get("subscription_id", ""), custom_data)
    )

    totals = (data.get("details") or {}).get("totals") or {}
    amount = float(totals.get("grand_total", 0)) / \
        100 if totals.get("grand_total") else 0

    await db.log_transaction({
        "paddle_transaction_id": data["id"],
        "paddle_subscription_id": data.get("subscription_id"),
        "paddle_customer_id": data.get("customer_id"),
        "discord_id": str(discord_id) if discord_id else None,
        "guild_id": int(guild_id) if guild_id else None,
        "amount_usd": amount,
        "status": "completed",
        "transaction_type": "purchase" if not data.get("subscription_id") else "renewal",
        "raw_payload": raw,
    })

    if data.get("subscription_id"):
        await db.update_subscription_status(
            data["subscription_id"],
            status="active",
            paddle_transaction_id=data["id"],
        )


async def _handle_transaction_payment_failed(db, data: Dict, raw: Dict) -> None:
    custom_data = data.get("custom_data") or {}
    discord_id = custom_data.get("discord_id")
    guild_id = custom_data.get("guild_id")

    await db.log_transaction({
        "paddle_transaction_id": data["id"],
        "paddle_subscription_id": data.get("subscription_id"),
        "paddle_customer_id": data.get("customer_id"),
        "discord_id": str(discord_id) if discord_id else None,
        "guild_id": int(guild_id) if guild_id else None,
        "amount_usd": 0,
        "status": "failed",
        "transaction_type": "payment_failed",
        "raw_payload": raw,
    })
    logger.warning("Payment failed for transaction %s", data["id"])


async def _handle_transaction_updated(db, data: Dict, raw: Dict) -> None:
    logger.debug("transaction.updated %s status=%s",
                 data["id"], data.get("status"))


async def _handle_transaction_billed(db, data: Dict, raw: Dict) -> None:
    logger.debug("transaction.billed %s", data["id"])


async def _handle_transaction_noop(db, data: Dict, raw: Dict) -> None:
    pass


async def _handle_adjustment_created(db, data: Dict, raw: Dict) -> None:
    if data.get("action") != "refund":
        return

    sub_id = data.get("subscription_id")
    txn_id = data.get("transaction_id")
    discord_id = await _resolve_discord_id_from_sub(db, sub_id or "", data.get("custom_data"))
    guild_id = await _resolve_guild_id(db, sub_id or "", data.get("custom_data"))

    totals = data.get("totals") or {}
    amount = float(totals.get("total", 0)) / 100 if totals.get("total") else 0

    await db.log_refund({
        "paddle_transaction_id": txn_id,
        "paddle_subscription_id": sub_id,
        "discord_id": str(discord_id) if discord_id else None,
        "guild_id": int(guild_id) if guild_id else None,
        "amount_usd": amount,
        "reason": data.get("reason", ""),
    })

    if sub_id:
        sub = await db.get_subscription(sub_id)
        if sub:
            revoked = await db.revoke_module_access(sub["id"])
            await db.update_subscription_status(sub_id, status="canceled")
            logger.info(
                "Refund processed for sub %s — revoked %d access rows", sub_id, revoked)


async def _handle_adjustment_updated(db, data: Dict, raw: Dict) -> None:
    logger.debug("adjustment.updated %s status=%s",
                 data.get("id"), data.get("status"))


async def _handle_customer_created(db, data: Dict, raw: Dict) -> None:
    custom_data = data.get("custom_data") or {}
    discord_id = custom_data.get("discord_id")
    if discord_id:
        await db.upsert_paddle_customer(
            str(discord_id),
            paddle_customer_id=data["id"],
            email=data.get("email"),
        )


async def _handle_customer_updated(db, data: Dict, raw: Dict) -> None:
    cust = await db.get_paddle_customer_by_paddle_id(data["id"])
    if cust:
        await db.upsert_paddle_customer(
            cust["discord_id"],
            paddle_customer_id=data["id"],
            email=data.get("email"),
        )


async def _handle_unknown(db, data: Dict, raw: Dict) -> None:
    logger.info("Unhandled Paddle event type: %s", raw.get("event_type"))
