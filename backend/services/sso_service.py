"""
backend/services/sso_service.py
Phase 6: SSO OAuth2 service for Google/Microsoft authentication
"""
import os
import logging
import secrets
import base64
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.orm.sso_configuration import SSOConfiguration, SSOProvider
from backend.orm.institution import Institution
from backend.orm.user import User, UserRole

logger = logging.getLogger(__name__)

# Encryption key for client secrets (should be in env)
ENCRYPTION_KEY = os.getenv("SSO_ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # Generate a key if not set (for development only - production MUST set this)
    logger.warning("SSO_ENCRYPTION_KEY not set - generating temporary key (NOT FOR PRODUCTION)")
    ENCRYPTION_KEY = Fernet.generate_key().decode()

fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


class SSOService:
    """Service for handling SSO authentication flows"""
    
    @staticmethod
    def encrypt_client_secret(secret: str) -> str:
        """Encrypt client secret using Fernet (AES-128-CBC)"""
        return fernet.encrypt(secret.encode()).decode()
    
    @staticmethod
    def decrypt_client_secret(encrypted: str) -> str:
        """Decrypt client secret"""
        return fernet.decrypt(encrypted.encode()).decode()
    
    @staticmethod
    def generate_state_param(institution_code: str) -> str:
        """Generate state parameter for OAuth2 flow"""
        nonce = secrets.token_urlsafe(16)
        return base64.urlsafe_b64encode(f"{institution_code}:{nonce}".encode()).decode()
    
    @staticmethod
    def parse_state_param(state: str) -> Optional[str]:
        """Parse institution code from state parameter"""
        try:
            decoded = base64.urlsafe_b64decode(state.encode()).decode()
            institution_code, _ = decoded.split(":", 1)
            return institution_code
        except Exception:
            return None
    
    @classmethod
    async def get_sso_config(
        cls,
        db: AsyncSession,
        institution_id: int,
        provider: str
    ) -> Optional[SSOConfiguration]:
        """Get SSO configuration for institution and provider"""
        result = await db.execute(
            select(SSOConfiguration).where(
                SSOConfiguration.institution_id == institution_id,
                SSOConfiguration.provider == provider,
                SSOConfiguration.is_enabled == True
            )
        )
        return result.scalar_one_or_none()
    
    @classmethod
    async def get_institution_by_code(
        cls,
        db: AsyncSession,
        code: str
    ) -> Optional[Institution]:
        """Get institution by its unique code"""
        result = await db.execute(
            select(Institution).where(
                Institution.code == code,
                Institution.is_active == True
            )
        )
        return result.scalar_one_or_none()
    
    @classmethod
    def build_google_authorization_url(
        cls,
        client_id: str,
        redirect_uri: str,
        state: str,
        scope: str = "openid email profile"
    ) -> str:
        """Build Google OAuth2 authorization URL"""
        return (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scope.replace(' ', '%20')}"
            f"&state={state}"
            f"&access_type=offline"
            f"&prompt=consent"
        )
    
    @classmethod
    def build_microsoft_authorization_url(
        cls,
        client_id: str,
        redirect_uri: str,
        state: str,
        tenant_id: str = "common",
        scope: str = "openid email profile"
    ) -> str:
        """Build Microsoft OAuth2 authorization URL"""
        return (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scope.replace(' ', '%20')}"
            f"&state={state}"
            f"&prompt=consent"
        )
    
    @classmethod
    async def exchange_code_for_token(
        cls,
        token_url: str,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str
    ) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        async with httpx.AsyncClient() as client:
            data = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri
            }
            
            try:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Token exchange failed: {str(e)}")
                return None
    
    @classmethod
    async def fetch_user_info(
        cls,
        userinfo_url: str,
        access_token: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch user info from OAuth2 provider"""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            
            try:
                response = await client.get(userinfo_url, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"User info fetch failed: {str(e)}")
                return None
    
    @classmethod
    async def find_or_create_sso_user(
        cls,
        db: AsyncSession,
        institution_id: int,
        email: str,
        name: str,
        provider: str
    ) -> Optional[User]:
        """Find existing user or create new one from SSO data"""
        # Check if user exists by email
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update institution if not set
            if not user.institution_id:
                user.institution_id = institution_id
            return user
        
        # Create new user
        # Generate a random password (user will use SSO only)
        import secrets
        random_password = secrets.token_urlsafe(32)
        
        from backend.auth import get_password_hash
        
        new_user = User(
            email=email,
            name=name,
            hashed_password=get_password_hash(random_password),
            institution_id=institution_id,
            role=UserRole.student,  # Default role for SSO users
            is_active=True
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        logger.info(f"Created new user from SSO: {email} (institution: {institution_id})")
        return new_user


# Convenience function for getting the service
async def get_sso_service():
    """Factory function to get SSO service instance"""
    return SSOService()
