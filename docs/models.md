# Models

## `Message`

Returned by [`listen_events`](./account.md#listen_events), [`listen_messages`](./account.md#listen_messagescontentnone) and [`listen_message_mentions`](./account.md#listen_message_mentions) from `Account`.

| Attribute | Type | Description |
|----|----|-------------|
| `id` | `str` | The message id. Can be passed to [`delete_message`](./account.md#delete_messageid) or used as a `reply_to_message_id`. |
| `chat_id` | `str` | The chat the message was sent in. |
| `content` | `str` | The message's text. For an [image](./types.md#content), this is the caption (if any) followed by the image path(s). |
| `text` | `str` | The message's raw text/caption. |
| `content_type` | [`types.Content`](./types.md#content) | What kind of content the message carries. |
| `from_public_key` | `str` | Public key of the sender. |
| `timestamp` | `datetime.datetime` | When the message was sent. |
| `edited_timestamp` | `datetime.datetime` | When the message was last edited, or `None` if it has never been edited. An edit arrives as a **new event** under the same `id` with updated `content`, so comparing this against the previous value is how an edit is told apart from a fresh message. |
| `chat_type` | [`types.Chat`](./types.md#chat) | What kind of chat the message was sent in. |
| `source` | `str` | `"status"` for a regular message, or the platform name (e.g. `"Discord"`) for a [bridged message](./account.md#send_bridged_messagechat_id-message-namenone-usernamenone-user_idnone-message_idnone-reply_to_message_idnone-image_urlnone). |
| `raw` | `dict` | The untouched payload Status Backend sent, exactly as it arrived. Use it to reach fields this model does not surface - `mentions`, `albumId`, `clock`, `emojiHash` and so on. |
| `image_urls` | `list[str]` | Local paths of attached images. Empty unless `content_type` is [`IMAGE`](./types.md#content) or [`STICKER`](./types.md#content). Contains more than one entry for an [album](./account.md#send_imagechat_id-file_paths-messagenone-reply_to_message_idnone). |
| `reply_id` | `str` | The `id` of the message this one replies to. `None` if it is not a reply. |
| `bridge_id` | `str` | The message's id **on the other platform**, for a [bridged message](./account.md#send_bridged_messagechat_id-message-namenone-usernamenone-user_idnone-message_idnone-reply_to_message_idnone-image_urlnone). `None` otherwise. |
| `payment_requests` | `list[`[`PaymentRequest`](./models.md#paymentrequest)`]` | Payment requests attached to the message. Empty for most messages. |

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for message in account.listen_messages():
    print(message.from_public_key, message.content)
```

## `PaymentRequest`

A payment request attached to a [`Message`](./models.md#message).

| Attribute | Type | Description |
|----|----|-------------|
| `to_address` | `str` | The address the payment should be sent to. |
| `token_symbol` | `str` | The requested token's symbol. |
| `token_address` | `str` | The requested token's contract address. |
| `chain_id` | `int` | The chain the token lives on. |
| `amount` | `str` | The requested amount, in the token's smallest unit (wei). |

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for message in account.listen_messages():
    for payment in message.payment_requests:
        print(f"{payment.amount} {payment.token_symbol} -> {payment.to_address}")
```

## `ContactRequest`

Returned by [`listen_events`](./account.md#listen_events) and [`listen_contact_requests`](./account.md#listen_contact_requests) from `Account`.

| Attribute | Type | Description |
|----|----|-------------|
| `id` | `str` | The contact request id. Pass this as `request_id` to [`add_contact`](./account.md#add_contactpublic_key-request_idnone-display_namenone) to approve it. |
| `timestamp` | `datetime.datetime` | When the request was sent, taken from the message that carried it. |
| `public_key` | `str` | Public key of the other account. |
| `text` | `str` | The message that came with the request |
| `raw` | `dict` | The untouched payload Status Backend sent, exactly as it arrived. |
| `incoming` | `bool` | Another user sent a contact request to the account. Approve it with [`add_contact`](./account.md#add_contactpublic_key-request_idnone-display_namenone). |
| `accepted` | `bool` | Another user accepted a contact request that the account had sent. The contact is now mutual. |
| `removed` | `bool` | A user has removed the account from their contacts. |

The state is carried by **three booleans** rather than one string, and **exactly one of them is `True`** on any yielded request - the one matching the state the request just moved into. The rest stay `False`.

```python
from status_sdk import Account

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for request in account.listen_contact_requests():
    if request.incoming:
        print("New contact request received")
    elif request.accepted:
        print("Contact request was accepted")
    elif request.removed:
        print(f"{request.public_key} has removed you")
```

## `CommunityRequest`

Returned by [`listen_requests`](./community.md#listen_requests) from `Community`, and by [`listen_events`](./account.md#listen_events) from `Account`.

| Attribute | Type | Description |
|----|----|-------------|
| `id` | `str` | The join request id. Pass this to [`accept`](./community.md#acceptpending_request_id) or [`decline`](./community.md#declinepending_request_id). |
| `timestamp` | `datetime.datetime` | When the request was received. Unlike the other models, this is the **local** time the event was handled rather than a timestamp from the backend - the join request payload carries none. |
| `public_key` | `str` | Public key of the requesting member. |
| `community_id` | `str` | The id of the community the request was sent to. |
| `raw` | `dict` | The untouched payload Status Backend sent, exactly as it arrived. |
| `pending` | `bool` | The request is waiting to be [accepted](./community.md#acceptpending_request_id) or [declined](./community.md#declinepending_request_id). |
| `reject` | `bool` | The request was declined. |
| `accept` | `bool` | The request was accepted and the member joined. |
| `cancel` | `bool` | The request was cancelled. |


```python
from status_sdk import Account, Community

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

url = "https://status.app/c/G3QAAMQn9ueHRsR3W5Ouuy25fkCxziknAIEkCbYAoC04HjyGeQ6X8k45q3GVeyZiksbd38tQ4S_EfhrJKhRV3sDvjhmrCuSoDBIf2QJiEKwAOZipxis8ntNRVyPhC5IoWaEsj9X4P5zw093pcLofZzTV2gM=#zQ3shZeEJqTC1xhGUjxuS4rtHSrhJ8vUYp64v6qWkLpvdy9L9"
community = Community(account, url=url)

for request in community.listen_requests():
    print(f"{request.public_key}\tpending={request.pending}")
```

## `TokenPermission`

Describe a token a community member must hold for a [permission](./community.md#add_permissionpermission-tokensnone). This model is **constructed by the user** and passed *into* the SDK - see [Token criteria](./community.md#token-criteria).

| Attribute | Type | Required | Description |
|----|----|----|-------------|
| `symbol` | `str` | Yes | The token symbol, as it appears in [`get_tokens`](./account.md#get_tokens) on `Account`. |
| `amount` | `float` | Yes | The minimum amount a member must hold. Converted to wei using the token's own `decimals`, so it is written in human units - `10` means 10 tokens, not 10 wei. |
| `chain_id` | `int` | No | The chain the token lives on. Defaults to `1` (Ethereum mainnet). |
| `address` | `str` | No | The token's contract address. Needed only when the same `symbol` exists more than once on `chain_id`. |

```python
from status_sdk import models

token = models.TokenPermission(symbol="SNT", amount=10)
```
