from dataclasses import dataclass, field
from typing import Self, Optional
import datetime

@dataclass
class ContactRequest:
    public_key: str
    incoming: bool = False
    accepted: bool = False

    def __post_init__(self):
        if not (self.incoming or self.accepted):
            raise ValueError("A ContactRequest must be `incoming` or `accepted`")

@dataclass
class PaymentRequest:
    to_address: str
    token_symbol: str
    token_address: str
    chain_id: int
    amount: str

    @classmethod
    def from_raw(cls, raw: dict) -> Self:
        chain_id, token_address = raw["tokenKey"].split("-")
        params = {
            "to_address": raw["receiver"],
            "token_symbol": raw["symbol"],
            "token_address": token_address,
            "chain_id": int(chain_id),
            "amount": raw["amount"]
        }
        return cls(**params)

@dataclass
class Message:
    id: str
    chat_id: str
    content: str
    content_type: str
    from_public_key: str
    timestamp: datetime.datetime
    chat_type: str
    source: str
    reply_id: Optional[str] = None
    bridge_id: Optional[str] = None
    payment_requests: list[PaymentRequest] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict) -> Self:
        content_type: int = raw["contentType"]
        msg_type: int = raw["messageType"]
        params = {
            "id": raw["id"],
            "chat_id": raw["chatId"],
            "from_public_key": raw["from"],
            "timestamp": datetime.datetime.fromtimestamp(raw["whisperTimestamp"] / 1_000),
            "source": raw.get("bridgeMessage", {}).get("bridgeName", "status")
        }

        if len(raw["responseTo"]) > 0:
            params["reply_id"] = raw["responseTo"]

        if msg_type == 5:
            params["chat_type"] = "community"

        elif msg_type == 1:
            params["chat_type"] = "private"

        elif msg_type in [2, 3]:
            params["chat_type"] = "group"

        # Text & Emojis
        if content_type in [1, 4]:
            params["content"] = raw["text"]
            params["content_type"] = "text" if content_type == 1 else "image"
        # Sticker
        elif content_type == 2:
            params["content"] = raw["sticker"]["url"]
            params["content_type"] = "sticker"
        # Image
        elif content_type == 7:
            img_path = raw["image"]
            text = raw["text"]
            caption = f"{text}\n\n" if len(text) > 0 else ""
            params["content"] = f"{caption}{img_path}"
            params["content_type"] = "image"
        # Bridged Message
        elif content_type == 18:
            params["content"] = raw["bridgeMessage"]["bridgeName"]
            params["content_type"] = "text"
            params["bridge_id"] = raw["bridgeMessage"]["messageID"]

        payments = raw.get("paymentRequests", [])
        if payments:
            params["payment_requests"] = [
                PaymentRequest.from_raw(payment)
                for payment in payments
            ]
        return cls(**params)


@dataclass
class CommunityRequest:
    id: str
    state: str
    public_key: str

@dataclass
class TokenPermission:
    symbol: str
    amount: float
    chain_id: int = 1
    address: Optional[str] = None
