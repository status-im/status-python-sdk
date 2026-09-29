from dataclasses import dataclass
from typing import Self

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


