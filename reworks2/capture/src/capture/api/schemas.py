from pydantic import BaseModel, Field
from typing import List, Optional


class MintTokenBody(BaseModel):
    sub: str
    roles: List[str] = Field(..., min_length=1)
    customer_id: Optional[int] = None
    ttl_days: Optional[int] = None
    ttl_seconds: Optional[int] = None


class RevokeTokenBody(BaseModel):
    jti: Optional[str] = None
    sub: Optional[str] = None
    reason: str = ""