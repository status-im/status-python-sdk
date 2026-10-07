from dataclasses import dataclass, field
from enum import IntEnum
from typing import Self, Optional, Union
import datetime
import uuid
import logging
import json

from . import PaymentRequest


class MessageContentTypeEnum(IntEnum):
    UNKNOWN_CONTENT_TYPE = 0
    TEXT_PLAIN = 1
    STICKER = 2
    STATUS = 3
    EMOJI = 4
    TRANSACTION_COMMAND = 5  # deprecated
    SYSTEM_MESSAGE_CONTENT_PRIVATE_GROUP = 6  # local only
    IMAGE = 7
    AUDIO = 8
    COMMUNITY = 9
    SYSTEM_MESSAGE_GAP = 10  # local only
    CONTACT_REQUEST = 11
    DISCORD_MESSAGE = 12
    IDENTITY_VERIFICATION = 13
    SYSTEM_MESSAGE_PINNED_MESSAGE = 14  # local only
    SYSTEM_MESSAGE_MUTUAL_EVENT_SENT = 15  # local only
    SYSTEM_MESSAGE_MUTUAL_EVENT_ACCEPTED = 16  # local only
    SYSTEM_MESSAGE_MUTUAL_EVENT_REMOVED = 17  # local only
    BRIDGE_MESSAGE = 18

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
class Message:
    id: str
    chat_id: str
    content: str
    text: str
    content_type: str
    from_public_key: str
    compressed_key: str
    timestamp: datetime.datetime
    message_type: int
    chat_type: str
    images_url: list[str]
    source: str
    reply_id: Optional[str] = None
    bridge_id: Optional[str] = None
    response_to: Optional[str] = None
    payment_requests: list[PaymentRequest] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict) -> Self:
        logging.info(f"Raw message {json.dumps(raw)}")
        content_type: int = raw["contentType"]
        msg_type: int = raw["messageType"]
        params = {
            "id": raw["id"],
            "text": raw["text"],
            "chat_id": raw["chatId"],
            "from_public_key": raw["from"],
            "compressed_key": raw["compressedKey"],
            "timestamp": datetime.datetime.fromtimestamp(raw["whisperTimestamp"] / 1_000),
            "source": raw.get("bridgeMessage", {}).get("bridgealloweName", "status"),
            "message_type": raw['contentType'],
            "images_url": []
        }

        if len(raw["responseTo"]) > 0:
            params["reply_id"] = raw["responseTo"]

        params["content"] = raw["text"]
        if msg_type == 1:
            params["chat_type"] = "private"
        elif msg_type in [2, 3]:
            params["chat_type"] = "group"
        elif msg_type == 5:
            params["chat_type"] = "community"
        else:
            params["chat_type"] = "unknown"

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
            params["images_url"] = [raw["image"]] if isinstance(raw["image"], str) else raw["image"]
            params["content_type"] = "image"
        # Bridged Message
        elif content_type == 18:
            params["content"] = raw["bridgeMessage"]["content"]
            params["content_type"] = "text"
            params["bridge_id"] = raw["bridgeMessage"]["messageID"]
            reply_id = raw["bridgeMessage"].get("parentMessageID")
            if isinstance(reply_id, str) and len(reply_id) == 0:
                reply_id = None
            params["reply_id"] = reply_id
        if raw["responseTo"]:
            params["response_to"] = raw["responseTo"]
        payments = raw.get("paymentRequests", [])
        if payments:
            params["payment_requests"] = [
                PaymentRequest.from_raw(payment)
                for payment in payments
            ]
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
