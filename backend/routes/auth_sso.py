"""
backend/routes/auth_sso.py
Phase 6: SSO authentication endpoints (Google/Microsoft OAuth2)
"""
import os
import logging
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.orm.sso_configuration import SSOConfiguration, SSOProvider
from backend.orm.institution import Institution
from backend.services.sso_service import SSOService
from backend.auth import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/sso", tags=["SSO Authentication"])

# Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5500")
SSO_CALLBACK_URL = os.getenv("SSO_CALLBACK_URL", f"{FRONTEND_URL}/auth/sso/callback")


@router.get("/{provider}")
async def initiate_sso(
    provider: str,
    institution_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    GET /api/auth/sso/{provider}?institution_code=xxx
    Initiate SSO authentication flow.
    Redirects to provider's authorization URL.
    """
    # Validate provider
    if provider not in ["google", "microsoft"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {provider}"
        )
    
    # Get institution
    institution = await SSOService.get_institution_by_code(db, institution_code)
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Get SSO config
    sso_config = await SSOService.get_sso_config(db, institution.id, provider)
    if not sso_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSO not configured for {provider}"
        )
    
    # Decrypt client secret
    client_secret = SSOService.decrypt_client_secret(sso_config.client_secret_encrypted)
    
    # Generate state parameter
    state = SSOService.generate_state_param(institution_code)
    
    # Build authorization URL
    if provider == "google":
        auth_url = SSOService.build_google_authorization_url(
            client_id=sso_config.client_id,
            redirect_uri=SSO_CALLBACK_URL,
            state=state,
            scope=sso_config.scope
        )
    elif provider == "microsoft":
        auth_url = SSOService.build_microsoft_authorization_url(
            client_id=sso_config.client_id,
            redirect_uri=SSO_CALLBACK_URL,
            state=state,
            scope=sso_config.scope
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider"
        )
    
    logger.info(f"Initiated {provider} SSO for institution {institution_code}")
    
    # Redirect to provider
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def sso_callback(
    code: str,
    state: str,
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    GET /api/auth/sso/callback?code=xxx&state=xxx
    OAuth2 callback handler.
    Exchanges code for token, fetches user info, creates/links account.
    """
    # Handle provider errors
    if error:
        logger.error(f"SSO provider error: {error}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=sso_failed&message={error}"
        )
    
    # Parse state parameter
    institution_code = SSOService.parse_state_param(state)
    if not institution_code:
        logger.error("Invalid state parameter")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=invalid_state"
        )
    
    # Get institution
    institution = await SSOService.get_institution_by_code(db, institution_code)
    if not institution:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=institution_not_found"
        )
    
    # Get SSO config (try Google first, then Microsoft)
    sso_config = await SSOService.get_sso_config(db, institution.id, "google")
    if not sso_config:
        sso_config = await SSOService.get_sso_config(db, institution.id, "microsoft")
    
    if not sso_config:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=sso_not_configured"
        )
    
    try:
        # Decrypt client secret
        client_secret = SSOService.decrypt_client_secret(sso_config.client_secret_encrypted)
        
        # Exchange code for access token
        token_data = await SSOService.exchange_code_for_token(
            token_url=sso_config.token_url,
            client_id=sso_config.client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=SSO_CALLBACK_URL
        )
        
        if not token_data:
            logger.error("Token exchange failed")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=token_exchange_failed"
            )
        
        access_token = token_data.get("access_token")
        if not access_token:
            logger.error("No access token in response")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=no_access_token"
            )
        
        # Fetch user info
        user_info = await SSOService.fetch_user_info(
            userinfo_url=sso_config.userinfo_url,
            access_token=access_token
        )
        
        if not user_info:
            logger.error("Failed to fetch user info")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=user_info_failed"
            )
        
        # Extract user data
        email = user_info.get("email", "").lower()
        name = user_info.get("name") or user_info.get("displayName") or email.split("@")[0]
        
        if not email:
            logger.error("No email in user info")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=no_email"
            )
        
        # Validate email domain matches institution
        if institution.domain and not email.endswith(f"@{institution.domain}"):
            logger.warning(f"Email domain mismatch: {email} vs {institution.domain}")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=email_domain_mismatch"
            )
        
        # Find or create user
        user = await SSOService.find_or_create_sso_user(
            db, institution.id, email, name, sso_config.provider
        )
        
        if not user:
            logger.error("Failed to create/find user")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=user_creation_failed"
            )
        
        # Generate JWT token
        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
            "institution_id": user.institution_id
        })
        
        logger.info(f"SSO login successful: {email} (institution: {institution_code})")
        
        # Redirect to frontend with token
        return RedirectResponse(
            url=f"{FRONTEND_URL}/sso-callback?token={token}&institution={institution_code}"
        )
    
    except Exception as e:
        logger.error(f"SSO callback error: {str(e)}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=sso_error"
        )


@router.get("/{provider}/login-url")
async def get_sso_login_url(
    provider: str,
    institution_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    GET /api/auth/sso/{provider}/login-url?institution_code=xxx
    Get SSO login URL for frontend (alternative to direct redirect).
    """
    # Validate provider
    if provider not in ["google", "microsoft"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {provider}"
        )
    
    # Get institution
    institution = await SSOService.get_institution_by_code(db, institution_code)
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Get SSO config
    sso_config = await SSOService.get_sso_config(db, institution.id, provider)
    if not sso_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSO not configured for {provider}"
        )
    
    # Generate state parameter
    state = SSOService.generate_state_param(institution_code)
    
    # Build authorization URL
    if provider == "google":
        auth_url = SSOService.build_google_authorization_url(
            client_id=sso_config.client_id,
            redirect_uri=SSO_CALLBACK_URL,
            state=state,
            scope=sso_config.scope
        )
    else:  # microsoft
        auth_url = SSOService.build_microsoft_authorization_url(
            client_id=sso_config.client_id,
            redirect_uri=SSO_CALLBACK_URL,
            state=state,
            scope=sso_config.scope
        )
    
    return {
        "login_url": auth_url,
        "provider": provider,
        "institution_code": institution_code
    }
