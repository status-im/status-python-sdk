from enum import Enum

class Content(Enum):
    TEXT = 1
    STICKER = 2
    EMOJI = 4
    IMAGE = 7
    BRIDGED = 18

class Chat(Enum):
    PRIVATE = 1
    COMMUNITY = 2
    GROUP = 3

class Event(Enum):
    """
    The kind of event yielded by `def listen_events`, paired with its payload
    """
    MESSAGE = 1
    MENTION = 2
    CONTACT_REQUEST = 3
    COMMUNITY_REQUEST = 4

# ===========================================================================
# ===========================================================================
# ===========================================================================

# Internal usage only
class Request(Enum):
    """
    The state a community join request moved into.
    """
    PENDING = 1
    REJECT = 2
    ACCEPT = 3
    CANCEL = 4
