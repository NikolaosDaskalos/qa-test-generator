"""Enumerations for repository sessions."""

from enum import Enum


class SessionMessageRole(str, Enum):
    """Author of a session history message."""

    user = "user"
    assistant = "assistant"


class OwnerVerdict(str, Enum):
    """The owner's human-in-the-loop verdict on an escalated Test Patch.

    Exactly three verdicts resolve the same suspended decision point: ``approve``
    commits and opens a Pull Request, ``reject`` discards the patch, and ``edit``
    returns the run to generation to revise the already-generated Test Files in
    place against the owner's free-text feedback. It is never a binary accept/discard.
    """

    approve = "approve"
    reject = "reject"
    edit = "edit"
