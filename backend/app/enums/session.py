"""Enumerations for repository sessions."""

from enum import Enum


class SessionMessageRole(str, Enum):
    """Author of a session history message."""

    user = "user"
    assistant = "assistant"
