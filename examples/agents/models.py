from pydantic import BaseModel, Field, AfterValidator
from typing import Optional, Literal, Annotated
import re

def validate_date(value: str) -> str:
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", value):
        raise ValueError(f"Expected YYYY-MM-DD, got '{value}'")
    return value

DateStr = Annotated[str, AfterValidator(validate_date)]

class AccountBalanceInput(BaseModel):
    ccy: str = Field(description="ISO 4217 alpha code to represent the fiat currency", default="USD")
    include_market: bool = Field(default=False, description="If market related information should be included per token in the final output")

class TokenSearchInput(BaseModel):
    chain_id: Optional[int] = Field(description="Chain ID where the token exists.", default=None)
    token_symbols: Optional[list[str]] = Field(description="Token Symbol for the given Chain ID", default=None)

class BalanceSearchInput(BaseModel):
    chain_id: int = Field(description="Chain ID where the token exists.", default=1)
    token_addresses: list[str] = Field(description="Token Addresses for the given Chain ID")
    wallet_address: str = Field(description="The wallet address that will be looked up")
    ccy: str = Field(description="ISO 4217 alpha code to represent the fiat currency", default="USD")

class AccountContactInput(BaseModel):
    display_name: Optional[str] = Field(description="The current display name of the contact", default=None)
    status: Literal['has_added_us', 'added', 'mutual', 'groups'] = Field(description=(
        "If `has_added_us` then the contact request is pending on my side. "
        "If `added` then the contact request is pending on the other user's side. "
        "If `added` then both the account and other account are contacts. "
        "If `group` then all group chats will be returned"
    ))

class AccountContactManagementInput(BaseModel):
    public_key: str = Field(description="The contact's public key that will be modified")
    action: Literal['accept', 'reject'] = Field(description=(
        "If `accept` and the contact is pending then the contact request will be accepted. "
        "If `accept` and there is no pending request then the contact will be sent a request. "
        "If `reject` and the contact is pending then the contact request will be declined. "
        "If `reject` and the contact exists then the contact will be removed."
    ))
    display_name: Optional[str] = Field(description="Required only if a new contact is being created. If a request is pending to be accepted, then this field is not required.")

class MessageInput(BaseModel):
    chat_id: str = Field(description="Required to send messages and fetch messages")
    message: Optional[str] = Field(description="Required to send messages", default=None)
    start_date: Optional[DateStr] = Field(description="Required to fetch chat messages from the specified date. Date should be in YYYY-MM-DD format.", default=None)
    end_date: Optional[DateStr] = Field(description="Required to fetch chat messages to the specified date. Date should be in YYYY-MM-DD format.", default=None)


class NoArgs(BaseModel):
    pass
