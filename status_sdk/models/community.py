from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CommunityRequest:
    id: str
    public_key: str
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
