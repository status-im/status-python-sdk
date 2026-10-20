# Saved Address

![Status App Wallet](./images/saved-address/overview.png)

A **saved address** is a wallet address kept under a friendly name, so it can be reused instead of being typed out every time. It is the SDK equivalent of the saved addresses in the Status App wallet. A `SavedAddress` is always reached through the [`wallet`](./account.md#wallet) of a logged-in [`Account`](./account.md). **You never construct it directly** - create one with [`add_address`](./wallet.md#add_addressaddress-name-ensnone) and read the existing ones from [`saved_addresses`](./wallet.md#saved_addresses).

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

for saved in account.wallet.saved_addresses.values():
    print(f"{saved.name}\t{saved.address}")
```

Printing a `SavedAddress` lays out its [properties](./saved-address.md#properties) one per line, which is handy while exploring the wallet:

```python
saved = account.wallet.saved_addresses["0xEf5674d64d5A71B6e654A24d8E88b66773D693A6"]
print(saved)
```

```
Address: 0xEf5674d64d5A71B6e654A24d8E88b66773D693A6
Name: Sam
Ens: None
Created At: 2026-05-14 09:21:37
```

Values that are empty - such as an address saved without an [`ens`](./saved-address.md#ens) - are shown as `None`. For the same data as a dictionary, use [`to_dict`](./saved-address.md#to_dict).

## Name

The **name** identifies a saved address for a human reader. It is set while [saving an address](./wallet.md#add_addressaddress-name-ensnone) and can be updated through the [`name`](./saved-address.md#name) property. Names must follow the validation rules enforced by the library and expected by the Status application. A valid name must satisfy all of the following conditions:

- It may contain **letters (`A-Z`, `a-z`)**
- It may contain **numbers (`0-9`)**
- It may contain **underscores (`_`)**
- It may contain **hyphens (`-`)**
- Words may be separated by a **single whitespace**
- It must be **at least 1 character long**
- It **cannot be more than 24 characters long**

Periods, commas, emojis and other symbols are **not allowed**, and neither are leading, trailing or repeated whitespaces.

### Valid examples

```
Sam
Jonathan Rain
jon_rain-01
SNT_PUMP
zoomer_enjoyer_67
```

### Invalid examples

| Example | Reason |
|-------|--------|
| | Too short (minimum length is 1) |
| `a-very-long-saved-address-name` | Too long (maximum length is 24) |
| `Sam,` | Contains invalid character `,` |
| `Jonathan.Rain` | Contains invalid character `.` |
| `thedatabro 🚀` | Contains an emoji |

If a name does not follow these rules, a custom exception is raised.

## Methods

### `delete()`

Delete the saved address from the wallet.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

for saved in account.wallet.saved_addresses.values():
    if saved.name == "Jonathan":
        saved.delete()
```

**Note**: the instance stays usable for **reading** after deletion - `address`, `name`, `ens` and `created_at` still return what they held. Writing to [`name`](./saved-address.md#name-1) or [`ens`](./saved-address.md#ens) raises a custom exception instead of silently recreating the entry.

### `to_dict()`

Turn the saved address into a plain dictionary, with one key per property - `address`, `name`, `ens` and `created_at`.

Returns `dict`.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

saved = account.wallet.saved_addresses["0xEf5674d64d5A71B6e654A24d8E88b66773D693A6"]
print(saved.to_dict())
```

Build a `DataFrame` out of every saved address:

```python
import pandas as pd

addresses = pd.DataFrame([
    saved.to_dict()
    for saved in account.wallet.saved_addresses.values()
])
```

### `validate_name(name)`

Check a name against the [naming rules](./saved-address.md#name) without saving anything. Raises a custom exception when the name is invalid and returns `None` when it is valid. This is useful for validating user input before [saving an address](./wallet.md#add_addressaddress-name-ensnone).

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `name` | `str` | Yes | The name to validate. |

```python
from status_sdk.saved_address import SavedAddress
from status_sdk import exceptions

try:
    SavedAddress.validate_name("Jo,")
except exceptions.InvalidSavedAddressNameError as error:
    print(error)
```

## Properties

### `address`

The saved wallet address, exactly as Status Backend stored it. Addresses saved through [`add_address`](./wallet.md#add_addressaddress-name-ensnone) are **lowercased**, while ones saved from Status App may keep their mixed-case [EIP-55](https://eips.ethereum.org/EIPS/eip-55) form - so compare addresses case-insensitively.

Returns `str`. **Read-only** - the address identifies the entry, so saving a different one creates a separate `SavedAddress` through [`add_address`](./wallet.md#add_addressaddress-name-ensnone) rather than renaming this one.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

saved = account.wallet.saved_addresses["0xEf5674d64d5A71B6e654A24d8E88b66773D693A6"]
print(saved.address)
```

### `name`

Get or update the name the address is saved under. The name must follow the [naming rules](./saved-address.md#name).

Returns `str` when reading. Assigning validates the new name, writes it to Status Backend and only then updates the instance - so a rejected rename leaves the object matching what the backend holds.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

saved = account.wallet.saved_addresses["0xEf5674d64d5A71B6e654A24d8E88b66773D693A6"]

# Read
print(saved.name)

# Update
saved.name = "Jonathan Rain"
```

### `ens`

Get or update the [ENS name](https://status.app/help/profile/transfer-your-ens-name-to-status) of the address. An address saved without one holds an empty string.

Returns `str` when reading.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

saved = account.wallet.saved_addresses["0xEf5674d64d5A71B6e654A24d8E88b66773D693A6"]

# Read
print(saved.ens)

# Update
saved.ens = "therealsamhyde.eth"
```

**Note**: The ENS value is **not** validated by the SDK - whatever you assign is sent to Status Backend as-is.

### `created_at`

When the address was saved.

Returns `datetime.datetime`, or `None` when Status Backend reports no creation time.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token": "token from https://www.infura.io/",
    "alchemy_token": "token from https://www.alchemy.com/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

for saved in account.wallet.saved_addresses.values():
    print(f"{saved.name}\tsaved on {saved.created_at}")
```
