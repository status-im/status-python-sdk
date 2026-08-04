from importlib.metadata import PackageNotFoundError, version as _version

from .account import Account
from .group_chat import GroupChat
from .community.base import Community
from .utils import launch_docker_container
from . import exceptions

try:
    __version__ = _version("status-sdk")
except PackageNotFoundError:
    # Running from a source checkout that was never installed
    __version__ = "dev"
