from typing import Optional, Union, Generator, Any
import uuid as uuid_lib
import requests, datetime, re, logging, os, json, ast, shutil, eth_abi, shutil
import pandas as pd
from . import exceptions
from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile
from . import constants
from .signal import Signal
from .logger import Logger

class Account:

    # Enum mappings from original wakuext.py
    __mappings = {
        "contact_request": {
            0: "none",     # No action taken / no association - initial state
            1: "mutual",   # Friends
            2: "sent",     # Request sent from the bot
            3: "received", # Request sent from another account
            4: "dismissed" # Request cancelled
        }
    }
    __prefix_mapping = {
        "messaging": "wakuext",
        "urls": "sharedurls",
        "wallets": "wallet",
        "account": "accounts",
        "identity": "multiaccounts"
    }
    __keccak256_selectors = {
        "transfer": "a9059cbb" # keccak256("transfer(address,uint256)")[:4]
    }
    __ETH_ADDRESS = "0x0000000000000000000000000000000000000000"

    def __init__(self, domain: str = "localhost", port: int = 8080, is_secure: bool = False, backup_folder: Optional[str] = None):
        """
        Work with your own Status App account

        Parameters:
            - `domain` - the domain name where Status Backend is running. If running locally it would be `localhost` and if it's running in a container it would be the image's name.
            - `port` - the port to connect to Status Backend. Verify the port in the Docker files.
            - `is_secure` - if `http` or `https` should be used
            - `backup_folder` - where backup files will be created and stored
        """
        # Wallet transactions
        self.__alchemy_token = None
        self.__transactions: Optional[pd.DataFrame] = None
        # Path of the account data in the Docker container for Status Backend
        self.__docker_data_folder = "./data-dir"
        # Path of the backups in the Docker container for Status Backend
        self.__docker_backup_folder = "./root/.config/Status/backups"
        self.__backup_folder = backup_folder
        # As the docker-compose.yaml folder is at the moment
        # NOTE: This might change for initial release
        self.__backup_sdk_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backups")
        os.makedirs(self.__backup_sdk_folder, exist_ok=True)

        # Path of where images will be uploaded to Status Backend
        self.__docker_asset_folder = "./assets"
        # As the docker-compose.yaml folder is at the moment
        # NOTE: This might change for initial release
        self.__assets_local_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        os.makedirs(self.__assets_local_folder, exist_ok=True)

        self.__logger = Logger()
        self.__timestamp_divisor = 1_000
        self.__kd_iterations = 256000
        self.__is_messenger_launched = False
        # Information for the logged in account
        self.__info = {}
        # Information for Production chains (chain id -> chain name)
        self.__chains = {}
        # Monitor if wallet is used in `login` and raise an exception if
        # a RPC endpoint for `wallet` is called without `alchemy_token`
        self.__is_wallet_set = False
        # All available tokens in Status Backend
        self.__available_tokens = pd.DataFrame()
        # All available ISO 4217 currencies
        self.__iso4217_ccy = []
        # All tokens in Status Backend
        self.__http_base_url = f"http{'s' if is_secure else ''}://{domain}:{port}/statusgo/"
        self.__ws_base_url = f"ws://{domain}:{port}/"
        self.__urls = {
            "http": {
                "initialize": f"{self.__http_base_url}InitializeApplication",
                "login": f"{self.__http_base_url}LoginAccount",
                "create": f"{self.__http_base_url}CreateAccountAndLogin",
                "restore": f"{self.__http_base_url}RestoreAccountAndLogin",
                "logout": f"{self.__http_base_url}Logout",
                "create_backup": f"{self.__http_base_url}PerformLocalBackup",
                "load_backup": f"{self.__http_base_url}LoadLocalBackup",
                "rpc": f"{self.__http_base_url}CallRPC",
                "transaction": f"{self.__http_base_url}SendTransactionV2"
            },
            "socket": {
                "signals": f"{self.__ws_base_url}signals"
            }
        }
        self.__signal = Signal(self.__urls["socket"]["signals"])
        # Initialize profile
        self.available_accounts
        # In case if there is a hanging logged in session
        self.logout()

    def login(self, password: str, key_uid: Optional[str] = None, name: Optional[str] = None, mnemonic: Optional[str] = None, infura_token: Optional[str] = None, alchemy_token: Optional[str] = None, coingecko_api_key: Optional[str] = None):
        """
        Login to the given account. If it does not exist,
        it will be created and automatically logged in.

        Parameters:
            - `password` - your Status password
            - `key_uid` - your key unique identifier. If not provided `display_name` will be used to fetch it. This means that each `display_name` can be linked to one `key_uid`
            - `name` - your Status display name or ENS. Use `name` and `password` parameter combination if you have a 1 to 1 mapping (ENS has a unique `key_uid`)
            - `mnemonic` - the mnemonic when creating an account. Use this field with `password` and `display_name` to recover an account
            - `infura_token` - https://www.infura.io/ RPC token to allow Status Backend to use a wallet
            - `alchemy_token` - https://alchemy.com/ RPC token to allow Status Backend to use a wallet
            - `coingecko_api_key` - https://www.coingecko.com/ API key to allow Status Backend to use a wallet
        """
        if not key_uid and not name:
            raise exceptions.InvalidContactError()

        available_accounts = self.available_accounts
        # Login combination: display_name (or ENS) + password
        if not key_uid:
            for account in available_accounts:
                if account["name"] != name:
                    continue

                key_uid = account["key_uid"]
                break
        # Login combination: key_uid + password
        else:
            available_key_uids = [current["key_uid"] for current in available_accounts]
            if key_uid not in available_key_uids:
                info = "\n".join([f"{current['key_uid']} - {current['name']}" for current in self.available_accounts])
                raise exceptions.InvalidContactError(f"Given Key Unique Identifier is invalid...\nAvailable Key Unique Identifiers:\n{info}")

        is_new_account = isinstance(key_uid, type(None))
        is_recovery = not isinstance(mnemonic, type(None)) and not key_uid

        url_key = "login"
        params = {
            "keyUid": key_uid,
            "password": password,
            'kdfIterations': self.__kd_iterations
        }

        if is_new_account or is_recovery:
            self.__validate_display_name(name)
            params = {
                "rootDataDir": self.__docker_data_folder,
                "kdfIterations": self.__kd_iterations,
                "displayName": name,
                "password": password,
                "customizationColor": "primary",
                "wakuV2LightClient": False,
                "thirdpartyServicesEnabled": True,
            }
        else:
            self.logger.info(f"Logging in with Key UID - {key_uid}")

        if is_new_account:
            self.logger.info(f"Creating account with display_name {name}")
            url_key = "create"

        if is_recovery:
            url_key = "restore"
            params["mnemonic"] = mnemonic
            self.logger.info(f"Restoring account for given mnemonics")

        self.logout()

        # Wallet usage is broken down into 3 components:
        # - transactions
        # - prices
        # - Ethereum RPC

        # Necessary for user transactions
        if alchemy_token:
            self.__alchemy_token = alchemy_token

        # Necessary for prices
        if coingecko_api_key:
            params["coingeckoDemoAPIKey"] = coingecko_api_key

        # Necessary for Ethereum RPC
        if infura_token:
            params["infuraToken"] = infura_token

        if alchemy_token and coingecko_api_key and infura_token:
            self.__is_wallet_set = True

        url = self.__urls["http"][url_key]
        params.update({
            "logEnabled": True,
            "logToStderr": True,
            "logLevel": "INFO",
        })
        response = requests.post(url, json=params)
        signal_event = self.__signal.get("node.login")
        if signal_event["is_error"]:
            raise exceptions.BackendError(f"There was an error with Status Backend...\n{signal_event['error_message']}")

        self.logger.info("Successfully logged in!")
        event: dict = signal_event["event"]["settings"]
        ens_info: list[dict] = signal_event["event"].get("ensUsernames", [])
        self.__info = {
            "public_key": event["public-key"],
            "url": None,
            "emojis": event["emojiHash"],
            "key_uid": event["key-uid"],
            "compressed_key": event["compressedKey"],
            "mnemonic": event.get("mnemonic", mnemonic),
            "display_name": event["display-name"],
            "bio": event.get("bio", ""),
            "password": password,
            "wallet_address": event["dapps-address"],
            "ens": {
                "preferred_name": event.get("preferred-name"),
                "usernames": ens_info
            },
            "logged_in_timestamp": datetime.datetime.now()
        }
        self.__info["url"] = self.__call_rpc("urls", "shareUserURLWithData", [event["public-key"]]).get("result")
        # Messenger can be activated only when logged in
        self.__start_messenger()
        if is_recovery:
            self.logger.info("Updating remote display name")
            self.display_name = event["display-name"]
            self.logger.info("Successfully updated display name!")
            self.__load_backup()

        return self

    def logout(self):
        """
        Logout of Status app. In a way this method behaves as a Status cleaner
        """
        response = requests.post(self.__urls["http"]["logout"])
        self.__info = {}
        self.__is_messenger_launched = False
        self.__is_wallet_set = False
        return self

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    @property
    def available_accounts(self) -> list[dict]:
        """
        All locally available accounts
        """
        response = requests.post(self.__urls["http"]["initialize"], json={
            "dataDir": self.__docker_data_folder
        })
        data: dict = response.json()
        accounts: list[dict] = data.get("accounts", [])
        if not isinstance(accounts, list):
            accounts = []

        current_available_accounts = [
            {
                "name": account["name"],
                "is_ens": account["name"].endswith(".eth"),
                "key_uid": account["key-uid"],
                "created_at": datetime.datetime.fromtimestamp(account["timestamp"])
            }
            for account in accounts
        ]
        return current_available_accounts

    @property
    def info(self) -> dict:
        """
        Overall information for currently logged in account.
        Can also be used to verify if the user has logged in.
        """
        if not self.__info:
            raise exceptions.NotLoggedInError()
        return self.__info

    @property
    def display_name(self) -> str:
        """
        Get the current display name
        """
        return self.info["display_name"]

    @display_name.setter
    def display_name(self, name: str):
        self.__validate_display_name(name)
        output = self.__call_rpc("messaging", "setDisplayName", [name])
        # It seems that if a valid name is given, it will be instantly updated
        # However after tracing the signals, an `envelope.sent` is sent a bit
        # after the name has been changed.
        self.signal.get("envelope.sent")
        self.__info["display_name"] = name

    @property
    def bio(self) -> str:
        """
        Get the current bio
        """
        return self.info["bio"]

    @bio.setter
    def bio(self, bio: Any):
        if isinstance(bio, type(None)):
            bio = ""

        bio = str(bio).strip()
        # Limit based from Status App
        CHARACTERS = 240
        if len(bio) > CHARACTERS:
            raise exceptions.InvalidDisplayNameError(f"Bio cannot be longer than {CHARACTERS} characters...")

        self.__call_rpc("messaging", "setBio", [bio])
        # It seems that if a valid bio is given, it will be instantly updated
        # However after tracing the signals, an `envelope.sent` is sent a bit
        # after the bio has been updated.
        self.signal.get("envelope.sent")
        self.__info["bio"] = bio

    @bio.deleter
    def bio(self):
        self.bio = ""

    @property
    def profile_picture(self) -> Optional[JpegImageFile]:
        """
        Get current profile picture
        """
        files = [
            os.path.join(self.__assets_local_folder, f)
            for f in os.listdir(self.__assets_local_folder)
            if os.path.isfile(os.path.join(self.__assets_local_folder, f))
        ]
        if not files:
            return

        latest_file_path = max(files, key=os.path.getctime)
        for file in files:
          if file == latest_file_path:
            continue
          os.remove(file)

        return Image.open(latest_file_path)

    @profile_picture.setter
    def profile_picture(self, file_path: str):

        if not isinstance(file_path, str):
            return

        if not os.path.exists(file_path):
            raise exceptions.ProfilePictureError(f"File path {file_path} does not exist")

        suffix = (".jpg", ".png", ".jpeg")
        if not file_path.endswith(suffix):
            raise exceptions.ProfilePictureError(f"Image must be one of the following extensions: {suffix}")

        file_name = os.path.basename(file_path)

        extension = file_name.split(".")[-1]
        asset_file_name = f"profile.{extension}"
        asset_file_path = os.path.join(self.__assets_local_folder, asset_file_name)
        docker_file_path = self.__docker_asset_folder + "/" + asset_file_name
        for file_name in os.listdir(self.__assets_local_folder):
            current_file_path = os.path.join(self.__assets_local_folder, file_name)
            if not os.path.isfile(current_file_path) or current_file_path.lower() == file_path.lower():
                continue
            os.remove(current_file_path)

        try:
            shutil.copy(file_path, asset_file_path)
        except shutil.SameFileError:
            self.logger.info("File is already in asset path")

        img = Image.open(asset_file_path)
        params = [
            self.info["key_uid"],
            docker_file_path,
            0,
            0,
            *img.size
        ]
        self.logger.info(f"Setting {file_path} as profile picture")
        self.__call_rpc("identity", "storeIdentityImage", params)
        self.logger.info(f"Profile picture has been updated!")

    @property
    def contacts(self) -> dict[str, dict]:
        """
        Get the contacts that the bot has.
        This includes contacts that have interacted with us. If a contact has removed us (or the bot has removed us)

        NOTE: We do not use internal state so we can get dynamic values such as:
        - Is currently active
        - Is currently blocked
        - Current display name
        - Current bio

        Terminology for Status contact requests:
            - approved - when both `contact_state` and `external_contact_state` are `mutual`
            - sent request - when `contact_state` is `sent` and `external_contact_state` is `none`
            - received request - when `contact_state` is `received`
        """
        data = self.__call_rpc("messaging", "contacts")
        raw: list[dict] = data.get("result", [])
        if not raw:
            return {}

        # dict format can be used in restricting functionality
        # such as - `send_message` and `remove_contact`
        contacts = {
            contact["id"]: {
                "public_key": contact["id"],
                "url": self.__call_rpc("urls", "shareUserURLWithData", [contact["id"]]).get("result"),
                "chat_id": contact["id"],
                "compressed_key": contact["compressedKey"],
                "emojis": contact["emojiHash"],
                "contact_state": self.__mappings["contact_request"][contact["contactRequestState"]],
                "external_contact_state": self.__mappings["contact_request"][contact["contactRequestRemoteState"]],
                "has_added_us": contact["hasAddedUs"],
                "added": contact["added"],
                "mutual": contact["mutual"],
                "display_name": contact["displayName"],
                "bio": contact["bio"],
                "last_updated": datetime.datetime.fromtimestamp(contact["lastUpdated"] / self.__timestamp_divisor) if contact["lastUpdated"] > 0 else None
            }
            for contact in raw
        }
        return contacts

    @property
    def signal(self) -> Signal:
        """
        Work with different Status event signals.
        To get a full list of all available signals,
        feel free to use `signal.available_signals`.
        """
        self.info
        return self.__signal

    @property
    def communities(self) -> list[dict]:
        """
        Get the communities that the bot is in.

        NOTE: We do not use internal state so we can get dynamic values such as:
        - Current community description
        - Current number of community members
        - Current channels' names, descriptions and permissions
        """
        data = self.__call_rpc("messaging", "communities")
        raw: list[dict] = data.get("result", [])
        if not raw:
            return []

        to_datetime = lambda key, mapping: (datetime.datetime.fromtimestamp(mapping[key]) if mapping[key] > 0 else None) if key in mapping else None
        communities = [
            {
                "id": community["id"],
                "url": self.__call_rpc("urls", "shareCommunityURLWithData", [community["id"]]).get("result"),
                "name": community["name"],
                "verified": community["verified"],
                "description": community["description"],
                "dialog": community["introMessage"],
                "leaving_message": community["outroMessage"],
                "tags": community["tags"],
                "is_member": community["isMember"],
                "joined": community["verified"],
                "joined_timestamp": to_datetime("joinedAt", community),
                "requested_timestamp": to_datetime("requestedToJoinAt", community),
                "encrypted": community["encrypted"],
                "members": len(community["members"]),
                "channels": [
                    {
                        "id": chat["id"],
                        "chat_id": community["id"] + chat["id"],
                        "url": self.__call_rpc("urls", "shareCommunityChannelURLWithData", [community["id"], chat["id"]]).get("result"),
                        "name": chat["name"],
                        "description": chat["description"],
                        "permissions": {
                            "posting": chat["canPost"],
                            "viewing": chat["canView"],
                            "reactions": chat["canPostReactions"],
                            "token_gated": chat["tokenGated"]
                        }
                    }
                    for chat in community["chats"].values()
                ]
            }
            for community in raw
        ]
        return communities

    @property
    def chats(self) -> list[dict]:
        """
        All chats that the bot can send messages to.
        This property combines `self.communities` and `self.contacts` chats.
        """
        communities = [
            {"type": "channel", "id": chat["chat_id"], "name": f"{community['name']} #{chat['name']}"}
            for community in self.communities
            for chat in community["channels"]
            if chat["permissions"]["posting"] and community["is_member"]
        ]
        contacts = [
            {"type": "contact", "id": contact["chat_id"], "name": contact["display_name"]}
            for contact in self.contacts.values()
        ]

        # Group chats in RPC endpoint are chat type 3
        data = self.__call_rpc("messaging", "activeChats")
        result: Optional[list[dict]] = data.get("result", [])
        if not result:
            result = []

        group_chats = [
            {"type": "group_chat", "id": active_chat["id"], "name": active_chat["name"]}
            for active_chat in result
            if active_chat["chatType"] == 3
        ]
        return contacts + communities + group_chats

    @property
    def chains(self) -> dict[int, str]:
        """
        All available production chains that are
        used in Status Backend.
        """

        # NOTE: An internal state can be used because chains
        # would be consistent for the currently pulled Status Bacckend image
        if self.__chains:
            return self.__chains

        result = self.__call_rpc("wallets", "getEthereumChains").get("result", [])
        key = "Prod"
        self.__chains = {chain[key]["chainId"]: chain[key]["chainName"] for chain in result if chain.get(key)}
        return self.__chains

    @property
    def balance(self) -> pd.DataFrame:
        """
        Get the account's balance
        """
        empty = pd.DataFrame(columns=["timestamp", "address", "chain_id", "amount", "symbol"])

        params = [[self.info["wallet_address"]], True]
        results = self.__call_rpc("wallets", "fetchOrGetCachedWalletBalances", params).get("result", {}).get(self.info["wallet_address"].lower(), [])
        if not results:
            return empty.copy()

        balance = pd.DataFrame(results)
        column_mapping = {"tokenAddress": "address", "tokenChainId": "chain_id", "balance": "amount", "hasError": "error"}
        balance = balance.rename(columns=column_mapping)[list(column_mapping.values())]\
                        .astype({"chain_id": "int8", "amount": "float64"})

        query = (balance["amount"] != 0) & (~balance["error"])
        if query.sum() == 0:
            return empty.copy()

        redundant_columns = ["error", "decimals", "cross_chain_id", "source_id"]
        available_tokens = self.get_tokens()
        balance = balance.loc[query].merge(available_tokens, "left", ["address", "chain_id"])\
                                    .drop(redundant_columns, axis=1)\
                                    .drop_duplicates()\
                                    .sort_values("chain_id", ascending=True)\
                                    .reset_index(drop=True)\

        balance.insert(0, "timestamp", datetime.datetime.now())
        return balance.copy()

    @property
    def community_members(self) -> pd.DataFrame:
        """
        Get enriched member data for all visible communities that the account belongs to.

        NOTE: This performs an additional RPC call for each member to fetch profile
        details, so it can be slower for large communities.

        This can be useful for analyzing community membership, such as identifying
        suspicious profiles or filtering for genuine community members.
        """
        data = self.__call_rpc("messaging", "communities")
        raw: list[dict] = data.get("result", [])

        if not raw:
            return pd.DataFrame()

        members = []
        for community in raw:
            for public_key, info in community.get("members", {}).items():
                response: dict = self.__call_rpc("messaging", "getContactByID", [public_key])
                result: dict = response.get("result") or {}

                url = self.__call_rpc("urls", "shareUserURLWithData", [public_key]).get("result")

                members.append({
                    "community_id": community["id"],
                    "community_name": community["name"],
                    "public_key": public_key,
                    "chat_id": public_key,
                    "display_name": result.get("displayName"),
                    "url": url,
                    "bio": result.get("bio", ""),
                    **info,
                })

        if not members:
            return pd.DataFrame()

        members = pd.DataFrame(members)
        members.columns = [self.__camel_to_snake(column) for column in members.columns]

        members = members.assign(
            # Accounts with no display names are populated as they appear in the Status URL
            display_name = members["display_name"].fillna(
                members["compressed_key"].str[:3] + "..." + members["url"].str[-6:]
            )
        ).drop(["last_update_clock", "color_id"], axis=1)\
        .rename(
            # Initial display name of the account when it was created
            columns={"alias": "status_alias"}
        )

        return members.copy()

    def __getitem__(self, key: str) -> pd.DataFrame:
        """
        Get the fiat currency balance
        """
        ccy = key.upper()

        if ccy not in self.__get_fiat_ccy():
            raise exceptions.InvalidCurrencyError(f"{ccy} is an invalid fiat (ISO 4217) currency code...")

        balance = self.balance
        tokens = (balance["chain_id"].astype(str) + "-" + balance["address"]).to_list()
        result = self.__call_rpc("wallets", "fetchPrices", [tokens, [ccy]]).get("result", {})
        if result:
            rates = pd.DataFrame([
                {
                    "chain_id": int(address.split("-")[0]),
                    "address": address.split("-")[1],
                    "rate": price,
                    "ccy": ccy,
                }
                for address, prices in result.items()
                for ccy, price in prices.items()
            ])
            balance = balance.merge(rates, "left", ["chain_id", "address"])
            balance["fiat_value"] = balance["amount"] * balance["rate"]
        else:
            balance = balance.assign(
                rate = None,
                ccy = ccy,
                fiat_value = None,
            )

        return balance.copy()

    def send_message(self, chat_id: str, message: str):
        """
        Send a message to the given chat.

        Parameters:
            - `chat_id` - the chat ID can be found in `self.chats`
            - `message` - the message that will be sent. Currently only text messages are supported
        """
        params = [{
            "chatId": chat_id,
            "text": message,
            "contentType": 1, # Send message only. Future versions can have different message types (audio, image, etc.)
            "responseTo": ""
        }]
        self.__call_rpc("messaging", "sendChatMessage", params)

    def listen_messages(self) -> Generator:
        """
        Listen for new **RAW** messages continuously. Can be used for real time processing.
        """
        for message in self.signal.listen("messages.new"):
            event: dict = message.get("event", {})
            if "chats" in event or "messages" in event:
                yield message

    def get_messages(self, chat_id: str, start_timestamp: Optional[datetime.datetime] = None, end_timestamp: Optional[datetime.datetime] = None) -> list[dict]:
        """
        Get all of the messages in the given start and end timestamps.
        Messages are returned in descending order (newest to oldest).
        Messages can be fetched for removed contacts as well.

        Parameters:
            - `chat_id` - the chat ID can be found in `self.chats`
            - `start_timestamp` - the start timestamp for message extraction. If not provided all early messages will be fetched.
            - `end_timestamp` - the end timestamp for message extraction. If not provided all latest messages will be fetched.
        """
        # NOTE: Order of params matters when making the RCP call
        params = {
            "chat_id": chat_id,
            "cursor": "",
            "limit": 500
        }
        all_messages = []
        # Keys that need to be converted to datetime.datetime
        timestamp_keys = []

        finished = False
        while not finished:
            data = self.__call_rpc("messaging", "chatMessages", list(params.values()))
            result: dict[str, Union[str, list[dict]]] = data.get("result", {})
            messages: Optional[list[dict]] = result.get("messages")
            cursor: Optional[str] = result.get("cursor")
            if not cursor:
                cursor = ""
            if not messages:
                messages = []

            if messages and not timestamp_keys:
                timestamp_keys = [key for key in result["messages"][0].keys() if "timestamp" in key.lower()]

            for message in messages:
                point = {
                    self.__camel_to_snake(key): value if key not in timestamp_keys else datetime.datetime.fromtimestamp(value / self.__timestamp_divisor)
                    for key, value in message.items()
                }
                if isinstance(point.get("bridge_message"), str):
                    point["bridge_message"] = json.loads(json.dumps(ast.literal_eval(point["bridge_message"])))

                if start_timestamp and point["timestamp"] < start_timestamp:
                    finished = True
                    break

                if end_timestamp and point["timestamp"] > end_timestamp:
                    continue

                all_messages.append(point)

            if len(cursor) > 0:
                params["cursor"] = cursor
            else:
                finished = True

        return all_messages

    def add_contact(self, public_key: str, display_name: Optional[str] = None):
        """
        Send a contact request / approve a contact.

        Parameters:
            - `public_key` - the contact's public key
            - `display_name` - this field is required if the `public_key` does not appear in your contacts. This will set their display name (can be different from the one the other user has chosen)
        """
        if public_key == self.info["public_key"]:
            return self

        contacts = list(self.contacts.values())
        if not display_name:
            for contact in contacts:
                if public_key != contact["public_key"]:
                    continue

                display_name = contact["display_name"]
                break

        if not display_name:
            raise exceptions.InvalidContactError(f"Cannot add contact {public_key}...\nPlease make sure you add display_name for contacts that you are sending friend requests to and have never interacted with before!")

        params = [{"id": public_key, "nickname": "", "displayName": display_name, "ensName": ""}]
        self.__call_rpc("messaging", "addContact", params)
        return self

    def remove_contact(self, public_key: str) -> bool:
        """
        Remove the contact / decline a contact request.

        Parameters:
            - `public_key` - the contact's public key

        Output:
            - If `True` the user has been removed. If `False` the user has not been removed (either not a contact or not a friend)
        """
        contact_info = self.contacts.get(public_key, {})
        # Cannot remove a contact that is not in your contact
        if not contact_info:
            return False
        # Contact has already been removed
        if contact_info["contact_state"] == "none":
            return False
        params = [public_key]
        self.__call_rpc("messaging", "removeContact", params)
        return True

    def send_request_community(self, url: str) -> Optional[datetime.datetime]:
        """
        Send a request to join a community

        Parameters:
            - `url` - the community's URL

        Output:
            - the timestamp the request was sent
        """
        data = self.__call_rpc("urls", "parseSharedURL", [url])
        raw: dict = data.get("result", {})
        community_key = raw["community"]["communityId"]

        params = [{"communityKey": community_key, "waitForResponse": True, "tryDatabase": True}]
        data = self.__call_rpc("messaging", "fetchCommunity", params)
        raw: dict = data.get("result", {})
        community_id = raw["id"]

        params = [{
            "communityId": community_id,
            "addressesToReveal": [self.info["wallet_address"]],
            "airdropAddress": self.info["wallet_address"]
        }]
        data = self.__call_rpc("messaging", "requestToJoinCommunity", params)
        return datetime.datetime.fromtimestamp(raw.get("requestedToJoinAt", datetime.datetime.now().timestamp()))

    def backup(self) -> str:
        """
        Create a `.bkp` (Backup) for the account. If the backup was not successful, a custom exception will be raised.

        Output:
            - the file path of the backup. The name is unique per account.
        """
        self.info
        response = requests.post(self.__urls["http"]["create_backup"])
        result: dict = response.json()
        file_path = result.get("filePath")

        if not file_path or (isinstance(file_path, str) and len(file_path) == 0):
            raise exceptions.BackupError(f"There was an error with creating a backup for {self.info['display_name']}")

        file_name = os.path.basename(file_path)
        sdk_file_path = os.path.join(self.__backup_sdk_folder, file_name)
        file_path = sdk_file_path
        if self.__backup_folder:
            file_path = os.path.join(self.__backup_folder, file_name)
            shutil.move(sdk_file_path, file_path)

        return file_path

    def get_tokens(self) -> pd.DataFrame:
        """
        Get all tokens that can be used in Status.

        Output:
            - DataFrame of all tokens
        """
        if len(self.__available_tokens) > 0:
            return self.__available_tokens.copy()

        columns = ["chainId", "address", "symbol", "decimals", "crossChainId"]
        info = []
        result: list[dict] = self.__call_rpc("wallets", "getAllTokenLists").get("result", [])
        for current in result:
            if len(current["tokens"]) == 0:
                continue
            data = pd.DataFrame(current["tokens"])[columns]
            data = data.assign(
                decimals = data["decimals"].astype("int8"),
                chainId = data["chainId"].astype("int8"),
                crossChainId = data["crossChainId"].apply(lambda value: None if len(value) == 0 else value),
                source_id = current["name"]
            )
            info.append(data)

        if info:
            self.__available_tokens = pd.concat(info, ignore_index=True)
            self.__available_tokens.columns = [self.__camel_to_snake(column) for column in self.__available_tokens.columns]

        return self.__available_tokens.copy()

    def get_balance(self, token_addresses: Union[list[str], str], chain_ids: Union[list[int], int] = 1, wallets: Optional[Union[list[str], str]] = None, ccy: Optional[Union[str, list[str]]] = None) -> pd.DataFrame:
        """
        Get the current amount for the provided token addresses, chain IDs and wallets.

        Parameters:
            - `token_addresses` - the token addresses as they appear in `get_tokens()`
            - `chain_ids` - chain IDs as they appear in `self.chains`
            - `wallets` - if left blank, the account's `wallet_address` will be used. However other wallets can be monitored as well.
            - `ccy` - the fiat currency the tokens will be converted to.

        Output:
            - DataFrame containing the current balance and fiat amount (if `ccy` is provided)
        """

        if isinstance(wallets, str):
            wallets = [wallets]

        elif isinstance(wallets, type(None)):
            wallets = [self.info["wallet_address"]]

        if isinstance(wallets, list):
            wallets = list(set(wallets))

        if isinstance(token_addresses, str):
            token_addresses = [token_addresses]

        if isinstance(token_addresses, list):
            token_addresses = list(set(token_addresses))

        if isinstance(chain_ids, int):
            chain_ids = [chain_ids]

        if isinstance(ccy, str):
            ccy = [ccy]
        elif isinstance(ccy, type(None)):
            ccy = []

        if ccy:
            ccy = [
                current.upper()
                for current in ccy
                if current.upper() in self.__get_fiat_ccy()
            ]

        tokens = self.__get_valid_tokens(chain_ids, token_addresses)

        result: dict[str, dict[str, dict[str, str]]] = self.__call_rpc("wallets", "getBalancesByChain", [wallets, tokens]).get("result", {})
        data = [
            {
                "chain_id": int(chain_id),
                "wallet_address": wallet_address,
                "token_address": token_address,
                "amount": token_hex_amount,
            }
            for chain_id, chain_info in result.items()
            for wallet_address, wallet_info in chain_info.items()
            for token_address, token_hex_amount in wallet_info.items()
        ]

        if not data:
            return pd.DataFrame()

        data = pd.DataFrame(data)
        available_tokens = self.get_tokens()
        column_mapping = {"chain_id": "chain_id", "address": "token_address", "symbol": "token_symbol", "decimals": "decimals"}
        data: pd.DataFrame = data.merge(
            available_tokens[list(column_mapping.keys())].rename(columns=column_mapping).drop_duplicates(),
            "left",
            ["chain_id", "token_address"]
        )
        final_columns = ["timestamp", "wallet_address", "token_address", "token_symbol", "amount", "chain_id"]
        data = data.assign(
            timestamp = datetime.datetime.now(),
            chain_id = data["chain_id"].astype("int8"),
            amount = data.apply(lambda row: int(row["amount"], 16) / (10 ** row["decimals"]), axis=1)
        )[final_columns]

        if not ccy:
            return data.copy()

        result = self.__call_rpc("wallets", "fetchPrices", [tokens, ccy]).get("result", {})
        if not result:
            return data.copy()

        rates = pd.DataFrame([
            {
                "chain_id": int(address.split("-")[0]),
                "token_address": address.split("-")[1],
                "ccy": ccy,
                "price": price
            }
            for address, prices in result.items()
            for ccy, price in prices.items()
        ])
        data = data.merge(rates, "outer", ["chain_id", "token_address"])
        return data

    def get_market(self, token_addresses: Union[list[str], str], chain_ids: Union[list[int], int] = 1, ccy: str = "USD") -> pd.DataFrame:
        """
        Get market information for the provided token addresses and chain IDs.

        Parameters:
            - `token_addresses` - the token addresses as they appear in `get_tokens()`
            - `chain_ids` - chain IDs as they appear in `self.chains`
            - `ccy` - the fiat currency the market values will be fetched for.

        Output:
            - DataFrame containing the current market values and fiat amount
        """
        if isinstance(token_addresses, str):
            token_addresses = [token_addresses]

        if isinstance(token_addresses, list):
            token_addresses = list(set(token_addresses))

        if isinstance(chain_ids, int):
            chain_ids = [chain_ids]

        ccy = ccy.upper()
        available_ccy = self.__get_fiat_ccy()
        if ccy not in available_ccy:
            raise exceptions.InvalidCurrencyError(f"Given currency {ccy} is invalid...\nAvailable ISO 4217 currencies: {available_ccy}")

        tokens = self.__get_valid_tokens(chain_ids, token_addresses)
        market_info = pd.DataFrame([
            {
                "chain_id": int(token_address.split("-")[0]),
                "address": token_address.split("-")[1],
                "currency": ccy,
                **info
            }
            for token_address, info in self.__call_rpc("wallets", "fetchMarketValues", [tokens, ccy]).get("result", {}).items()
        ])
        market_info: pd.DataFrame = market_info.assign(
            timestamp = datetime.datetime.now(),
            chain_id = market_info["chain_id"].astype("int8")
        )
        market_info = market_info.merge(
            self.get_tokens()[["chain_id", "address", "symbol"]].drop_duplicates(),
            "left",
            ["chain_id", "address"]
        )
        column_mapping = {
            "timestamp": "timestamp",
            "chain_id": "chain_id",
            "address": "token_address",
            "symbol": "token_symbol",
            "currency": "fiat_ccy",
            "MKTCAP": "market_cap",
            "HIGHDAY": "high_price",
            "LOWDAY": "low_price",
            "CHANGE24HOUR": "pnl_24hr",
            "CHANGEPCTDAY": "pct_change",
            "CHANGEPCTHOUR": "pct_change_1hr",
            "CHANGEPCT24HOUR": "pct_change_24hr"
        }
        market_info = market_info.rename(columns=column_mapping)[list(column_mapping.values())]
        return market_info.copy()

    def send_transaction(self, address: str, symbol: str, amount: float, chain_id: int = 1) -> Optional[str]:
        """
        Send crypto to specified `address`

        Parameters:
            - `address` - the wallet address of the receiver
            - `symbol` - either a valid Status token symbol from `def get_tokens()` or its address
            - `amount` - the amount that will be sent to the `address`
            - `chain_id` - valid Chain from `self.chains`

        Output:
            - Transaction hash that to monitor the transactions progress
        """
        is_eth = symbol == "ETH"
        is_address = symbol.startswith("0x")
        symbol = symbol.upper()
        tokens = self.get_tokens()[["chain_id", "address", "symbol", "decimals"]].drop_duplicates().reset_index(drop=True)
        query = (tokens["address" if is_address else "symbol"] == symbol) & (tokens["chain_id"] == chain_id)
        if query.sum() == 0:
            raise exceptions.InvalidTokenError(f"Given {'address' if is_address else 'symbol'} {symbol} on chain ID {chain_id} does not exist...")

        token_info = tokens.loc[query].to_dict("records")[0]

        balance = self.balance
        query = (balance["address"] == token_info["address"]) & (balance["chain_id"] == chain_id)
        if query.sum() == 0:
            raise exceptions.InvalidTokenError(f"Given {'address' if is_address else 'symbol'} {symbol} on chain ID {chain_id} was not found in your wallet ({self.info['wallet_address']})...")

        wallet_amount = balance.loc[query].reset_index(drop=True)["amount"].iloc[0]
        if amount > wallet_amount:
            raise exceptions.InvalidTokenError(f"Given {'address' if is_address else 'symbol'} {symbol} on chain ID {chain_id} has {wallet_amount} but you are trying to send {amount}...")

        raw_amount = int(amount * (10**token_info["decimals"]))

        tx = {
            "version": 1,
            "from": self.info["wallet_address"],
            "to": address if is_eth else token_info["address"],
            "value": hex(raw_amount) if is_eth else "0x0",
            "fromChainID": chain_id,
            "toChainID": chain_id,
        }
        if not is_eth:
            encoded_args = eth_abi.encode(["address", "uint256"], [address, raw_amount]).hex()
            tx["data"] = "0x" + self.__keccak256_selectors["transfer"] + encoded_args

        payload = {
            "password": self.info["password"],
            "txArgs": tx
        }
        response = requests.post(self.__urls["http"]["transaction"], json=payload)
        transaction_hash: str = response.json().get("result")

        url = f"http://etherscan.io/tx/{transaction_hash}"
        self.logger.info(f"Transaction: {url}")
        return transaction_hash

    def swap_tokens(self, from_token: str, to_token: str, amount: float, chain_id: int = 1) -> Optional[str]:
        """
        Convert ERC-20 token to ETH and ETH to ERC-20 token.

        NOTE: Only `ETH` <-> ERC-20 swaps are currently supported. ERC-20 <-> ERC-20
        swaps (e.g. `SNT` <-> `USDT`) are not yet implemented and the routing engine

        Parameters:
            - `from_token` - the token to swap from. Either a valid Status token symbol from `get_tokens()` (e.g. `ETH`), or its address
            - `to_token` - the token to swap to. Either a valid Status token symbol from `get_tokens()` (e.g. `ETH`), or its address
            - `amount` - the amount of `from_token` to swap
            - `chain_id` - valid Chain from `self.chains`. The swap happens on a single chain (`from_token` and `to_token` must be on the same chain)

        Output:
            - Transaction hash to monitor the swap's progress
        """
        def normalize_token(token: str, chain_id: int) -> str:
            """
            Normalize token input so it can be passed to
            """
            if token.startswith("0x"):
                return f"{chain_id}-{token}"

            tokens = self.get_tokens()
            token = token.upper()
            # NOTE: There are multiple ETHs
            if token == "ETH":
                return f"{chain_id}-{self.__ETH_ADDRESS}"

            query = (tokens["symbol"] == token) & (tokens["chain_id"] == chain_id)
            if query.sum() == 0:
                raise exceptions.InvalidTokenError(f"Token {token} on chain {chain_id} is not available...")

            selected = tokens.loc[query].copy()
            token_key = selected.apply(lambda row: f"{row['chain_id']}-{row['address']}", axis=1).drop_duplicates().iloc[0]
            return token_key

        def to_hex_wei(amount: float, address: str, chain_id: int) -> str:
            """
            Convert the `from_token` amount to hexadecimal WEI
            """
            # Remove chain_id from beginning
            address = address.split("-")[-1]
            tokens = self.get_tokens()
            query = (tokens["address"] == address) & (tokens["chain_id"] == chain_id)
            selected = tokens.loc[query].reset_index(drop=True).copy()
            decimals = int(selected["decimals"].iloc[0])
            raw_amount = int(amount * (10**decimals))
            return hex(raw_amount)

        def verify(from_address: str, amount: float):
            """
            Verify if the FROM address exists in the wallet and has enough balance.
            """
            balance = self.balance
            query = balance["chain_id"].astype(str) + "-" + balance["address"] == from_address
            if query.sum() == 0:
                raise exceptions.InvalidTokenError(f"Token {from_address} was not found in your wallet ({self.info['wallet_address']})...")

            selected = balance.loc[query].reset_index(drop=True).copy()
            available_amount = selected["amount"].iloc[0]
            if available_amount < amount:
                raise exceptions.InvalidTokenError(f"Token {from_address} has a balance of {available_amount} but you are trying to swap {amount}...")


        from_address = normalize_token(from_token, chain_id)
        verify(from_address, amount)
        to_address = normalize_token(to_token, chain_id)

        # ETH <-> ERC-20 swaps
        is_eth_swap = from_address.split("-")[-1] == self.__ETH_ADDRESS or to_address.split("-")[-1] == self.__ETH_ADDRESS
        if not is_eth_swap:
            raise exceptions.InvalidTokenError(f"Only ETH <-> ERC-20 swaps are supported. Either `from_token` or `to_token` must be ETH (got {from_token} -> {to_token})...")

        amount_in = to_hex_wei(amount, from_address, chain_id)
        transaction_uuid = str(uuid_lib.uuid4())
        params = {
            "uuid": transaction_uuid,
            "sendType": 8, # swap
            "addrFrom": self.info["wallet_address"],
            "addrTo":   self.info["wallet_address"], # swap output goes back to you
            "amountIn":  amount_in,
            "amountOut": "0x0",
            "tokenKey":   from_address,
            "toTokenKey": to_address,
            "tokenIDIsOwnerToken": False,
            "fromChainID": chain_id,
            "toChainID":   chain_id,
            "gasFeeMode":  1,
            "slippagePercentage": 0.5,
        }
        # (1) Get suggested routes
        self.signal.connect()
        with self.signal.expect("wallet.suggested.routes") as exp:
            self.__call_rpc("wallets", "getSuggestedRoutesAsync", [params])

        suggested_routes = exp.result
        error = suggested_routes["event"].get("ErrorResponse", {})
        if error:
            details = "\n".join([f"{key}: {value}" for key, value in error.items()])
            raise exceptions.BackendError(f"Status Backend could not build a swap route for {from_token} -> {to_token} on chain {chain_id}:\n{details}")

        params = [suggested_routes["event"]["Uuid"]]
        # (2) Build transaction from Route
        with self.signal.expect("wallet.router.sign-transactions") as exp:
            self.__call_rpc("wallets", "buildTransactionsFromRoute", params)

        # (3) Sign transaction
        signed_transaction = exp.result
        event = signed_transaction["event"]
        signatures = {}
        for hash in event["signingDetails"]["hashes"]:
            params = [hash, self.info["wallet_address"], self.info["password"]]
            sig = self.__call_rpc("wallets", "signMessage", params).get("result")
            # Strip 0x
            raw = sig[2:]
            signatures[hash] = {
                "r": raw[:64],
                "s": raw[64:128],
                "v": raw[128:]
            }

        # (4) Send transaction
        with self.signal.expect("wallet.router.transactions-sent") as exp:
            params = [{"uuid": transaction_uuid, "signatures": signatures}]
            self.__call_rpc("wallets", "sendRouterTransactionsWithSignatures", params)

        event: dict[str, dict] = exp.result["event"]
        # Usually just 1
        sent_transactions: list[dict] = event["sentTransactions"]
        self.signal.disconnect()
        return sent_transactions[0]["hash"]

    def get_transactions(self, refresh: bool = False) -> pd.DataFrame:
        """
        Get wallet transactions from all Alchemy chains.

        Parameters:
            - `refresh` - if `True` then the data will be refetched from scratch. If `False` then the data will be cached after the first call.

        Output:
            - Wallet's transactions
        """
        if not self.__alchemy_token:
            raise exceptions.WalletNotConfiguredError("Cannot fetch transactions without setting an `alchemy_token` when calling `login`.")

        if not refresh and isinstance(self.__transactions, pd.DataFrame):
            return self.__transactions.copy()

        wallet_address = self.info["wallet_address"]
        final = []
        for domain, chain_id in constants.ALCHEMY_CHAIN_IDS.items():
            for key in ["fromAddress", "toAddress"]:
                transfers = []
                page_key = ""
                url = f"https://{domain}.g.alchemy.com/v2/{self.__alchemy_token}"
                while isinstance(page_key, str):
                    payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "alchemy_getAssetTransfers",
                        "params": [
                            {
                                key: wallet_address,
                                "maxCount": hex(1_000),
                                "pageKey": page_key if isinstance(page_key, str) else None,
                                "category": ["external", "internal", "erc20"]
                            }
                        ]
                    }
                    response = requests.post(url, json=payload)
                    result: dict = response.json().get("result", {})
                    current_transfers = result.get("transfers", [])
                    transfers += current_transfers
                    page_key = result.get("pageKey")

                if len(transfers) == 0:
                    continue
                transfers = pd.DataFrame(transfers).assign(chain_id = chain_id)
                final.append(transfers)

        if len(final) == 0:
            return pd.DataFrame()

        final: pd.DataFrame = pd.concat(final, ignore_index=True)
        columns = {
            "blockNum": "block_number",
            "hash": "trx_hash",
            "from": "from_address",
            "to": "to_address",
            "value": "amount",
            "asset": "symbol",
            "category": "trx_type",
            "chain_id": "chain_id"
        }
        final = final[list(columns.keys())].rename(columns=columns)

        block_mapping = {}
        for block_number in final["block_number"].unique():
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getBlockByNumber",
                "params": [block_number, False],
            }
            url = f"https://eth-mainnet.g.alchemy.com/v2/{self.__alchemy_token}"
            response = requests.post(url, json=payload)
            block_mapping[block_number] = int(response.json()["result"]["timestamp"], 16)

        final.insert(0, "timestamp", pd.to_datetime(final["block_number"].map(block_mapping), unit="s", utc=True))
        final = final.assign(
            block_number = final["block_number"].apply(lambda value: int(value, 16)),
            trx_type = final.apply(lambda row: "sent" if row["from_address"].lower() == wallet_address.lower() else "received", axis=1),
            amount = final["amount"] * final.apply(lambda row: -1 if row["from_address"].lower() == wallet_address.lower() else 1, axis=1)
        ).sort_values("block_number", ascending=False).reset_index(drop=True)

        self.__transactions = final.copy()
        return self.__transactions.copy()

    def __start_messenger(self):
        """
        Start the decentralized messaging service.
        This is required for messages to be received / sent.
        """
        if self.__is_messenger_launched:
            return
        self.logger.info("Starting messaging")
        self.__call_rpc("messaging", "startMessenger")
        self.__signal.get("wakuv2.peerstats")
        self.__is_messenger_launched = True
        self.logger.info("Messaging launched")

    def __del__(self):
        """
        Handles automatic logout when calling `del`
        and after running `python`
        """
        try:
            self.logout()
        except Exception:
            pass

        try:
            self.__signal.close(None)
        except Exception:
            pass

    def call_rpc(self, prefix: str, method_name: str, params: Optional[Union[list, dict]] = None) -> dict:
        """
        For faster development purposes
        """
        return self.__call_rpc(prefix, method_name, params)

    def __load_backup(self):
        """
        Try to load every file in the Docker volume
        when an account recover is done.
        """
        folder = self.__backup_folder if self.__backup_folder else self.__backup_sdk_folder

        file_name = self.info["compressed_key"][-6:] + "_user_data.bkp"
        file_path = os.path.join(folder, self.info["compressed_key"][-6:] + "_user_data.bkp")
        if not os.path.exists(file_path):
            self.logger.warning(f"Backup file was not found in {folder}")
            return

        sdk_file_path = os.path.join(self.__backup_sdk_folder, file_name)
        if sdk_file_path != file_path:
            shutil.copy(file_path, sdk_file_path)

        params = {
            "filePath": os.path.join(self.__docker_backup_folder, file_name).replace("\\", "/")
        }
        self.logger.info(f"Loading backup file: {file_path}")
        response = requests.post(self.__urls["http"]["load_backup"], json=params)
        error: str = response.json().get("error", "")

        if sdk_file_path != file_path:
            os.remove(sdk_file_path)

        if len(error) == 0:
            self.logger.info(f"Successfully loaded file!")
        else:
            self.logger.warning(error)

    def __call_rpc(self, prefix: str, method_name: str, params: Optional[Union[list, dict]] = None) -> dict:
        """
        Make RPC calls to Status Backend

        Parameters:
            - `prefix` - the prefix of the method name
            - `method_name` - the method name as it is in the backend
            - `params` - RPC call parameters

        Output:
            - the raw output from the RPC method
        """
        # Quick initialization check - RPC calls
        # can be made only after the user has logged in
        self.info
        name = self.__prefix_mapping.get(prefix)
        if not name:
            raise exceptions.BackendError(f"Name {name} does not exist... Available options: {list(self.__prefix_mapping.keys())}")

        if name == "wallet" and not self.__is_wallet_set:
            raise exceptions.WalletNotConfiguredError()

        data = {
            'jsonrpc': '2.0',
            # NOTE: Waku may be renamed to Logos Messaging (or something similar)
            'method': f'{name}_{method_name}',
            'id': None # Original code has an incrementing ID but it does not make a difference
        }
        if params:
            data["params"] = params

        response = requests.get(self.__urls["http"]["rpc"], json=data)
        return response.json()

    def __get_fiat_ccy(self) -> list[str]:
        """
        Get the fiat currency symbols that Status has access to

        https://www.iso.org/iso-4217-currency-codes.html
        https://www.iban.com/currency-codes

        Output:
            - list of all fiat currency symbols
        """
        if self.__iso4217_ccy:
            return self.__iso4217_ccy

        self.__iso4217_ccy = [
            ccy.upper()
            for ccy in self.__call_rpc("wallets", "getCachedCurrencyFormats").get("result", {}).keys()
            if len(ccy) == 3 and ccy.upper() != "XXX"
        ]
        return self.__iso4217_ccy

    def __get_valid_tokens(self, chain_ids: list[int], token_addresses: list[str]) -> list[str]:
        available_chains = list(self.chains.keys())
        available_tokens = self.get_tokens()
        tokens = []
        for chain_id in chain_ids:

            if chain_id not in available_chains:
                continue

            query = available_tokens["address"].isin(token_addresses) & (available_tokens["chain_id"] == chain_id)
            selected = available_tokens.loc[query].reset_index(drop=True).copy()
            if len(selected) == 0:
                continue

            tokens += selected.apply(lambda row: f"{row['chain_id']}-{row['address']}", axis=1).unique().tolist()
        return tokens

    def __camel_to_snake(self, name: str) -> str:
        """
        Used to make camel case Status Backend keys
        more Pythonic (snake case). Function is used
        when the entire raw data point is returned.

        Parameters:
            - `name` - camel case dictionary key

        Output:
            - snake case `name`
        """
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
        s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()

    def __validate_display_name(self, name: str) -> bool:
        """
        Validate the display name based on Status App rules.
        Validation most probably is dealt with on the GUI side
        of the application instead of the backend.

        Status App validation rules:
            - Use A-Z and 0-9, hyphens and underscores only
            - Display name must be at least 5 characters long
            - Display name can't start or end with a space

        Parameters:
            - `name` - the name that the user wants to use to login / create account / change

        Output:
            - `True` if the name was successfully changed. A
        """
        if name != name.strip():
            raise exceptions.InvalidDisplayNameError("Display name cannot start or end with a space.")

        if len(name) < 5:
            raise exceptions.InvalidDisplayNameError("Display name must be at least 5 characters long.")

        if len(name) > 24:
            raise exceptions.InvalidDisplayNameError("Display name cannot be more than 24 characters long.")

        if not re.fullmatch(r"[A-Za-z0-9 _-]+", name):
            raise exceptions.InvalidDisplayNameError("Display name can contain only A-Z, 0-9, hyphens (-), underscores (_) and spaces.")

        return True
