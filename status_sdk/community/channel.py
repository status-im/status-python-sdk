from ..account import Account
from .. import exceptions, models
from ..utils import community as utils
from typing import Union, Optional
import pandas as pd
import re, datetime, random

class Channel:

    __permission_mapping = {
        1: "admin",
        2: "member",
        3: "view",
        4: "view_post",
        5: "token_master",
        6: "token_owner"
    }
    __STATUS_COLOURS = [
        "#FF7D46", # Orange
        "#F6B03C", # Yellow
        "#1992D7", # Sky
        "#7140FD" # Purple
    ]

    # Common single-codepoint emoji ranges (heuristic, not the full Unicode emoji data)
    __EMOJI_RANGES = (
        (0x1F300, 0x1FAFF),  # symbols & pictographs (emoticons, transport, supplemental, extended-A)
        (0x2600, 0x27BF),    # misc symbols & dingbats
        (0x2B00, 0x2BFF),    # misc symbols & arrows
        (0x2300, 0x23FF),    # misc technical (e.g. ⌚, ⏳)
    )

    # Picked at random as the channel emoji when none is provided
    __DEFAULT_EMOJIS = (
        "😀", "🤖", "🚀", "🌟", "🔥", "💬", "📢", "🎨", "🧠", "⚡",
        "💡", "📌", "🎯", "🌈", "🎮", "📚", "🔔", "💎", "🌍", "🛰",
    )

    def __init__(self, account: Account, community_id: str, chat_info: Optional[dict] = None, name: Optional[str] = None, description: Optional[str] = None, emoji: Optional[str] = None, colour: Optional[str] = None, category_id: Optional[str] = None):
        """
        Work with Status App Community Channels (chats).
        This class is automatically handled in `class Community`

        Parameters:
            - `account` - a logged in `Account`
            - `community_id` - the Community's ID
            - `chat_info` - channel information from
        """
        account.info
        # Verify that the user is logged in
        self.__account = account
        self.__community_id = community_id

        if chat_info:
            self.__id: str = community_id + chat_info["id"]
            return

        self.__validate_name(name)
        self.__validate_description(description)

        if not colour:
            colour = random.choice(self.__STATUS_COLOURS)

        self.__validate_colour(colour)

        if not emoji:
            emoji = random.choice(self.__DEFAULT_EMOJIS)

        self.__validate_emoji(emoji)
        payload = {
            "identity": {
                "display_name": name,
                "color": colour,
                "description": description,
                "emoji": emoji
            },
            "viewersCanPostReactions": True,
            "hideIfPermissionsNotMet": True,
            "permissions": {"access": 1},
        }
        if category_id:
            payload["category_id"] = category_id

        response: dict = account._call_rpc("messaging", "createCommunityChat", [community_id, payload])
        result = response.get("result", {})
        if not result:
            error: dict = response.get("error", {})
            message: str = error.get("message", f"Could not create channel '{name}' in community '{community_id}'...")
            if "duplicate" in message:
                raise exceptions.CommunityDuplicateError(f"Channel '{name}' already exists in community '{community_id}'...")
            raise exceptions.CommunityChannelCreationError(message)

        chat: dict = result["chats"][0]
        self.__id = chat["id"]

    @property
    def id(self) -> str:
        """
        Chat ID is a combination of Community ID and channel ID
        """
        if not self.__id:
            raise exceptions.CommunityChannelNotFoundError()
        return self.__id

    @property
    def permissions(self) -> pd.DataFrame:
        data = utils.get_channel_permissions(self.__account, self.__community_id, self.id)
        if len(data) > 0:
            data["type"] = data["type"].map(self.__permission_mapping)
        return data

    @property
    def url(self) -> str:
        """
        The URL of the channel
        """
        info = self.__get_channel_info()
        return self.__account._call_rpc("urls", "shareCommunityChannelURLWithData", [self.__community_id, info["id"]]).get("result")

    @property
    def can_view(self) -> bool:
        """
        If the account is allowed to view messages
        """
        return self.__get_channel_info()["canView"]

    @property
    def can_react(self) -> bool:
        """
        If the account is allowed to post rections
        """
        return self.__get_channel_info()["canPostReactions"]

    @property
    def is_token_gated(self) -> bool:
        """
        If the channel is token gated
        """
        return self.__get_channel_info()["tokenGated"]

    @property
    def can_post(self) -> bool:
        """
        If the account is allowed to send messages
        """
        return self.__get_channel_info()["canPost"]

    @property
    def category(self) -> Optional[str]:
        """
        The category's name
        """
        return self.__get_channel_info()["categoryName"]

    @category.setter
    def category(self, value: str):
        community_info = utils.get_community_info(self.__account, self.__community_id)
        category_mapping = {
            info["name"]: category_id
            for category_id, info in community_info.get("categories", {}).items()
        }

        new_category = category_mapping.get(value)

        position_mapping = self.__get_category_positions()
        params = [{
            "communityId": self.__community_id,
            "categoryId": '' if not new_category else new_category,
            "chatId": self.id,
            "position": position_mapping.get(new_category, 0) + 1
        }]
        self.__account._call_rpc("messaging", "reorderCommunityChat", params)

    @property
    def position(self) -> Optional[str]:
        """
        The position of the chat in the current `category`
        """
        return self.__get_channel_info()["position"]

    @position.setter
    def position(self, value: int):
        if not isinstance(value, int):
            raise exceptions.InvalidCommunityChannelPositionError("Community channel position must be an integer.")

        category_id = self.__get_channel_info()["categoryID"]
        if len(category_id) == 0:
            category_id = None

        position_mapping = self.__get_category_positions()
        largest_position = position_mapping[category_id]
        new_largest_position = largest_position + 1
        if value < 0:
            value = 0

        if value > new_largest_position:
            value = new_largest_position

        params = [{
            "communityId": self.__community_id,
            "categoryId": '' if not category_id else category_id,
            "chatId": self.id,
            "position": value
        }]
        self.__account._call_rpc("messaging", "reorderCommunityChat", params)

    @property
    def description(self) -> str:
        """
        The Community Chat's description
        """
        return self.__get_channel_info()["description"]

    @description.setter
    def description(self, value: str):
        self.__validate_description(value)
        self.__edit_channel(description=value)

    @property
    def name(self) -> str:
        """
        Get the current name of the Community Chat
        """
        return self.__get_channel_info()["name"]

    @name.setter
    def name(self, value: str):
        self.__validate_name(value)
        self.__edit_channel(name=value)

    @property
    def colour(self) -> str:
        """
        Get the current colour of the Community Chat
        """
        return self.__get_channel_info()["color"]

    @colour.setter
    def colour(self, value: str):
        self.__validate_colour(value)
        self.__edit_channel(colour=value)

    @property
    def emoji(self) -> Optional[str]:
        """
        Get the current emoji of the Community Chat
        """
        selected_emojis: str = self.__get_channel_info()["emoji"]
        return selected_emojis.strip() if len(selected_emojis) > 0 else None

    @emoji.setter
    def emoji(self, value: str):
        """
        Skin-tone and Zero-Width Joiner sequences are not supported.
        """
        self.__validate_emoji(value)
        self.__edit_channel(emoji=value)

    def send_message(self, message: str, reply_to_message_id: Optional[str] = None) -> Optional[str]:
        """
        Send a message to the Community chat.

        Parameters:
            - `message` - the message that will be sent. Currently only text messages are supported
            - `reply_to_message_id` - the `id` of the message to reply to, as it appears in `self.get_messages()`. If not provided, the message is sent as a standalone message.

        Output:
            - The message ID
        """
        return self.__account.send_message(self.id, message, reply_to_message_id) if self.can_post else None

    def send_image(self, file_path: str, message: Optional[str] = None, reply_to_message_id: Optional[str] = None) -> str:
        """
        Send a image to the group chat.

        Parameters:
            - `file_path` - the file path of the image
            - `message` - the message that will be sent. Currently only text messages are supported
            - `reply_to_message_id` - the `id` of the message to reply to, as it appears in `self.get_messages()`. If not provided, the message is sent as a standalone message.

        Output:
            - The message ID
        """
        return self.__account.send_image(self.id, file_path, message, reply_to_message_id) if self.can_post else None

    def send_emoji_reaction(self, message_id: str, emoji_shortname: str):
        """
        Set / unset emoji reaction for a message in the channel.

        Parameters:
            - `message_id` - the `id` of the message, as it appears in `self.get_messages()`
            - `emoji_shortname` - the emoji shortname as in Status App, with or without the surrounding colons
        """
        if not self.can_react:
            return
        self.__account.send_emoji_reaction(message_id, emoji_shortname, self.id)

    def get_messages(self, start_timestamp: Optional[Union[str, datetime.datetime, datetime.date, pd.Timestamp]] = None, end_timestamp: Optional[Union[str, datetime.datetime, datetime.date, pd.Timestamp]] = None) -> list[dict]:
        """
        Get all of the messages in the given start and end timestamps.
        Messages are returned in descending order (newest to oldest).
        Messages can be fetched for removed contacts as well.

        Parameters:
            - `start_timestamp` - the start timestamp for message extraction. If not provided all early messages will be fetched. Can be a `datetime.datetime` or a string like `2026-08-11 22:57:51.134000` / `2026-08-11 22:57` / `2026-08-11`
            - `end_timestamp` - the end timestamp for message extraction. If not provided all latest messages will be fetched. Can be a `datetime.datetime` or a string like `2026-08-11 22:57:51.134000` / `2026-08-11 22:57` / `2026-08-11`

        Output:
            - All messages within the given range
        """
        return self.__account.get_messages(self.id, start_timestamp, end_timestamp) if self.can_view else []

    def delete_message(self, id: str) -> bool:
        """
        Delete one of your own Community messages. If you are an admin,
        you can delete other users' messages as well.

        Parameters:
            - `id` - the `id` of the message from `community["community-chat-id"].get_messages()`.

        Output:
            - if `True` then the message was deleted. If `False` then the message was not deleted due to permissions.
        """
        self.name
        return self.__account.delete_message(id)

    def add_permission(self, permission: str, tokens: Optional[Union[list[models.TokenPermission], models.TokenPermission]] = None):
        """
        Add a new permission for the channel

        Parameters:
            - `permission` - the scope of the permission

        """
        if not isinstance(permission, str):
            raise exceptions.InvalidCommunityChannelPermissionError("Community channel permission must be a string.")

        reversed_mapping = {name: number for number, name in self.__permission_mapping.items()}
        permission = permission.lower()
        if permission not in reversed_mapping:
            raise exceptions.InvalidCommunityChannelPermissionError(f"'{permission}' is not a valid community channel permission. It must be one of: {', '.join(reversed_mapping)}.")

        token_criteria = []
        if tokens:
            if isinstance(tokens, models.TokenPermission):
                tokens = [tokens]

            available_tokens = self.__account.get_tokens()
            for token_permission in tokens:
                query = (available_tokens["symbol"] == token_permission.symbol) & (available_tokens["chain_id"] == token_permission.chain_id)
                selected_tokens = available_tokens.loc[query, ["address", "decimals"]].drop_duplicates().reset_index(drop=True).copy()
                if len(selected_tokens) > 1 and not token_permission.address:
                    continue

                token_info = selected_tokens.to_dict("records")[0]
                token_criteria.append({
                    "type": 1, # ERC20
                    "contract_addresses": {str(token_permission.chain_id): token_info["address"]},
                    "symbol": token_permission.symbol,
                    "name": token_permission.symbol,
                    "amountInWei": str(token_permission.amount * (10 ** token_info["decimals"]))
                })

        params = {
            "communityId": self.__community_id,
            "type": reversed_mapping[permission],
            "tokenCriteria": token_criteria,
            "chat_ids": [self.id]
        }
        response = self.__account._call_rpc("messaging", "createCommunityTokenPermission", [params])
        if response.get("error"):
            raise exceptions.InvalidCommunityChannelPermissionError(response["error"]["message"])

    def delete_permission(self, id: str):
        """
        Delete a permission. Channel permissions can be found property `permissions`.

        Parameters:
            - `id` - the permission's ID as it is in property `permissions`
        """
        params = [
            {
                "communityId": self.__community_id,
                "permissionId": id,
            }
        ]
        response = self.__account._call_rpc("messaging", "deleteCommunityTokenPermission", params)
        if response.get("error"):
            raise exceptions.InvalidCommunityChannelPermissionError(response["error"]["message"])

    def __edit_channel(self, name: Optional[str] = None, emoji: Optional[str] = None, colour: Optional[str] = None, description: Optional[str] = None):
        """
        Modify chat related properties.

        NOTE: `editCommunityChat` overwrites the whole chat identity, so any field
        left out of `chat_setup` is cleared. That is why every current value is filled
        in first, and only the provided arguments override it.
        """
        info = self.__get_channel_info()
        channel_setup = {
            "identity": {
                "display_name": self.name,
                "emoji": self.emoji,
                "color": self.colour,
                "description": self.description
            },
            "category_id": info["categoryID"],
            "position": info["position"]
        }

        if name:
            channel_setup["identity"]["display_name"] = name

        if emoji:
            channel_setup["identity"]["emoji"] = emoji

        if colour:
            channel_setup["identity"]["color"] = colour

        if description:
            channel_setup["identity"]["description"] = description

        params = [self.__community_id, self.id, channel_setup]
        self.__account._call_rpc("messaging", "editCommunityChat", params)

    def __get_category_positions(self) -> dict:
        """
        Get the largest position for each category
        """
        largest = {}
        for chat in (utils.get_community_info(self.__account, self.__community_id).get("chats") or {}).values():
            category_id: str = chat["categoryID"]
            current_position = chat["position"]
            if len(category_id) == 0:
                category_id = None

            if category_id not in largest:
                largest[category_id] = current_position

            if current_position > largest[category_id]:
                largest[category_id] = current_position

        return largest

    def __get_channel_info(self) -> dict:
        """
        Get information for the current channel.
        """
        response = utils.get_community_info(self.__account, self.__community_id)
        chats: dict[str, dict] = response["chats"]
        selected_chat: dict = chats.get(self.id.replace(self.__community_id, ""), {})
        if not selected_chat:
            raise exceptions.CommunityChannelNotFoundError()

        category_mapping = {
            category_id: info["name"]
            for category_id, info in response.get("categories", {}).items()
        }
        selected_chat["categoryName"] = category_mapping.get(selected_chat["categoryID"])
        return selected_chat

    def __validate_name(self, name: str):
        """
        Validate and normalize a community channel name based on Status App rules.

        Status App validation rules:
            - Only letters, numbers, underscores (_), periods (.) and hyphens (-) allowed
            - Whitespaces are replaced with hyphens (-)
            - Cannot be more than 24 characters long

        Parameters:
            - `name` - the community channel name to validate
        """
        if not isinstance(name, str):
            raise exceptions.InvalidCommunityChannelNameError("Community channel name must be a string.")

        # Status App replaces whitespaces with hyphens in channel names
        name = name.replace(" ", "-")

        if not 1 <= len(name) <= 24:
            raise exceptions.InvalidCommunityChannelNameError("Community channel name must be between 1 and 24 characters long.")

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise exceptions.InvalidCommunityChannelNameError("Community channel name can contain only letters, numbers, underscores (_), periods (.) and hyphens (-).")

    def __validate_description(self, description: str) -> bool:
        """
        Validate a community channel description based on Status App rules.

        Status App validation rules:
            - Only letters, numbers, underscores (_), periods (.), whitespaces and hyphens (-) allowed
            - Must be between 1 and 140 characters long

        Parameters:
            - `description` - the community channel description to validate
        """
        if not isinstance(description, str):
            raise exceptions.InvalidCommunityChannelDescriptionError("Community channel description must be a string.")

        if not 1 <= len(description) <= 140:
            raise exceptions.InvalidCommunityChannelDescriptionError("Community channel description must be between 1 and 140 characters long.")

        if not re.fullmatch(r"[A-Za-z0-9_. -]+", description):
            raise exceptions.InvalidCommunityChannelDescriptionError("Community channel description can contain only letters, numbers, underscores (_), periods (.), whitespaces and hyphens (-).")

    def __validate_colour(self, colour: str):
        """
        Validate a community channel colour based on Status App rules.

        Status App validation rules:
            - Must be a hex colour code, e.g. `#4360DF`
            - Starts with a `#` followed by 3 (`#RGB`) or 6 (`#RRGGBB`) hex digits
            - Hex digits are case-insensitive (`0-9`, `a-f`, `A-F`)

        Parameters:
            - `colour` - the community channel colour to validate
        """
        if not isinstance(colour, str):
            raise exceptions.InvalidCommunityChannelColourError("Community channel colour must be a string.")

        if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", colour):
            raise exceptions.InvalidCommunityChannelColourError("Community channel colour must be a hex colour code, e.g. #4360DF.")

    def __validate_emoji(self, emoji: str):
        """
        Validate that `emoji` is a single "normal" emoji.

        NOTE: This is a stdlib-only heuristic based on common emoji Unicode
        ranges. It covers standard single-codepoint emoji, optionally with a
        trailing variation selector (e.g. ❤️), but does not handle
        multi-codepoint sequences such as skin tones, flags or ZWJ emoji
        (e.g. 👨‍👩‍👧). For exact validation use the `emoji` package.

        Parameters:
            - `emoji` - the community channel emoji to validate
        """
        if not isinstance(emoji, str):
            raise exceptions.InvalidCommunityChannelEmojiError("Community channel emoji must be a string.")

        # Drop the variation selector (U+FE0F) so ❤️ is treated the same as ❤
        normalized = "".join(char for char in emoji if ord(char) != 0xFE0F)
        if len(normalized) != 1:
            raise exceptions.InvalidCommunityChannelEmojiError("Community channel emoji must be a single emoji.")

        codepoint = ord(normalized)
        if not any(start <= codepoint <= end for start, end in self.__EMOJI_RANGES):
            raise exceptions.InvalidCommunityChannelEmojiError(f"'{emoji}' is not a valid emoji.")
