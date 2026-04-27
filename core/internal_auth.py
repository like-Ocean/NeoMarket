from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from core.config import settings

api_key_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)

async def verify_internal_token(token: str = Security(api_key_header)) -> str:
    if not token or token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal token"
        )
    return token