# Types

## `Content`

The content type of a message, matching the `contentType` Status Backend uses internally.

| Name | Value | Meaning |
|-----|-----|-------------|
| `TEXT` | `1` | A plain text message. |
| `STICKER` | `2` | A sticker. |
| `EMOJI` | `4` | An emoji-only message. |
| `IMAGE` | `7` | An image, or an album of images sent together - see [`send_image`](./account.md#send_imagechat_id-file_paths-messagenone-reply_to_message_idnone). |
| `BRIDGED` | `18` | A message relayed from another platform - see [`send_bridged_message`](./account.md#send_bridged_messagechat_id-message-namenone-usernamenone-user_idnone-message_idnone-reply_to_message_idnone-image_urlnone). |

```python
from status_sdk import Account, types

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

# Only yield text and emoji messages
for msg in account.listen_messages(content=[types.Content.TEXT, types.Content.EMOJI]):
    print(msg.content)
```

A single value can be passed instead of a list:

```python
# Only yield images (and albums)
for msg in account.listen_messages(content=types.Content.IMAGE):
    print(msg.image_urls)
```

## `Chat`

The type of chat a message was sent in.

| Name | Value | Meaning |
|-----|-----|-------------|
| `PRIVATE` | `1` | A one-to-one chat with a [mutual contact](./account.md#contacts). |
| `COMMUNITY` | `2` | A [`Channel`](./community.md) inside a community. |
| `GROUP` | `3` | A [`GroupChat`](./group-chat.md). |

```python
from status_sdk import Account, types

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for msg in account.listen_messages():
    if msg.chat_type == types.Chat.GROUP:
        print(f"Group message: {msg.content}")
```

## `Event`

The kind of event yielded by [`listen_events`](./account.md#listen_events), paired with its payload.

| Name | Value | Payload | Meaning |
|-----|-----|-----|-------------|
| `MESSAGE` | `1` | [`Message`](./models.md#message) | A new message in any chat the account can see. |
| `MENTION` | `2` | [`Message`](./models.md#message) | A message mentioning the account - `@<public key>`, or `@0x00001` for everybody in the chat. |
| `CONTACT_REQUEST` | `3` | [`ContactRequest`](./models.md#contactrequest) | A contact request was received, accepted or removed. |
| `COMMUNITY_REQUEST` | `4` | [`CommunityRequest`](./models.md#communityrequest) | Somebody asked to join a community the account administers. |

```python
from status_sdk import Account, types

account = Account()
params = {
    "name": "status-app-bot",
    "password": "SNTPUMP"
}
account.login(**params)

for event, payload in account.listen_events():
    if event is types.Event.MENTION:
        print(f"mentioned by {payload.from_public_key}")
```
