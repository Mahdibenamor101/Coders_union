import secrets

from cryptography.fernet import Fernet
from fastapi import Header, HTTPException, status

from .config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt_rtsp_url(url: str) -> str:
    return _fernet().encrypt(url.encode()).decode()


def decrypt_rtsp_url(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_api_key, get_settings().api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
