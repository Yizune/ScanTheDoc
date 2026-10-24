from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import Settings, get_settings
from app.database import get_session
from app.models import Account, Document
from app.services.storage import DocumentStorage

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    session: Session,
    settings: AppSettings,
):
    if not settings.clerk_webhook_signing_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk webhook is not configured",
        )

    payload = await request.body()
    try:
        event = Webhook(settings.clerk_webhook_signing_secret).verify(
            payload,
            dict(request.headers),
        )
    except WebhookVerificationError as error:
        raise HTTPException(
            status_code=400, detail="Invalid webhook signature"
        ) from error

    if event.get("type") != "user.deleted":
        return {"received": True}

    user_id = event.get("data", {}).get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Deleted user ID is missing")

    documents = list(
        (
            await session.execute(select(Document).where(Document.owner_id == user_id))
        ).scalars()
    )
    storage = getattr(request.app.state, "storage", None) or DocumentStorage(settings)
    await asyncio.to_thread(storage.initialize)
    for document in documents:
        await asyncio.to_thread(storage.delete, document.storage_key)
    result = await session.execute(
        delete(Account).where(Account.clerk_user_id == user_id)
    )
    await session.commit()
    return {"received": True, "deleted": result.rowcount > 0}
