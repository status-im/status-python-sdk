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
