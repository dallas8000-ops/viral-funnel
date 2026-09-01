from __future__ import annotations

import stripe
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.pipeline import load_config
from app.engine.scoreboard import new_access_token
from app.models import Member
from app.settings import get_settings


def client() -> stripe.StripeClient:
    key = get_settings().stripe_secret_key
    if not key:
        raise HTTPException(400, "STRIPE_SECRET_KEY missing")
    stripe.api_key = key
    return stripe


async def resolve_price_id(session: AsyncSession) -> str:
    s = get_settings()
    if s.stripe_price_id:
        return s.stripe_price_id
    cfg = await load_config(session)
    if cfg.stripe_price_id:
        return cfg.stripe_price_id
    client()
    product = stripe.Product.create(name=cfg.offer_name or "Operator Community")
    created = stripe.Price.create(
        product=product.id,
        unit_amount=s.stripe_price_cents,
        currency="usd",
        recurring={"interval": "month"},
    )
    cfg.stripe_price_id = created.id
    return created.id


async def checkout_url(session: AsyncSession, email: str | None = None) -> str:
    s = get_settings()
    client()
    price = await resolve_price_id(session)
    checkout = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=f"{s.public_url}/community?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{s.public_url}/join",
        customer_email=email or None,
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )
    return checkout.url or ""


async def upsert_member(session: AsyncSession, email: str, customer_id: str, sub_id: str, status: str) -> Member:
    row = await session.scalar(select(Member).where(Member.email == email.lower()))
    if row is None:
        row = Member(email=email.lower(), access_token=new_access_token())
        session.add(row)
    row.stripe_customer_id = customer_id
    row.stripe_subscription_id = sub_id
    row.status = status
    return row


async def member_from_checkout_session(session: AsyncSession, session_id: str) -> Member | None:
    client()
    try:
        checkout = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise HTTPException(400, f"Unable to load checkout: {exc}") from exc
    email = (checkout.get("customer_details") or {}).get("email") or checkout.get("customer_email")
    if not email or checkout.get("status") != "complete":
        return None
    return await upsert_member(
        session,
        email=email,
        customer_id=str(checkout.get("customer") or ""),
        sub_id=str(checkout.get("subscription") or ""),
        status="active",
    )


async def handle_webhook(request: Request, session: AsyncSession) -> dict:
    s = get_settings()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not s.stripe_webhook_secret:
        raise HTTPException(400, "STRIPE_WEBHOOK_SECRET missing")
    try:
        event = stripe.Webhook.construct_event(payload, sig, s.stripe_webhook_secret)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

    etype = event["type"]
    obj = event["data"]["object"]
    if etype == "checkout.session.completed":
        email = (obj.get("customer_details") or {}).get("email") or obj.get("customer_email")
        if email:
            await upsert_member(
                session,
                email=email,
                customer_id=str(obj.get("customer") or ""),
                sub_id=str(obj.get("subscription") or ""),
                status="active",
            )
    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub_id = obj.get("id")
        row = await session.scalar(select(Member).where(Member.stripe_subscription_id == sub_id))
        if row:
            row.status = "canceled"
    return {"received": True, "type": etype}
