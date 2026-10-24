from typing import Annotated

import truststore
from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings

truststore.inject_into_ssl()

PUBLIC_WORKSPACE_ID = "public"


def authenticated_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    authorization = request.headers.get("authorization")
    if authorization:
        if not settings.clerk_secret_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured",
            )
        auth_state = authenticate_request(
            request,
            AuthenticateRequestOptions(
                secret_key=settings.clerk_secret_key,
                jwt_key=settings.clerk_jwt_key or None,
                authorized_parties=settings.clerk_authorized_parties,
                accepts_token=["session_token"],
            ),
        )
        if not auth_state.is_signed_in or not auth_state.payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
            )
        return str(auth_state.payload["sub"])

    return PUBLIC_WORKSPACE_ID


CurrentUser = Annotated[str, Depends(authenticated_user)]
