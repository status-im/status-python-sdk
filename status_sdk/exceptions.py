from typing import Optional

class BackendError(Exception):
    pass

class NotLoggedInError(Exception):
    def __init__(self):
        super().__init__("Make sure you are logged in to your Status account with login() first...")

class WalletNotConfiguredError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Cannot use this wallet method without setting `infura_token`, `alchemy_token` and `coingecko_api_key` when calling `login`.")

class InvalidCommunityKeyError(ValueError):
    pass

class CommunityNotFoundError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Please initialize the class with a valid `community_id` / make sure that you have been accepted in the community to use the class...")

class CommunityChannelNotFoundError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "The community channel was not found! The channel does not exist...")

class CommunityMembersError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Please provide valid Public Keys from the community only...")

class CommunityPendingMemberError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "The given request id is not a pending join request...")

class CommunityChannelCreationError(Exception):
    pass

class CommunityDuplicateError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "A community item with this name already exists! Please pick a different name...")

class CommunityPermissionError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Only the community's owner, admins and token masters can perform this action...")

class CommunityDataFolderError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Please provide a local `data_folder` when creating the Community. Make sure the folder is the same one used in `launch_docker_container`...")

class CommunityControlNodeError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "The provided folder cannot be uploaded as the community's control node...")

class InvalidUserStatusError(ValueError):
    pass

class InvalidDisplayNameError(ValueError):
    pass

class InvalidGroupChatNameError(ValueError):
    pass

class InvalidCommunityChannelNameError(ValueError):
    pass

class InvalidCommunityChannelDescriptionError(ValueError):
    pass

class InvalidCommunityChannelColourError(ValueError):
    pass

class InvalidCommunityChannelEmojiError(ValueError):
    pass

class GroupChatCreationError(Exception):
    pass

class GroupChatAlreadyExistsError(Exception):
    pass

class GroupChatNotFoundError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Please `create` the chat or initialize the class with `chat_id`")

class GroupChatMembersError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "The Group Chat has no members...")

class PublicKeyError(Exception):
    pass

class InvalidContactError(ValueError):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Please provide either a Key Unique Identifier (key_uid) or a Display Name / ENS (name)...")

class MessageTooLongError(ValueError):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Message cannot be longer than 2000 characters...")

class InvalidCurrencyError(Exception):
    pass

class InvalidTokenError(Exception):
    pass

class BackupError(Exception):
    pass

class DeviceSyncError(Exception):
    pass

class ProfilePictureError(Exception):
    pass

class DockerError(Exception):
    pass

class SignalError(Exception):
    pass
