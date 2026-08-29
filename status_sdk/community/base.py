from ..account import Account
from .. import exceptions, models
from .channel import Channel
from typing import Union, Optional, Generator
import pandas as pd
import datetime, copy, os, shutil

class Community:

    __role_mapping = {
        0: "none",
        1: "owner",
        4: "admin",
        5: "token_master"
    }

    __request_states = {
        1: "pending",
        2: "reject",
        3: "accept",
        4: "cancel"
    }

    def __init__(self, account: Account, community_id: Optional[str] = None, url: Optional[str] = None, data_folder: Optional[str] = None):
        """
        Work with Status App Communities

        Parameters:
            - `account` - a logged in `Account`
            - `community_id` - the Community's ID. If unknown, please provide `url`.
            - `url` - the Community's URL. If unknown, please provide `community_id`
            - `data_folder` - the local folder mounted into the Status Backend Docker container, holding the accounts and their community data. It must be the **same** folder that was passed to `launch_docker_container`, otherwise the community data written by Status Backend cannot be reached.
        """
        # Verify that the user is logged in
        account.info
        self.__account = account
        self.__data_folder = data_folder
        if self.__data_folder and os.path.basename(self.__data_folder) != "data":
            self.__data_folder = os.path.join(self.__data_folder, "data")

        if community_id:
            self.__id = community_id
            return

        response = account._call_rpc("urls", "parseSharedURL", [url])
        error = response.get("error", {})
        if error:
            raise exceptions.CommunityNotFoundError(error["message"])

        self.__id = response["result"]["community"]["communityId"]
        result: dict = self.__get_community_info()
        # Account is a member -> actions can be used
        if result["joined"]:
            return

        if result["requestedToJoinAt"] != 0:
            # Account is pending -> no actions can be taken until approved
            self.__account.logger.warning(f"Request for community {self.__id} is pending.")
            self.__id = None
            return

        params = [account.info["public_key"], self.__id, [account.info["wallet_address"]]]
        sign_params = account._call_rpc("messaging", "generateJoiningCommunityRequestsForSigning", params)["result"]
        for p in sign_params:
            p["password"] = account.info["password"]

        signatures = account._call_rpc("messaging", "signData", [sign_params])["result"]
        params = [{
            "communityId": self.__id,
            "addressesToReveal": [self.__account.info["wallet_address"]],
            "airdropAddress": self.__account.info["wallet_address"],
            "signatures": signatures
        }]
        result = self.__account._call_rpc("messaging", "requestToJoinCommunity", params)
        self.__account.logger.info(f"Sent request to community {self.__id}")
        self.__id = None

    def leave(self):
        """
        Leave the community
        """
        self.__account._call_rpc("messaging", "leaveCommunity", [self.id])
        self.__id = None

    def kick(self, public_keys: Union[str, list[str]]):
        """
        Kick a member from the community.

        Parameters:
            - `public_keys` - a single value or a list of public keys / chat keys / account URLs to kick. The formats can be mixed within the same list. Current members can be found in `members`
        """
        self.__verify_admin()
        public_keys = self.__normalise_public_keys(public_keys)
        for public_key in public_keys:
            params = [self.id, self.__account.get_public_key(public_key)]
            self.__account._call_rpc("messaging", "removeUserFromCommunity", params)

    def ban(self, public_keys: Union[str, list[str]], delete_messages: bool = False):
        """
        Ban a member from the community. Banned members will appear in `banned_members`.

        Parameters:
            - `public_keys` - a single value or a list of public keys / chat keys / account URLs to ban. The formats can be mixed within the same list. Current members can be found in `members`
            - `delete_messages` - if `True`, all messages sent by the banned members are also deleted
        """
        self.__verify_admin()
        public_keys = self.__normalise_public_keys(public_keys)
        for public_key in public_keys:
            params = [{"communityId": self.id, "user": self.__account.get_public_key(public_key), "deleteAllMessages": delete_messages}]
            self.__account._call_rpc("messaging", "banUserFromCommunity", params)

    def unban(self, public_keys: Union[str, list[str]]):
        """
        Unban a member from the community. Banned members can be found in `banned_members`.

        Parameters:
            - `public_keys` - a single value or a list of public keys / chat keys / account URLs to unban. The formats can be mixed within the same list. Banned members can be found in `banned_members`
        """
        self.__verify_admin()
        public_keys = self.__normalise_public_keys(public_keys)
        for public_key in public_keys:
            params = [{"communityId": self.id, "user": public_key}]
            self.__account._call_rpc("messaging", "unbanUserFromCommunity", params)

    def accept(self, pending_request_id: str):
        """
        Accept a pending member into the community. Pending members can be found in `pending_members`

        Parameters:
            - `pending_request_id` - the `request_id` of a member from `pending_members`
        """
        self.__accept_or_decline(pending_request_id, "accept")

    def decline(self, pending_request_id: str):
        """
        Decline a pending member into the community. Pending members can be found in `pending_members`

        Parameters:
            - `pending_request_id` - the `request_id` of a member from `pending_members`
        """
        self.__accept_or_decline(pending_request_id, "decline")

    def __accept_or_decline(self, pending_request_id: str, mode: str):
        """
        Shared logic for `accept` and `decline`. Resolves the `mode` to its RPC
        call and validates that `pending_request_id` is an actual pending join
        request before acting on it.

        Parameters:
            - `pending_request_id` - the `request_id` of a member from `pending_members`
            - `mode` - either `accept` or `decline`, selecting which action to perform
        """
        self.__verify_admin()
        mode_mapping = {
            "accept": "acceptRequestToJoinCommunity",
            "decline": "declineRequestToJoinCommunity"
        }
        rpc_call = mode_mapping[mode]
        pending_request_ids = [member["request_id"] for member in self.pending_members + self.declined_members]
        if pending_request_id not in pending_request_ids:
            raise exceptions.CommunityPendingMemberError(f"Cannot {mode} '{pending_request_id}' - it is not a pending join request...")

        params = [{"id": pending_request_id}]
        self.__account._call_rpc("messaging", rpc_call, params)

    def get_collectibles(self) -> pd.DataFrame:
        """
        Get all token collectibles from the community and the amount they are holding.

        Output:
            - DataFrame - row per `owner` per contract.
        """
        result: dict = self.__get_community_info()
        info = [
            {
                "symbol": nft_info["symbol"],
                "name": nft_info["name"],
                "chain_id": int(chain_id),
                "contract_address": contract_address,
                "owner": collectible["ownerAddress"],
                "balance": int(balance["balance"])
            }
            for nft_info in result["communityTokensMetadata"]
            for chain_id, contract_address in nft_info["contract_addresses"].items()
            for collectible in (self.__account._call_rpc("wallets", "getCollectibleOwnersByContractAddress", [int(chain_id), contract_address]).get("result", {}) or {}).get("owners") or []
            for balance in collectible["tokenBalances"]
        ]
        info = pd.DataFrame(info)
        info = info.groupby(info.columns[:-1].to_list()).sum().reset_index()
        info["is_owner"] = info["owner"] == self.__account.info["wallet_address"]
        return info

    def upload_control_node(self, folder: str):
        """
        Upload a `data` (if using Status App) / `data` (if using `status-im/status-go`) folder.
        NOTE: This is a destructive action, so always make sure `folder` has valid account data. If
        the folder is

        Parameters:
            - `folder` - the Status App `data` folder if using Status App or `data` if using `status-im/status-go` Docker image
        """

        if self.role != "owner":
            raise exceptions.CommunityPermissionError("Only community owners can perform this action...")
        self.__account.logger.info(f"Account is owner of Community {self.name} [{self.id}]")

        if not isinstance(self.__data_folder, str):
            raise exceptions.CommunityDataFolderError()

        for name, path in (("folder", folder), ("data_folder", self.__data_folder)):
            if not os.path.isdir(path):
                raise exceptions.CommunityDataFolderError(f"The `{name}` '{path}' does not exist / is not a folder...")
            if not os.listdir(path):
                raise exceptions.CommunityDataFolderError(f"The `{name}` '{path}' is empty...")

        source = os.path.normcase(os.path.realpath(folder))
        destination = os.path.normcase(os.path.realpath(self.__data_folder))

        if os.path.basename(source) != os.path.basename(destination):
            raise exceptions.CommunityControlNodeError(f"'{folder}' and '{self.__data_folder}' must end in the same folder name - Status Backend only reads the account data from a folder named '{os.path.basename(destination)}'...")

        if source == destination or source.startswith(destination + os.sep) or destination.startswith(source + os.sep):
            raise exceptions.CommunityControlNodeError(f"'{folder}' and '{self.__data_folder}' must be two separate folders - the contents of the `data_folder` are deleted during the upload...")

        account_info: dict = copy.deepcopy(self.__account.info)
        login_params = {
            "password": account_info["password"],
            "key_uid": account_info["key_uid"]
        }
        self.__account.backup()
        self.__account.logger.info(f"Backup (.bkp) file for {account_info['key_uid']} created!")

        self.__account.logout()
        self.__account.logger.info("Account has been logged off successfully!")

        # Replace the account data generated in `status-go`
        for entry in os.listdir(destination):
            entry_path = os.path.join(destination, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)

            self.__account.logger.warning(f"Deleted {entry_path}")

        shutil.copytree(source, destination, dirs_exist_ok=True)
        self.__account.logger.info(f"Copied data from {source} to {destination}")
        # Error
        self.__account.login(**login_params)
        self.__account._load_backup()



    def create_channel(self, name: str, description: str, emoji: Optional[str] = None, colour: Optional[str] = None, category_name: Optional[str] = None) -> Channel:
        """
        Create a new community channel.

        Parameters:
            - `name` - the channel name
            - `description` - the channel description
            - `emoji` - the channel emoji
            - `colour` - the channel colour as a hex code, e.g. `#4360DF`. When omitted, a random default colour is chosen
            - `category_name` - the name of an existing category to place the channel under, from `categories`. When omitted, the channel is not categorised

        Output:
            - the created `Channel`
        """
        self.__verify_admin()
        category_id = self.categories.get(category_name, {}).get("id")
        return Channel(self.__account, self.id, name=name, description=description, emoji=emoji, colour=colour, category_id=category_id)

    def delete_channel(self, channel_name: str):
        """
        Delete a community channel by its name. Available channel names can be found in `channels`.

        Parameters:
            - `channel_name` - the name of the channel to delete
        """
        self.__verify_admin()
        channel = self.__getitem__(channel_name)
        params = [self.id, channel.id.replace(self.id, "")]
        self.__account._call_rpc("messaging", "deleteCommunityChat", params)

    def listen_requests(self) -> Generator[models.CommunityRequest, None, None]:
        """
        Listen for commnunity requests
        """
        key = "requestsToJoinCommunity"
        for message in self.__account.signal.listen("messages.new"):
            event: dict = message.get("event", {})

            if key not in event:
                continue

            for request in event[key]:
                if request.get("communityId") != self.id:
                    continue

                state = self.__request_states.get(request["state"])
                if not state:
                    continue

                yield models.CommunityRequest(request["id"], state, request["publicKey"])

    @property
    def categories(self) -> dict[str, str]:
        """
        The community's categories, keyed by category ID.
        Each category id has the `name` and `position` of the ID.
        """
        mapping = {
            info["name"]: {
                "id": community_id,
                "position": info["position"]
            }
            for community_id, info in self.__get_community_info().get("categories", {}).items()
        }
        return mapping

    @property
    def role(self) -> str:
        """
        The account's community role
        """
        result = self.__get_community_info()
        return self.__role_mapping[result["memberRole"]]

    @property
    def name(self) -> str:
        """
        The community's name
        """
        result = self.__get_community_info()
        return result["name"]

    @property
    def description(self) -> str:
        """
        The community's description
        """
        result = self.__get_community_info()
        return result["description"]

    @property
    def is_member(self) -> str:
        """
        If the account is a member of the community
        """
        result = self.__get_community_info()
        return result["isMember"]

    @property
    def is_encrypted(self) -> str:
        """
        If the account is a member of the community
        """
        result = self.__get_community_info()
        return result["encrypted"]

    @property
    def tags(self) -> str:
        """
        The community's tags
        """
        result = self.__get_community_info()
        return result["tags"]

    @property
    def has_joined(self) -> str:
        """
        The community's tags
        """
        result = self.__get_community_info()
        return result["joined"]

    @property
    def joined_timestamp(self) -> Optional[datetime.datetime]:
        """
        The datetime of when the community was joined
        """
        return self.__to_datetime("joinedAt")

    @property
    def requested_timestamp(self) -> Optional[datetime.datetime]:
        """
        The datetime of when the community request was sent
        """
        return self.__to_datetime("requestedToJoinAt")

    @property
    def introduction(self) -> str:
        """
        The community's introduction message when new users join
        """
        result = self.__get_community_info()
        return result["introMessage"]

    @property
    def leave_message(self) -> str:
        """
        The community's leave message when a member leaves.
        """
        result = self.__get_community_info()
        return result["outroMessage"]

    def get_members(self, dataframe: bool = False) -> Union[dict[str, dict], pd.DataFrame]:
        """
        Current community members.

        Parameters:
            - `dataframe` - if `True` then a `dict` of the existing members will be returned. Use this where speed matters.
                            If `False` then a `pd.DataFrame` of the existing members will be returned. Use this for data related pipelines.

        Output:
            - `dict` or `DataFrame` of the current community members
        """
        raw_data: dict[str, dict] = self.__get_community_info().get("members", {})
        if not dataframe:
            return raw_data

        members = []
        for public_key, member_info in raw_data.items():
            response: dict = self.__account._call_rpc("messaging", "getContactByID", [public_key])
            result: dict = response.get("result", {})
            if not result:
                result = {}

            url = self.__account._call_rpc("urls", "shareUserURLWithData", [public_key]).get("result")
            members.append({
                "public_key": public_key,
                "chat_id": public_key,
                "compressed_key": member_info["compressedKey"],
                "emojis": member_info["emojiHash"],
                "display_name": result.get("displayName"),
                "alias": member_info["alias"],
                "roles": [self.__role_mapping[role] for role in member_info.get("roles", [0])],
                "bio": result.get("bio", ""),
                "url": url
            })
        if not members:
            return pd.DataFrame()

        members = pd.DataFrame(members)
        members = members.assign(
            # Accounts with no display names are populated as they appear in the Status URL
            display_name = members["display_name"].fillna(
                members["compressed_key"].str[:3] + "..." + members["url"].str[-6:]
            )
        )
        return members.copy()

    @property
    def channels(self) -> list[dict]:
        """
        High level information for all community channels
        """
        result = self.__get_community_info()
        category_mapping = {
            category_id: info["name"]
            for category_id, info in result.get("categories", {}).items()
        }
        available_chats = [
            {
                "id": current["id"],
                "name": current["name"],
                "category_id": current["categoryID"] if len(current["categoryID"]) > 0 else None,
                "category_name": category_mapping.get(current["categoryID"])
            }
            for current in result["chats"].values()
        ]
        return available_chats

    @property
    def banned_members(self) -> list[str]:
        """
        Currently banned public keys
        """
        result = self.__get_community_info()
        banned_states = [0, 4] # Banned, BanWithAllmessagesDeleted
        public_keys = [
            public_key
            for public_key, member_state in result.get("pendingAndBannedMembers", {}).items()
            if member_state in banned_states
        ]
        return public_keys

    @property
    def pending_members(self) -> list[dict[str, str]]:
        """
        Members who have to be accepted or rejected
        """
        return self.__pending_declined_members("pending")

    @property
    def declined_members(self) -> list[dict[str, str]]:
        """
        Members who have to be accepted or rejected
        """
        return self.__pending_declined_members("declined")

    def __pending_declined_members(self, mode: str) -> list[dict[str, str]]:
        """
        Shared logic for `pending_members` and `declined_members`. Resolves the
        `mode` to its RPC call and returns the members for that request state.

        Parameters:
            - `mode` - either `pending` or `declined`, selecting which requests to fetch

        Output:
            - a list of `{"public_key": ..., "request_id": ...}` for each request,
              or an empty list if there are none
        """
        self.__verify_admin()
        mode_mapping = {
            "pending": "pendingRequestsToJoinForCommunity",
            "declined": "declinedRequestsToJoinForCommunity"
        }
        selected_rpc_call = mode_mapping[mode]
        members: Optional[list[dict]] = self.__account._call_rpc("messaging", selected_rpc_call, [self.id])["result"]
        if not members:
            return []

        public_keys = [{"public_key": member["publicKey"], "request_id": member["id"]} for member in members]
        return public_keys

    @property
    def id(self) -> str:
        """
        Get the Community's ID
        """
        if not self.__id:
            raise exceptions.CommunityNotFoundError()

        return self.__id

    @property
    def url(self) -> Optional[str]:
        """
        Get the URL of the community
        """
        return self.__account._call_rpc("urls", "shareCommunityURLWithChatKey", [self.id]).get("result")

    def __getitem__(self, channel_name: str) -> Channel:
        """
        Fetch a community chat by its name using subscript access, e.g. `community[channel_name]`.
        Available chat names can be found in the `chats` property.
        """
        result = self.__get_community_info()
        category_mapping = {
            category_id: info["name"]
            for category_id, info in result.get("categories", {}).items()
        }

        chat_info = None
        chat_mapping: dict[str, dict] = result["chats"]
        for chat in self.channels:
            if chat["name"] != channel_name:
                continue

            chat_info: Optional[dict] = chat_mapping.get(chat["id"])
            break

        if not chat_info:
            raise exceptions.CommunityChannelNotFoundError(f"No community channel with id or name '{channel_name}' was found...")

        chat_info["categoryName"] = category_mapping.get(chat_info["categoryID"])
        return Channel(self.__account, self.id, chat_info)

    def __len__(self) -> int:
        """
        Get the total number of members in the community
        """
        return len(self.get_members())

    def __get_community_info(self) -> dict:
        """
        Get up to date information for the community

        Output:
            - up to date community data
        """
        params = {
            "communityKey": self.id,
            "waitForResponse": True,
            "tryDatabase": True
        }
        response = self.__account._call_rpc("messaging", "fetchCommunity", [params])
        error: dict = response.get("error", {})
        if error:
            raise exceptions.InvalidCommunityKeyError(error["message"])

        if not response["result"]:
            raise exceptions.CommunityNotFoundError(f"Community '{self.id}' was not found...")

        return response["result"]

    def __normalise_public_keys(self, public_keys: Union[str, list[str]]) -> list[str]:
        """
        Verify if the given public keys exist in the community

        Parameters:
            - `public_keys` - a single or a list of public keys / chat keys / URLs

        Output:
            - the provided public keys that exist in the community
        """
        if isinstance(public_keys, str):
            public_keys = [public_keys]

        public_keys = pd.Series([
            self.__account.get_public_key(public_key)
            for public_key in public_keys
        ]).str.lower()
        members = self.get_members(True)
        query = members["public_key"].str.lower().isin(public_keys)
        if query.sum() > 0:
            return members.loc[query, "public_key"].to_list()

        banned = pd.Series(self.banned_members)
        query = banned.str.lower().isin(public_keys)
        if query.sum() > 0:
            return banned.loc[query].to_list()

        raise exceptions.CommunityMembersError("None of the provided Public Keys were found in the community...")

    def __to_datetime(self, key: str) -> Optional[datetime.datetime]:
        """
        Extract the `datetime.datetime` from the given key.

        Parameters:
            - `key` - a key from `__get_community_info()`

        Output:
            - the `datetime.datetime` of the `key`
        """
        result = self.__get_community_info()
        return datetime.datetime.fromtimestamp(result[key]) if result[key] != 0 else None

    def __verify_admin(self):

        if self.role not in list(self.__role_mapping.values())[1:]:
            raise exceptions.CommunityPermissionError()
