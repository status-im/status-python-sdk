# Account

![Account header image](./images/overview-account.png)

The account class allows you to easily work with a Status account.

## Display name

The **display name** is the human‑readable identifier for a Status account. It is used when creating an account, resolving an existing account during [`login`](./account.md#loginpassword-key_uidnone-display_namenone-mnemonicnone-infura_tokennonecoingecko_api_keynone), and when updating the account name through the [`display_name`](./account.md#display_name) property.

Display names must follow strict validation rules enforced by the library and expected by the Status application. A valid display name must satisfy all of the following conditions:

- It may contain **uppercase letters (`A–Z`)**
- It may contain **spaces (` `)**
- It may contain **numbers (`0–9`)**
- It may contain **hyphens (`-`)**
- It may contain **underscores (`_`)**
- It must be **at least 5 characters long**
- It **cannot be more than 24 characters long**
- It **cannot start or end with a space**

Characters such as spaces, punctuation, emojis, or other symbols are **not allowed**.

### Valid examples

```
alpha_01
STATUS-01
bot_user_5
HELLO123
node-42
```

### Invalid examples

| Example | Reason |
|-------|--------|
| `bot` | Too short (minimum length is 5) |
| ` mybot` | Leading space |
| `mybot ` | Trailing space |
| `bot!123` | Contains invalid character `!` |

If a display name does not follow these rules, a **`ValueError`** will be raised by the account validation logic.

## Backups

Backup files (`.bkp`) can be both created in [Status App](https://our.status.im/status-desktop-v2-35-local-backups-new-home-page-performance-boosts-and-more/) and the [Python SDK](./account.md#backup). 

![Status App Backup](./images/backup.png)

[Status Backend](https://github.com/status-im/status-go) backup folder is exposed in a Docker volume so users can:

- **Upload backup** - by dropping `.bkp` files in the `backups` folder locally (linked to Status Backend Docker container). Backups are automatically uploaded if a [`mnemonic` is provided during `login`](./account.md#loginpassword-key_uidnone-display_namenone-mnemonicnone-infura_tokennonecoingecko_api_keynone).
- **Create backup** - by using [`backup()`](./account.md#backup) or creating one in [Status App](https://our.status.im/status-desktop-v2-35-local-backups-new-home-page-performance-boosts-and-more/).

**Note**: Status App will not automatically backup messages. This has to be manually overridden on the app (above screenshot). When using the Python SDK, the messages are automatically stored in the `.bkp` files.


## Wallet

Wallet features are optional and can be omitted if not required for your use case. They provide functionality equivalent to the **Wallet** and **Market** tabs.

![Status App Wallet](./images/wallet.png)

## `Account(domain="localhost", port=8080, is_secure=False, backup_folder=None)`

Create a new `Account` instance ready to be logged in. The constructor wires the SDK to a running [Status Backend](https://github.com/status-im/status-go) at the given `domain` and `port`, prepares the local `assets/` folder (used for image uploads, such as the [profile picture](./account.md#profile_picture)) and `backups/` folder (used for [backup uploads](./account.md#backups) and recovery).

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `domain` | `str` | No | Domain where Status Backend is reachable. Defaults to `localhost` when running through [`launch_docker_container`](./utils.md#launch_docker_container) on the same machine. **Use the container name when the SDK runs inside the same Docker network as Status Backend.** |
| `port` | `int` | No | Port exposed by Status Backend. Defaults to `8080`. Verify the value in `docker-compose.yaml` if you have customized the setup. |
| `is_secure` | `bool` | No | When `True`, the SDK communicates over `https`; otherwise `http` is used. Defaults to `False`. |
| `backup_folder` | `str` | No | Absolute path on the host machine where `.bkp` files will be stored and loaded from. If not provided, the SDK's own `backups/` folder is used. See [Backups](./account.md#backups). |

The constructor does not log into any account on its own - call [`login`](./account.md#loginpassword-key_uidnone-display_namenone-mnemonicnone-infura_tokennonecoingecko_api_keynone) afterwards. To discover what accounts already exist in the configured data directory, use the [`available_accounts`](./account.md#available_accounts) property, which is also populated automatically during initialization.

Default setup (localhost, port 8080, http):

```python
from bot import Account

account = Account()
```

Use a custom backup folder:

```python
from bot import Account

account = Account(backup_folder="C:/Users/me/status-backups")
```

Connect to a Status Backend running on a different host or port:

```python
from bot import Account

account = Account(
    domain="status-backend.internal",
    port=9090,
    is_secure=True
)
```

**Note**: Status Backend must be running before initializing `Account`. You can launch the backend container with [`launch_docker_container`](./utils.md#launch_docker_container). If the backend is not reachable on `domain:port`, calls to [`login`](./account.md#loginpassword-key_uidnone-display_namenone-mnemonicnone-infura_tokennonecoingecko_api_keynone) will fail.

**Note**: When `backup_folder` is set, [`backup`](./account.md#backup) moves the generated `.bkp` file out of the SDK's internal `backups/` folder into the provided path, and recovery via `mnemonic` will look in this same folder for `.bkp` files to auto-load. Make sure the folder exists and is writable.

## Methods

### `login(password, key_uid=None, display_name=None, mnemonic=None, infura_token=None,coingecko_api_key=None)`

Login to an existing Status account. If the account does not exist in the initialized data directory, a new account will be created and automatically logged in. 

![Account creation](./images/login/create.png)

After a successful login, the decentralized messenger service is automatically started so the account can send and receive messages.

An account can also be recovered if the [`mnemonic`](https://status.app/help/profile/understand-your-status-keys-and-recovery-phrase#about-your-recovery-phrase) is passed.

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `password` | `str` | Yes | Password used to encrypt the account |
| `key_uid` | `str` | Yes* | Unique key identifier of the account. If provided, the account will be logged in directly using this identifier. If not provided, then you must use `display_name` and `password` to login. |
| `display_name` | `str` | Yes* | Display name of the account. Used to resolve the `key_uid` if it is not provided, or to create a new account if one does not already exist. This field is required if an account needs to be recovered with `mnemonic`. |
| `mnemonic` | `str` | No | The [mnemonic](https://status.app/help/profile/understand-your-status-keys-and-recovery-phrase#about-your-recovery-phrase) from [`info`](./account.md#info). Use this field with `password` and `display_name` to recover the account. If you have [`.bkp`](./account.md#backup) files, in the backup Docker volume they will be automatically picked up and loaded.<br><br>**Note**: You can pass a different `display_name` but that will be internal only. When an account is recovered setting [`display_name`](./account.md#display_name) can be buggy. Ideally when recovering the account, use the original `display_name` of the account. |
| `infura_token` | `str` | No | [RPC token](https://www.infura.io/) to allow Status Backend to use a wallet. |
| `coingecko_api_key` | `str` | No | [API token](https://www.coingecko.com/) to allow Status Backend to use a wallet. |

Returns the current `Account` instance, allowing method chaining.

#### Login with `display_name`
```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)
```

The code above is equivalent to the following screen on Status App:

![Log in screen](./images/login/log-in.png)

**Note**: This assumes that `display_name` and is unique for every `key_uid`. If there are duplicated `display_names` then the first found match will be used. You can log in with `key_uid` if you have `display_name` duplicates.

#### Login with `key_uid`

```python
from bot import Account

account = Account()
params = {
    "key_uid": "0xff2c3...",
    "password": "SNTPUMP"
}
account.login(**params)
```

#### Recover account

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "mnemonic" : "phrase_1 phrase_2 phrase_3 phrase_4 phrase_5 phrase_6 phrase_7 phrase_8 phrase_9 phrase_10 phrase_11 phrase_12"
}
account.login(**params)
```

The code above is equivalent to the following screen on Status App:

![Recover screen](./images/login/recover.png)

**Note**: When in recovery mode, the display name is updated on Status App as well so it is consistent locally and to other users.

#### Wallet setup

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)
```

**Note**: `infura_token` and `coingecko_api_key` can be used when creating, recovering and logging in to an account.

### `logout()`

Logout from the currently logged-in Status account. This method also clears the internal account state and stops the active messenger session. This function is also supported in `del` and when the script automatically finishes.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Optional - even if not specified __del__ will log you out
account.logout()
```

Returns the current `Account` instance. This allows chaining additional operations if needed.

**Note**: Currently `logout` works for a single sign in and may break because it does not listen for [`signals`](./account.md#signal).

### `backup()`

Create a **local backup file** (`.bkp`) for the currently logged‑in account. The backup is generated by the Status Backend and stored inside the configured Docker backup volume. Each file is uniquely associated with an account. If the backup creation fails, an **exception will be raised**.

Returns `str` representing the **Docker path** of the generated backup file. The returned path refers to the **Docker container path** where the backup was created. If the backup directory is mounted as a Docker volume, the file will also appear on the host machine in the mapped folder.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

backup_path = account.backup()
print(f"Backup created at: {backup_path}")
```

### Chat

#### `send_message(chat_id, message)`

Send a text message to a specific chat. This method currently supports **text messages only**.

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `chat_id` | `str` | Yes | Identifier of the chat where the message will be sent. All available chat IDs can be obtained from the [`chats`](./account.md#chats) property. |
| `message` | `str` | Yes | The text message to send. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# This is under the assumption you already have a contact / joined a community
chat = account.chats[0]
account.send_message(chat["id"], "Hello from my Status bot!")
```

#### `get_messages(chat_id, start_timestamp=None, end_timestamp=None)`

Retrieve messages from the specified chat within an optional time range. Messages are returned in **descending order** (newest to oldest). The method automatically paginates through the backend until all messages in the specified range are collected. This method is ideal for backfilling, [batch processing](https://aws.amazon.com/what-is/batch-processing/) or [micro batch processing](https://www.dremio.com/wiki/micro-batch-processing/).

Messages can be fetched from:
- **Direct messages** - current contacts and contacts that were later removed
- **Community channels** - the bot must have read access from the admin

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `chat_id` | `str` | Yes | Identifier of the chat. All available chat IDs can be obtained from the [`chats`](./account.md#chats) property. |
| `start_timestamp` | `datetime.datetime` | No | The earliest timestamp to include. Messages older than this value will stop the fetch process. |
| `end_timestamp` | `datetime.datetime` | No | The latest timestamp to include. Messages newer than this value will be skipped. |

Returns `list[dict]` containing message objects. Timestamp fields returned by the backend are automatically converted into `datetime.datetime` objects.

```python
from bot import Account
import datetime

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

chat = account.chats[0]

messages = account.get_messages(
    chat_id=chat["id"],
    start_timestamp=datetime.datetime(2024, 1, 1)
)

for message in messages:
    print(f"{message['timestamp']}\t{message['text']}")
```

**Note**: If there are missing messages in a chat that might be because the node (Status Backend) has not received them yet. They may appear later.

#### `listen_messages()`

Listen for new incoming messages **in real time**. This method yields raw message events as they are received from the Status Backend [signal](./account.md#signallisten) `messages.new`. This method is ideal for developing real time chat applications

```python
from bot import Account
import datetime
# For terminal readability only
from rich import print as rprint
from rich.pretty import Pretty

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for msg in account.listen_messages():
    rprint(Pretty(msg))
```

**Note**: If you receive multiple messages at once, `contacts` and `chats` will grow.

#### `add_contact(public_key, display_name=None)`

Send a contact request or approve an existing contact request. The mode depends on how the contact shows up in [`contacts`](./account.md#contacts). Best practice would be to look at the the following [`contacts`](./account.md#contacts) keys:

- `has_added_us` - `bool` value to check if the other user has added the account as a friend
- `added` - `bool` value to check if the account has added the other user as a friend
- `mutual` - `bool` value to check if the account and other user are in contacts
- `contact_state` - `str` value to see the account's current state
- `external_contact_state` - `str` value to see the other user's state as it is in your node

Modes:

- **Approve mode** - `has_added_us` is `True` and `added` is `False`
- **Add mode** - `has_added_us` is `False`

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `public_key` | `str` | Yes | The contact's Status public key. |
| `display_name` | `str` | Yes / No | Display name for the contact. If the contact already exists in [`contacts`](./account.md#contacts), the `display_name` parameter is optional and the existing name will be reused. If the contact has **never interacted with the bot before**, `display_name` must be provided so the contact can be created locally. |

Returns the current `Account` instance, allowing method chaining.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Send a contact request
account.add_contact(
    public_key="0x04ebcad...",
    display_name="nickninov"
)
```

#### `remove_contact(public_key)`

Remove a contact or decline a pending contact request. The mode depends on how the contact shows up in [`contacts`](./account.md#contacts). Best practice would be to look at the the following [`contacts`](./account.md#contacts) keys:

- `has_added_us` - `bool` value to check if the other user has added the account as a friend
- `added` - `bool` value to check if the account has added the other user as a friend
- `mutual` - `bool` value to check if the account and other user are in contacts
- `contact_state` - `str` value to see the account's current state
- `external_contact_state` - `str` value to see the other user's state as it is in your node

Modes:

- **Remove** - `has_added_us` is `True` and `added` is `True`
- **Reject mode** - `has_added_us` is `True`

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `public_key` | `str` | Yes | The contact's Status public key. This value corresponds to the key used in [`contacts`](./account.md#contacts). |

Returns `bool`.

| Value | Meaning |
|------|--------|
| `True` | The contact was successfully removed or the request was declined. |
| `False` | The contact does not exist or was already removed. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# NOTE: contacts are returned as a dict for 
# internal class checks and scalability
contact = list(account.contacts.values())[0]

removed = account.remove_contact(contact["public_key"])
print(f"Removed: {removed}")
```

#### `send_request_community(url)`

Send a request to join a community using its invitation URL. The method parses the shared Status community URL and submits a join request using the currently logged-in account. The account's [wallet address](./account.md#info) is provided to the community.

**This method works with community invites instead of specific community channel ones. Method is currently unstable.**

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `url` | `str` | Yes | The shared Status community invitation URL. |

Returns `datetime.datetime` representing when the join request was submitted.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

account.send_request_community(
    "https://status.app/c/community-invite-link"
)
```

### Wallet

#### `get_tokens()`

Retrieve all tokens available in Status Backend across all supported chains.

Returns `pd.DataFrame`.


| Column | Type | Description |
|--------|------|-------------|
| `chain_id` | `int` | Chain ID where the token exists. Matches values from [`chains`](./account.md#chains). |
| `address` | `str` | Token contract address. |
| `symbol` | `str` | Token symbol (e.g. `ETH`, `USDT`). |
| `decimals` | `int` | Number of decimals used for the token. |
| `cross_chain_id` | `str`<br>`None` | Cross-chain identifier (if available). |
| `source_id` | `str` | Source list from which the token was fetched. |

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)
available_tokens = account.get_tokens()
```

#### `get_balance(token_addresses, chain_ids=1, wallets=None, ccy=None)`

Retrieve token balances for one or more wallets across specified chains. This method supports querying multiple tokens, chains, and wallets. Balances are adjusted using token decimals. Optionally, values can be converted to fiat currencies.

Returns `pd.DataFrame`.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `datetime.datetime` | Timestamp when the balance was fetched. |
| `wallet_address` | `str` | Wallet address for which the balance was retrieved. |
| `token_address` | `str` | Token contract address. |
| `token_symbol` | `str` | Token symbol (e.g. `ETH`, `USDT`). |
| `amount` | `float` | Token balance (adjusted using token decimals). |
| `chain_id` | `int` | Chain ID where the token exists. |
| `ccy` | `str` | Fiat currency (only present if `ccy` is provided). |
| `price` | `float` | Token price **for 1 `token_symbol`** in the given fiat currency (only present if `ccy` is provided). If you want to get the amount in the wallet, you must `amount * price`. |

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

token_mapping = {
    'ETH': '0x0000000000000000000000000000000000000000',
    'SNT': '0x744d70fdbe2ba4cf95131626614a1763df805b9e',
    'USDT': '0xdac17f958d2ee523a2206206994597c13d831ec7',
    'CELO': '0x9b88d293b7a791e40d36a39765ffd5a1b9b5c349'
}
token_addresses = list(token_mapping.values())
# Returns data for logged in wallet
data = account.get_balance(token_addresses)
```

Access multuple chains:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

token_mapping = {
    'ETH': '0x0000000000000000000000000000000000000000',
    'SNT': '0x744d70fdbe2ba4cf95131626614a1763df805b9e',
    'USDT': '0xdac17f958d2ee523a2206206994597c13d831ec7',
    'CELO': '0x9b88d293b7a791e40d36a39765ffd5a1b9b5c349'
}
token_addresses = list(token_mapping.values())
chain_ids = [1, 10] # Can be a single int value as well
# Returns data for logged in wallet
data = account.get_balance(token_addresses, chain_ids)
```

Access multiple wallets:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

token_mapping = {
    'ETH': '0x0000000000000000000000000000000000000000',
    'SNT': '0x744d70fdbe2ba4cf95131626614a1763df805b9e',
    'USDT': '0xdac17f958d2ee523a2206206994597c13d831ec7',
    'CELO': '0x9b88d293b7a791e40d36a39765ffd5a1b9b5c349'
}
token_addresses = list(token_mapping.values())
chain_ids = [1, 10] # Can be a single int value as well

vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
bot_wallet = account.info["wallet_address"]
wallets = [bot_wallet, vitalik_address]

data = account.get_balance(token_addresses, chain_ids, wallets)
```

Get token prices:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

token_mapping = {
    'ETH': '0x0000000000000000000000000000000000000000',
    'SNT': '0x744d70fdbe2ba4cf95131626614a1763df805b9e',
    'USDT': '0xdac17f958d2ee523a2206206994597c13d831ec7',
    'CELO': '0x9b88d293b7a791e40d36a39765ffd5a1b9b5c349'
}
token_addresses = list(token_mapping.values())
chain_ids = [1, 10] # Can be a single int value as well

vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
bot_wallet = account.info["wallet_address"]
wallets = [bot_wallet, vitalik_address] # Can be a single str value as well
ccy = ["GBP", "USD"] # Can be a single str value as well

data = account.get_balance(token_addresses, chain_ids, wallets, ccy)
```

#### `get_market(token_addresses, chain_ids=1, ccy="USD")`

Retrieve market data for one or more tokens across specified chains. 

Returns `pd.DataFrame`.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `datetime.datetime` | Timestamp when the market data was fetched. |
| `chain_id` | `int` | Chain ID where the token exists. |
| `token_address` | `str` | Token contract address. |
| `token_symbol` | `str` | Token symbol (e.g. `ETH`, `USDT`). |
| `fiat_ccy` | `str` | Fiat currency used for the market data. |
| `market_cap` | `float` | Total market capitalization of the token. |
| `high_price` | `float` | Highest price in the last 24 hours. |
| `low_price` | `float` | Lowest price in the last 24 hours. |
| `pnl_24hr` | `float` | Absolute price change over the last 24 hours. |
| `pct_change` | `float` | Percentage price change (day-level). |
| `pct_change_1hr` | `float` | Percentage price change over the last hour. |
| `pct_change_24hr` | `float` | Percentage price change over the last 24 hours. |


#### `send_transaction(address, symbol, amount, chain_id=1)`

Send crypto from the logged-in account's wallet to another wallet address on the same chain. This method supports both **ETH** and **ERC-20** tokens. The token can be identified either by its Status symbol (e.g. `ETH`, `SNT`, `USDT`) or by its contract address. Before broadcasting, the method validates that the token exists on the given chain and that the wallet holds enough balance for the requested `amount`.

| Name | Type | Required | Description |
|-----|-----|-----|-------------|
| `address` | `str` | Yes | The wallet address of the receiver. |
| `symbol` | `str` | Yes | Either a valid Status token symbol from [`get_tokens`](./account.md#get_tokens) or the token's contract address (must start with `0x`). |
| `amount` | `float` | Yes | The amount of the token to send. Must be less than or equal to the wallet's current balance for that token. |
| `chain_id` | `int` | No | Chain ID where the transaction will be broadcast. Defaults to `1` (Ethereum mainnet). All available chain IDs can be obtained from the [`chains`](./account.md#chains) property. |

Returns `str` representing the **transaction hash**. The hash can be appended to `https://etherscan.io/tx/` to monitor the transaction's progress. The transaction URL is also written to [`logger`](./account.md#logger) at `INFO` level. If the backend fails to broadcast and does not return a hash, `None` is returned instead.

Send ETH:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

tx_hash = account.send_transaction(
    address=vitalik_address,
    symbol="ETH",
    amount=0.01
)
print(f"Transaction: https://etherscan.io/tx/{tx_hash}")
```

Send an ERC-20 token by symbol:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

tx_hash = account.send_transaction(
    address=vitalik_address,
    symbol="SNT",
    amount=10
)
```

Send an ERC-20 token by contract address:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
snt_address = "0x744d70fdbe2ba4cf95131626614a1763df805b9e"

tx_hash = account.send_transaction(
    address=vitalik_address,
    symbol=snt_address,
    amount=10
)
```

Send on a different chain:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)

vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

tx_hash = account.send_transaction(
    address=vitalik_address,
    symbol="ETH",
    amount=0.01,
    chain_id=10 # Optimism
)
```

**Note**: This is a wallet method, so it requires both `infura_token` and `coingecko_api_key` to be provided in [`login`](./account.md#loginpassword-key_uidnone-display_namenone-mnemonicnone-infura_tokennonecoingecko_api_keynone). If either is missing, an exception will be raised when this method is called.

**Note**: The sender and receiver must be on the **same chain**. Cross-chain transfers are not supported by this method - set `chain_id` to the chain where the funds currently exist.

**Note**: An **exception will be raised** when:
- the `symbol` (or contract address) does not exist on the given `chain_id`
- the token is not present in the logged-in wallet's balance
- the requested `amount` exceeds the current wallet balance

## Properties

### `available_accounts`

Returns all Status accounts that are **locally available** in the initialized data directory. These accounts are detected when the `Account` class is initialized.

This property is useful when you want to:
- inspect which accounts exist locally
- retrieve a `key_uid` for login
- display metadata about stored accounts

**You will have to know the passwords for the given `key_uid`.**

Returns `list[dict]`.

```python
from bot import Account
# For terminal readability only
from rich import print as rprint
from rich.pretty import Pretty

account = Account()

rprint(Pretty(account.available_accounts))
```

### `info`

Provides information about the currently logged-in account. If `login()` has not been called, accessing this property will raise an exception. Returns `dict` containing account metadata.

| Key | Type | Description |
|----|----|-------------|
| `public_key` | `str` | Public key that uniquely identifies the account. |
| `url` | `str` | The URL that can be shared with other users. |
| `emojis` | `str` | Emoji hash associated with the account identity. |
| `key_uid` | `str` | Internal Status key identifier for the account. |
| `compressed_key` | `str` | The chat key as it is in Status App. |
| `mnemonic` | `str` | Mnemonic phrase used to generate the account keys. |
| `display_name` | `str` | Display name of the account. |
| `password` | `str` | Password used to encrypt the account locally. |
| `wallet_address` | `str` | Ethereum wallet address associated with the account. |
| `logged_in_timestamp` | `datetime.datetime` | Timestamp when the account successfully logged in. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

print(account.info)
```

### `display_name`

Get or update the current display name of the logged‑in account.

Returns `str` when reading the property.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Get the current display name
print(account.display_name)
```

You can update the display name by assigning a new value:

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Change the display name
account.name = "status_bot_42"
print(account.display_name)
```

**Note**: Next time you login with the changed display name, you will have to put in the new display name, instead of the initial one.

### `bio`

Get or update the **bio** of the currently logged‑in account. The length of the bio (as in Status App) is 240 characters.

Returns `str` when reading the property.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Read the current bio
print(account.bio)
```

The value assigned to `bio` will automatically be converted to a string before being sent to the backend. You can update the bio by assigning a new value:

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Update the bio
account.bio = "Monitoring Status communities and chats"
print(account.bio)
```

You can also **clear the bio** by deleting the property:

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Clears the bio - same as: 
# account.bio = ""
# account.bio = None
del account.bio
```

### `profile_picture`

Get or update the **profile picture** of the currently logged‑in account. The image is the same one shown on the user's profile in Status App.

Returns `PIL.Image.Image` when reading the property, or `None` if no profile picture has been set.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Read the current profile picture
image = account.profile_picture
if image:
    image.show()
```

The file path assigned to `profile_picture` will be automatically set as the latest profile picture in Status App. If the given file does not exist or the extension is not supported, an **exception will be raised**. Supported image formats are `.jpg`, `.jpeg` and `.png`.

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Update the profile picture
account.profile_picture = "./full_path/to/my_image.png"
account.profile_picture.show()
```

When a new profile picture is set, any previous image in the **assets** folder is removed. The image is also copied into the Status Backend Docker volume so it is picked up by the backend when updating the account identity.

### `signal`

The property exists in `Account` because signals require an **active logged‑in session**. Attempting to use signals before calling `login()` will raise an exception. Signals are low‑level events emitted by the Status Backend. Examples include:

- `messages.new`
- `message.delivered`
- `node.ready`
- `node.started`
- `node.login`
- `node.stopped`

The property exposes two primary methods:

- `signal.get()` - fetch a single event. If the event is not found, you may end up in an infinite loop.
- `signal.listen()` - stream events continuously. Example usage of this is found in [`listen_messages()`](./account.md#listen_messages)

### `logger`

Provides access to the internal **Python logger** for monitoring the lifecycle of the account and backend operations such as login, account creation, messenger startup, and recovery.

Returns `logging.Logger`.

Default logger configuration:

- **Name**: `status-bot`
- **Level**: `INFO`
- **Output**: standard output (terminal)

Example:

```python
from bot import Account

account = Account()

account.logger.info("Starting Status bot")
account.logger.warning("This is a warning")
account.logger.error("Something went wrong")
```

### Chat

#### `contacts`

This property returns contacts that have interacted with the account, including:

- active contacts.
- users who sent a contact request.
- users whose contact request was sent by the bot.
- contacts that were previously removed. If the contact is removed on both sides then it might disappear from the property.

The property always fetches the latest state directly from the Status Backend. The lifecycle is as follows:
  - `none` - no relationship
  - `sent` - request sent by this account
  - `received` - request received from another account
  - `mutual` - both users have added each other

Returns `dict[str, dict]` where the key is the contact's **public key**. This makes internal searching for account specific information faster.

| Key | Type | Description |
|----|----|-------------|
| `public_key` | `str` | Public key that uniquely identifies the contact. |
| `url` | `str` | The URL that can be shared with other users. |
| `chat_id` | `str` | Chat identifier used for direct messaging. |
| `compressed_key` | `str` | Internal compressed key identifier used by Status Backend. |
| `emojis` | `str` | Emoji hash associated with the contact identity. |
| `contact_state` | `str` | Current state of the contact relationship (`none`, `mutual`, `sent`, `received`, `dismissed`). |
| `external_contact_state` | `str` | How the contact relationship appears from the other user's perspective. |
| `has_added_us` | `bool` | Whether the other user has added this account as a contact. |
| `added` | `bool` | Whether this account has added the other user as a contact. |
| `mutual` | `bool` | Whether both users have added each other. |
| `display_name` | `str` | The current display name of the contact. |
| `bio` | `str` | The contact's profile bio. |
| `wallet_address` | `str` | Ethereum wallet address associated with the contact. |
| `last_updated` | `datetime.datetime` | Timestamp when the contact information was last updated. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

contacts = account.contacts

for contact in contacts.values():
    print(contact["display_name"], contact["contact_state"])
```

#### `communities`

Get all communities that the account is currently a member of. This property always fetches the **latest community state** directly from the Status Backend. This ensures dynamic values such as community metadata, members, and channel permissions are always up to date.

Each community contains information about:

- community metadata (name, description, tags)
- membership status
- number of members
- available channels and their permissions

Returns `list[dict]` where each element represents a community.

| Key | Type | Description |
|----|----|-------------|
| `id` | `str` | Unique identifier of the community. |
| `url` | `str` | The URL that can be shared with other users. |
| `name` | `str` | Name of the community. |
| `verified` | `bool` | Whether the community is verified. |
| `description` | `str` | Community description. |
| `dialog` | `str` | Intro message shown when joining the community. |
| `leaving_message` | `str` | Message shown when leaving the community. |
| `tags` | `list[str]` | Tags associated with the community. |
| `is_member` | `bool` | Whether the account is currently a member of the community. |
| `joined_timestamp` | `datetime.datetime` | Timestamp when the account joined the community. |
| `requested_timestamp` | `datetime.datetime` | Timestamp when the join request was submitted. |
| `encrypted` | `bool` | Whether the community messaging is encrypted. |
| `members` | `int` | Total number of community members. |
| `channels` | `list[dict]` | List of channels available in the community. |

Each channel contains:

| Key | Type | Description |
|----|----|-------------|
| `id` | `str` | Channel identifier inside the community. |
| `chat_id` | `str` | Combined community + channel ID used for sending messages. |
| `url` | `str` | The URL that can be shared with other users. |
| `name` | `str` | Channel name. |
| `description` | `str` | Channel description. |
| `permissions` | `dict` | Permissions for the channel. |

Channel `id` values can be used directly with [`send_message`](./account.md#send_messagechat_id-message)

Channel permissions:

| Key | Type | Description |
|----|----|-------------|
| `posting` | `bool` | Whether the account can post messages in the channel. |
| `viewing` | `bool` | Whether the account can view messages in the channel. |
| `reactions` | `bool` | Whether the account can react to messages. |
| `token_gated` | `bool` | Whether the channel requires a token to participate. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for community in account.communities:
    print(community["name"], community["members"])

    for channel in community["channels"]:
        print(f"\t#{channel['name']} posting: {channel['permissions']['posting']}")
```

#### `community_members`

Get member information for all visible communities that the account is in. It can be useful to review community membership, identify suspicious profiles, or filter genuine community members. For each community member, an additional RPC call is made to fetch profile information such as `display_name`, `bio` and `url`. This can make the property slower for larger communities.

Returns `pd.DataFrame`.

| Column | Type | Description |
|--------|------|-------------|
| `community_id` | `str` | Unique identifier of the community. |
| `community_name` | `str` | Name of the community that the member belongs to. |
| `public_key` | `str` | Public key that uniquely identifies the community member. |
| `chat_id` | `str` | Chat identifier used when sending messages. |
| `display_name` | `str` | Current display name of the member. If unavailable, a fallback name is generated from the compressed key and Status URL. |
| `url` | `str` | Shareable Status profile URL for the member. |
| `bio` | `str` | Profile bio of the member, if available. |
| `roles` | `list[int]` | Roles that the community member has. |
| `compressed_key` | `str` | The member's compressed chat key as shown in Status App. |
| `emoji_hash` | `str` | The member's compressed chat key as shown in Status App. |
| `status_alias` | `str` | Initial display name of the member when the account was created. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

members = account.community_members
print(community_members.head().to_markdown(index=False))
```

#### `chats`

Get all chats that the account can **send messages to**. This includes:
- [`contacts`](./account.md#contacts) - direct messages with users
- [`communities`](./account.md#communities) - community channels where the account has **posting permission**
- Group chats that the account is in

Returns `list[dict]` where each `dict` represents a chat that can be used with [`send_message`](./account.md#send_messagechat_id-message) and [`get_messages`](./account.md#get_messageschat_id-start_timestampnone-end_timestampnone).

| Key | Type | Description |
|----|----|-------------|
| `type` | `str` | Type of chat (`contact`, `channel` or `group_chat`). |
| `id` | `str` | Chat identifier used when sending messages. |
| `name` | `str` | Either the display name of the user or the community channel name. |

```python
from bot import Account

account = Account()
params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# This is under the assumption you already have a contact / joined a community
for chat in account.chats:
    print(f"{chat['type']}\t{chat['name']}\t{chat['id']}")
```

### Wallet

#### `chains`

Retrieve all **production blockchain networks** available in Status Backend. This property returns a mapping between `chain_id` and the corresponding **chain name**.

Returns `dict[int, str]`.


| Key | Type | Description |
|-----|------|-------------|
| `chain_id` | `int` | Unique identifier of the blockchain network. |
| `chain_name` | `str` | Human-readable name of the chain (e.g. `Ethereum`, `Optimism`). |


```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)
print(account.chains)
```

#### `balance`

Retrieve the current **non-zero balances** token balances for the **logged-in account wallet** across all supported chains.

Returns `pd.DataFrame`.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `datetime.datetime` | Timestamp when the balance was fetched. |
| `address` | `str` | Token contract address. |
| `chain_id` | `int` | Chain ID where the token exists. |
| `amount` | `float` | Token balance (adjusted using token decimals). |
| `symbol` | `str` | Token symbol (e.g. `ETH`, `USDT`). |

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)
print(account.balance)
```

You can convert the current balance into fiat currency by using a [ISO 4217 currency code](https://www.iso.org/iso-4217-currency-codes.html) in the `[]` accessor:

```python
from bot import Account

account = Account()

params = {
    "display_name": "status-app-bot",
    "password": "SNTPUMP",
    "infura_token" : "token from https://www.infura.io/",
    "coingecko_api_key": "API key from https://www.coingecko.com/"
}
account.login(**params)
print(account["GBP"])
```
