from dataclasses import dataclass
from typing import Optional
import datetime

@dataclass
class CommunityRequest:
    id: str
    timestamp: datetime.datetime
    public_key: str
    community_id: str
    raw: dict
    pending: bool = False
    reject: bool = False
    accept: bool = False
    cancel: bool = False

@dataclass
class TokenPermission:
    symbol: str
    amount: float
    chain_id: int = 1
    address: Optional[str] = None
