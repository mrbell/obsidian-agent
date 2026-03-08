from typing import Protocol


class DeliveryError(Exception):
    """Raised when message delivery fails or is misconfigured."""


class Delivery(Protocol):
    def send(self, subject: str, body: str) -> None: ...
