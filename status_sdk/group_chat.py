from .account import Account
from . import exceptions
from typing import Union, Optional
import re, datetime

class GroupChat:

    __TOTAL_MEMBERS = 20 # https://status.app/help/messaging/create-a-group-chat
    def __init__(self, account: Account, chat_id: Optional[str] = None):
        """
        Work with your own Status App Group Chats.

        Parameters:
            - `account` - a logged in `Account`
            - `chat_id` - a group chat `id` from `.chats` in `Account`
        """
        # Verify that the user is logged in
        account.info
        self.__account = account
        self.__id = None

        if not chat_id:
            return

        chat = self.__get_group_info(chat_id)
        self.__id = chat["id"]
        is_admin = self.__extract_admin_public_key(chat["id"]) == self.__account.info["public_key"]
        self.__account.logger.info(f"Account is{'' if is_admin else ' NOT'} admin.")

    def create(self, public_keys: Union[list[str], str], name: str):
        """
        Create a Group Chat from the given public keys.

        Parameters:
            - `public_keys` - the public keys of the members to create the chat with. Public keys can be found in `contacts` in `Account`
            - `name` - the name of the Group Chat. Must follow the Status App naming rules

        Output:
            - the `GroupChat` itself, so calls can be chained
        """
        if self.__id:
            raise exceptions.GroupChatAlreadyExistsError("Chat has already been created! To create a new one, please initialize a new `GroupChat`...")

        self.__validate_name(name)
        public_keys = self.__get_public_keys(public_keys)
        if len(public_keys) > self.__TOTAL_MEMBERS:
            raise exceptions.GroupChatCreationError(f"Group chats can have up to {self.__TOTAL_MEMBERS} members. Please consider creating a Status Community...")

        response: dict = self.__account._call_rpc("messaging", "createGroupChatWithMembers", [name, public_keys])
        error = response.get("error")
        if error:
            raise exceptions.GroupChatCreationError(error["message"])

        chat: dict = response["result"]["chats"][0]
        self.__id = chat["id"]
        self.__account.logger.info(f"Created group chat {name} [{self.id}]")
        return self

    def send_message(self, message: str, reply_to_message_id: Optional[str] = None):
        """
        Send a message to the group chat.

        Parameters:
            - `message` - the message that will be sent. Currently only text messages are supported
            - `reply_to_message_id` - the `id` of the message to reply to, as it appears in `self.get_messages()`. If not provided, the message is sent as a standalone message.

        Output:
            - the `GroupChat` itself, so calls can be chained
        """
        self.__account.send_message(self.id, message, reply_to_message_id)
        return self

    def get_messages(self, start_timestamp: Optional[datetime.datetime] = None, end_timestamp: Optional[datetime.datetime] = None) -> list[dict]:
        """
        Get all of the messages in the given start and end timestamps.
        Messages are returned in descending order (newest to oldest).
        Messages can be fetched for removed contacts as well.

        Parameters:
            - `start_timestamp` - the start timestamp for message extraction. If not provided all early messages will be fetched.
            - `end_timestamp` - the end timestamp for message extraction. If not provided all latest messages will be fetched.

        Output:
            - All messages within the given range
        """
        return self.__account.get_messages(self.id, start_timestamp, end_timestamp)

    def remove(self, public_keys: Union[list[str], str]):
        """
        Remove members from the Group Chat. Only the administrator of the chat can remove members.

        Parameters:
            - `public_keys` - the public keys of the members to remove. Current members can be found in `self.members`

        Output:
            - the `GroupChat` itself, so calls can be chained
        """

        if len(self.members.keys()) == 0:
            self.__account.logger.error("There are no members to remove from the Group Chat...")
            return

        if not self.is_admin:
            raise exceptions.GroupChatMembersError("Only administrators can remove members from")

        public_keys = self.__get_public_keys(public_keys)
        current_members = self.members.keys()
        public_keys = [public_key for public_key in public_keys if public_key in current_members]
        if len(public_keys) == 0:
            raise exceptions.GroupChatMembersError("Please provide valid Public Keys from the chat only...")

        params = [self.id, public_keys]
        response: dict = self.__account._call_rpc("messaging", "removeMembersFromGroupChat", params)
        self.__action_log(public_keys, "remove")
        return self

    def add(self, public_keys: Union[list[str], str]):
        """
        Add members to the Group Chat.

        Parameters:
            - `public_keys` - the public keys of the members to add. Public keys can be found in `contacts` in `Account`

        Output:
            - the `GroupChat` itself, so calls can be chained
        """
        public_keys = self.__get_public_keys(public_keys)
        current_members = list(self.members.keys())
        public_keys = [
            public_key
            for public_key in public_keys
            if public_key not in current_members
        ]
        if len(public_keys) + len(current_members) > self.__TOTAL_MEMBERS:
            self.__account.logger.warning(f"Too many members in the Group Chat! Group chats can have up to {self.__TOTAL_MEMBERS} members. Please consider creating a Status Community...")
            return

        params = [self.id, public_keys]
        response: dict = self.__account._call_rpc("messaging", "addMembersToGroupChat", params)
        error = response.get("error", {})
        if error:
            raise exceptions.GroupChatMembersError(response["error"]["message"])

        self.__action_log(public_keys, "add")
        return self

    def leave(self):
        """
        Leave the Group Chat. The internal state is cleared afterwards,
        so the `GroupChat` must be re-initialized with a `chat_id`
        (or a new one must be created) before it can be used again.

        Output:
            - the `GroupChat` itself, so calls can be chained
        """
        self.__account._call_rpc("messaging", "leaveGroupChat", [self.id, True])
        self.__id = None
        self.__account.logger.info(f"Left group chat {self.name} [{self.id}]")
        return self

    def delete_message(self, id: str) -> bool:
        """
        Delete one of your own Group Chat messages.

        Parameters:
            - `id` - the `id` of the message from `group_chat.get_messages()`.

        Output:
            - if `True` then the message was deleted. If `False` then the message was not deleted due to permissions.
        """
        self.name
        return self.__account.delete_message(id)

    @property
    def members(self) -> dict[str, dict]:
        """
        The current members in the chat, mapped by their public key.
        """
        members = {}
        chat = self.__get_group_info(self.id)
        for member in chat["members"]:
            response: dict = self.__account._call_rpc("messaging", "getContactByID", [member["id"]])
            result = response["result"]
            members[member["id"]] = {
                "public_key": result["id"],
                "url": self.__account._call_rpc("urls", "shareUserURLWithData", [result["id"]]).get("result"),
                "display_name": result["displayName"],
                "compressed_key": result["compressedKey"],
                "admin": self.__extract_admin_public_key(self.id) == result["id"]
            }
        return members

    @property
    def is_admin(self) -> bool:
        """
        If `True` then the `Account` is the administrator of the group
        """
        chat = self.__get_group_info(self.id)
        return self.__extract_admin_public_key(chat["id"]) == self.__account.info["public_key"]

    @property
    def name(self) -> str:
        """
        Get the current chat's name
        """
        chat = self.__get_group_info(self.id)
        return chat["name"]

    @name.setter
    def name(self, name: str):
        self.__validate_name(name)
        self.__account._call_rpc("messaging", "changeGroupChatName", [self.id, name])
        self.__account.signal.get("envelope.sent")

    @property
    def id(self) -> str:
        """
        Get the chat's ID
        """
        if not self.__id:
            raise exceptions.GroupChatNotFoundError()

        return self.__id

    def __extract_admin_public_key(self, chat_id: str) -> str:
        """
        Extract the Admin's public key from a Group Chat.
        A Group Chat's ID has the administrator's public key appended to it.

        Parameters:
            - `chat_id` - a valid Group Chat ID

        Output:
            - the public key of the Group Chat's administrator
        """
        return chat_id[chat_id.index("0x"):]

    def __get_public_keys(self, public_keys: Union[list[str], str]) -> list[str]:
        """
        Convert user input public keys to a list. The `Account`'s own public key is filtered out,
        as the `Account` cannot add or remove itself from a Group Chat.

        Parameters:
            - `public_keys` - a single public key or a list of public keys

        Output:
            - the unique public keys as a list, without the `Account`'s own public key
        """
        if not isinstance(public_keys, (list, str)):
            pass

        if isinstance(public_keys, str):
            public_keys = [public_keys]

        public_keys = [
            public_key
            for public_key in public_keys
            if public_key != self.__account.info["public_key"]
        ]
        if len(public_keys) == 0:
            raise exceptions.PublicKeyError("No public keys were given to the method...")

        return list(set(public_keys))

    @property
    def available_slots(self) -> bool:
        return self.__TOTAL_MEMBERS - len(self.members)

    def __validate_name(self, name: str):
        """
        Validate the Group chat name based on Status App rules.

        Status App validation rules:
            - Only letters, numbers, underscores (_), periods (.), whitespaces and hyphens (-) allowed
            - Must be between 1 and 30 characters long

        Parameters:
            - `name` - the group chat name to validate

        Output:
            - `True` if the name is valid. Otherwise a custom exception is raised
        """

        if not isinstance(name, str):
            raise exceptions.InvalidGroupChatNameError("Group chat name must be a string.")

        if not 1 <= len(name) <= 30 or name == " ":
            raise exceptions.InvalidGroupChatNameError("Group chat name must be between 1 and 30 characters long.")

        if not re.fullmatch(r"[A-Za-z0-9_. \t-]+", name):
            raise exceptions.InvalidGroupChatNameError("Group chat name can contain only letters, numbers, underscores (_), periods (.), whitespaces and hyphens (-).")

        return True

    def __action_log(self, public_keys: list[str], action: str):
        """
        Log how many members were affected by an `add` / `remove` action.
        The `action` is converted to its past tense, so `add` is logged as
        `Added` and `remove` is logged as `Removed`.

        Parameters:
            - `public_keys` - the public keys that the action was performed on
            - `action` - the action that was performed. Either `add` or `remove`
        """
        past_tense = f"{action}{'d' if action.endswith('e') else 'ed'}".title()
        preposition = "from" if action == "remove" else "to"
        total = len(public_keys)
        self.__account.logger.info(f"{past_tense} {total} contact{'s' if total != 1 else ''} {preposition} '{self.name}'")

    def __get_group_info(self, chat_id: str) -> dict:
        """
        Fetch latest group information. Other chat members can also modify some group information.:
            - Added / remove member
            - Change group name

        Parameters:
            - `chat_id` - the current chat's ID

        Output:
            - Overall chat information
        """
        response: dict = self.__account._call_rpc("messaging", "confirmJoiningGroup", [chat_id])
        if response.get("error"):
            raise exceptions.GroupChatNotFoundError(f"Group Chat not found...\nChat ID: {chat_id}")

        chat: dict = response["result"]["chats"][0]
        return chat
