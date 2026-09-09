from dataclasses import dataclass, field
from typing import Self, Optional, Union
import datetime, uuid

@dataclass
class ContactRequest:
    id: str
    public_key: str
    incoming: bool = False
    accepted: bool = False
    removed: bool = False

    def __post_init__(self):
        if not (self.incoming or self.accepted or self.removed):
            raise ValueError(f"A {self.__class__.__name__} must be `incoming`, `accepted` or `removed`")

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
class BridgedContent:
    message: str
    name: Optional[str] = None
    username: Optional[str] = None
    user_id: Optional[Union[str, int]] = None
    reply_to_message_id: Optional[Union[str, int]] = None
    message_id: Optional[Union[str, int]] = None
    image_url: Optional[str] = None

    def __post_init__(self):
        to_string = lambda value: str(value) if isinstance(value, int) else value

        self.user_id = to_string(self.user_id)
        self.reply_to_message_id = to_string(self.reply_to_message_id)
        self.message_id = to_string(self.message_id)

    @property
    def status_go_params(self) -> dict:
        content = {
            "bridgeName": self.name or "Unknown",
            "userName": self.username or "Anon",
            "userAvatar": self.image_url or "",
            "userID": self.user_id or str(uuid.uuid4()),
            "content": self.message,
            "messageID": self.message_id or str(uuid.uuid4()),
            "parentMessageID": self.reply_to_message_id or "",
        }
        return content

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
