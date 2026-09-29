from importlib.metadata import PackageNotFoundError, version as _version

from . import exceptions
from .account import Account
from .community.base import Community, Channel
from .group_chat import GroupChat
from .signal import Signal

__all__ = [
    "Account",
    "GroupChat",
    "Community",
    "Channel",
    "exceptions",
    "Signal"
]

try:
    __version__ = _version("status-sdk")
except PackageNotFoundError:
    # Running from a source checkout that was never installed
    __version__ = "dev"
