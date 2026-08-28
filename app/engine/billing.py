from __future__ import annotations

import stripe
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.scoreboard import new_access_token
from app.models import Member
from app.settings import get_settings


def stripe_ready() -> bool:
    s = get_settings()
    return bool(s.stripe_secret_key and (s.stripe_price_id or True))


def client() -> stripe.StripeClient:
    key = get_settings().stripe_secret_key
    if not key:
        raise HTTPException(400, "STRIPE_SECRET_KEY missing")
    stripe.api_key = key
    return stripe


async def checkout_url(email: str | None = None) -> str:
    s = get_settings()
    client()
    price = s.stripe_price_id
    if not price:
        product = stripe.Product.create(name="Operator Community")
        created = stripe.Price.create(
            product=product.id,
            unit_amount=s.stripe_price_cents,
            currency="usd",
            recurring={"interval": "month"},
        )
        price = created.id
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=f"{s.public_url}/community?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{s.public_url}/join",
        customer_email=email or None,
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )
    return session.url or ""


async def upsert_member(session: AsyncSession, email: str, customer_id: str, sub_id: str, status: str) -> Member:
    row = await session.scalar(select(Member).where(Member.email == email.lower()))
    if row is None:
        row = Member(email=email.lower(), access_token=new_access_token())
        session.add(row)
    row.stripe_customer_id = customer_id
    row.stripe_subscription_id = sub_id
    row.status = status
    return row


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
