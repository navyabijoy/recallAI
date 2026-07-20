"""
Authentication: Google OAuth sign-in + Bearer-JWT sessions.

Flow:
  1. Browser hits GET /api/auth/google/login  -> redirected to Google's consent screen.
  2. Google redirects back to GET /api/auth/google/callback?code=...&state=...
  3. We verify state, exchange the code for a Google access token, fetch the profile,
     upsert the User (by email), onboard new users, mint an app JWT, and redirect to
     the frontend with the token in the URL fragment.
  4. The frontend stores the JWT and sends it as `Authorization: Bearer <jwt>` on every
     API call; `get_current_user` decodes it. The extension uses API keys instead.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import jwt
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from .config import settings
from .models import get_session, User, Topic, KnowledgeNode, UserMemoryParams
from .memory_model import DEFAULT_DECAY_EXPONENT, DEFAULT_STABILITY_GROWTH

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

router = APIRouter()


# --- JWT helpers ---

def create_access_token(user_id: str, expires_hours: Optional[int] = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours or settings.jwt_expire_hours)
    return jwt.encode(
        {"sub": user_id, "exp": exp, "type": "access"},
        settings.secret_key, algorithm=ALGORITHM,
    )


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def _create_state_token() -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode(
        {"exp": exp, "nonce": secrets.token_urlsafe(8), "type": "oauth_state"},
        settings.secret_key, algorithm=ALGORITHM,
    )


def _verify_state_token(token: str) -> bool:
    try:
        return decode_token(token).get("type") == "oauth_state"
    except jwt.PyJWTError:
        return False


# --- current-user dependency ---

def get_current_user(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Resolves the web-app user from the `Authorization: Bearer <jwt>` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = session.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# --- user onboarding + Google upsert ---

def onboard_user(session: Session, user: User) -> None:
    """Idempotently seeds a user's memory params + a knowledge node per topic."""
    if not session.get(UserMemoryParams, user.id):
        session.add(UserMemoryParams(
            user_id=user.id,
            decay_exponent=DEFAULT_DECAY_EXPONENT,
            stability_growth=DEFAULT_STABILITY_GROWTH,
            speed_baselines={},
        ))
    have = {
        n.topic_id for n in session.exec(
            select(KnowledgeNode).where(KnowledgeNode.user_id == user.id)
        ).all()
    }
    for topic in session.exec(select(Topic)).all():
        if topic.id not in have:
            session.add(KnowledgeNode(
                user_id=user.id, topic_id=topic.id,
                fsrs_stability=1.0, fsrs_difficulty=6.0,
                last_review=datetime.utcnow() - timedelta(days=7), practice_count=0,
            ))
    session.commit()


def upsert_user_from_google(session: Session, userinfo: Dict[str, Any]) -> User:
    """Finds or creates a User from a Google profile, then (idempotently) onboards them."""
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account did not return an email")
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        user = User(
            name=userinfo.get("name") or email.split("@")[0],
            email=email,
            preferences={"dailyStudyTimeMinutes": 120},
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    onboard_user(session, user)
    return user


# --- Google OAuth network calls ---

def google_login_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_userinfo(code: str) -> Dict[str, Any]:
    """Exchanges an auth code for tokens and returns the Google profile."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Google token exchange failed")
        info_res = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        info_res.raise_for_status()
        return info_res.json()


# --- routes ---

@router.get("/api/auth/google/login")
def google_login():
    if not settings.google_configured:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID/SECRET in backend/.env.",
        )
    return RedirectResponse(google_login_url(_create_state_token()))


@router.get("/api/auth/google/callback")
async def google_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
):
    if error:
        return RedirectResponse(f"{settings.frontend_url}/login?error={error}")
    if not code or not state or not _verify_state_token(state):
        raise HTTPException(status_code=400, detail="Invalid OAuth callback (missing/invalid code or state)")
    try:
        userinfo = await exchange_code_for_userinfo(code)
    except httpx.HTTPError as e:
        logger.error("Google OAuth exchange failed: %s", e)
        return RedirectResponse(f"{settings.frontend_url}/login?error=oauth_failed")

    user = upsert_user_from_google(session, userinfo)
    token = create_access_token(user.id)
    # Token in the fragment so it never lands in server access logs.
    return RedirectResponse(f"{settings.frontend_url}/auth/callback#token={token}")


@router.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "preferences": current_user.preferences,
    }
