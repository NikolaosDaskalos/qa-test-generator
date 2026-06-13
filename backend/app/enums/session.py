from enum import Enum


class SessionMessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
