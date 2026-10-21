"""Recording, credential-free Alchemy responses for real Account method tests."""

from copy import deepcopy
from urllib.parse import urlparse

from status_sdk.account import Account


WALLET_ADDRESS = "0x1111111111111111111111111111111111111111"
OTHER_ADDRESS = "0x2222222222222222222222222222222222222222"
CHAINS = {"eth-mainnet": 1, "base-mainnet": 8453}
UNSET = object()


def make_account(token="fixture-key", transactions=None):
    """Avoid login/backend initialization; exercise the imported production method."""
    account = Account.__new__(Account)
    account._Account__alchemy_token = token
    account._Account__transactions = transactions
    account._Account__info = {"wallet_address": WALLET_ADDRESS}
    return account


def transfer(block="0x64", transaction_hash="0xabc", sender=WALLET_ADDRESS,
             recipient=OTHER_ADDRESS, value=1.25, metadata=UNSET, symbol="ETH"):
    result = {
        "blockNum": block,
        "hash": transaction_hash,
        "from": sender,
        "to": recipient,
        "value": value,
        "asset": symbol,
        "category": "external",
        "rawContract": {"address": None, "decimal": "0x12", "value": "0x1"},
    }
    if metadata is not UNSET:
        result["metadata"] = metadata
    return result


class JsonResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return deepcopy(self.body)


class RecordingAlchemy:
    """Callable requests.post replacement, also reusable by a loopback server.

    pages maps (domain, direction, page_key) to result dictionaries; direction is
    fromAddress or toAddress, and the initial page key is ''. Unspecified pages
    return no transfers. blocks maps (domain, hexadecimal height) to hexadecimal
    timestamps or None. fail_on maps (domain, method, selector) to exceptions:
    selector is (direction, page_key) for transfers, or the height for blocks.
    """

    def __init__(self, pages=None, blocks=None, fail_on=None):
        self.pages = deepcopy(pages or {})
        self.blocks = dict(blocks or {})
        self.fail_on = dict(fail_on or {})
        self.calls = []

    def __call__(self, url, json, **kwargs):
        domain = urlparse(url).hostname.split(".")[0]
        method = json["method"]
        params = deepcopy(json["params"])
        self.calls.append({"domain": domain, "method": method, "params": params})
        if method == "alchemy_getAssetTransfers":
            query = params[0]
            direction = "fromAddress" if "fromAddress" in query else "toAddress"
            page_key = query.get("pageKey") or ""
            selector = (direction, page_key)
            key = (domain, direction, page_key)
            failure = self.fail_on.get((domain, method, selector))
            if failure is not None:
                raise failure
            result = deepcopy(self.pages.get(key, {"transfers": []}))
            if query.get("withMetadata") is not True:
                for item in result.get("transfers", []):
                    item.pop("metadata", None)
        elif method == "eth_getBlockByNumber":
            block_number = params[0]
            failure = self.fail_on.get((domain, method, block_number))
            if failure is not None:
                raise failure
            key = (domain, block_number)
            if key not in self.blocks:
                raise AssertionError(f"Unexpected block lookup: {key}")
            timestamp = self.blocks[key]
            result = None if timestamp is None else {"timestamp": timestamp}
        else:
            raise AssertionError(f"Unexpected RPC method: {method}")
        return JsonResponse({"jsonrpc": "2.0", "id": json.get("id", 1), "result": result})

    @property
    def transfer_calls(self):
        return [call for call in self.calls if call["method"] == "alchemy_getAssetTransfers"]

    @property
    def block_calls(self):
        return [call for call in self.calls if call["method"] == "eth_getBlockByNumber"]
