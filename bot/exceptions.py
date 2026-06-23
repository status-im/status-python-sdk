from typing import Optional

class BackendError(Exception):
    pass

class NotLoggedInError(Exception):
    def __init__(self):
        super().__init__("Make sure you are logged in to your Status account with login() first...")

class WalletNotConfiguredError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Cannot use this wallet method without setting `infura_token`, `alchemy_token` and `coingecko_api_key` when calling `login`.")

class InvalidDisplayNameError(ValueError):
    pass

class InvalidContactError(ValueError):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "Please provide either a Key Unique Identifier (key_uid) or a Display Name / ENS (name)...")

class InvalidCurrencyError(Exception):
    pass

class InvalidTokenError(Exception):
    pass

class BackupError(Exception):
    pass

class ProfilePictureError(Exception):
    pass

class DockerError(Exception):
    pass

class SignalError(Exception):
    pass
