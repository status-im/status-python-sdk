from enum import Enum

class Content(Enum):
    TEXT = 1
    STICKER = 2
    STATUS = 3
    EMOJI = 4
    IMAGE = 7
    CONTACT_REQUEST = 11
    ACCEPTED_REQUEST = 16
    REMOVED_CONTACT = 17
    BRIDGED = 18


class Chat(Enum):
    PRIVATE = 1
    COMMUNITY = 2
    GROUP = 3
