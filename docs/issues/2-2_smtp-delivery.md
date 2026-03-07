# 2-2 — SMTP Email Delivery

**Status**: `open`
**Parent**: 2
**Children**: —
**Depends on**: 1-1, 2-1

## Description

Implement `obsidian_agent/delivery/base.py` (protocol) and `obsidian_agent/delivery/smtp.py`.

## Implementation Notes

### base.py

```python
from typing import Protocol

class Delivery(Protocol):
    def send(self, subject: str, body: str) -> None: ...
```

### smtp.py

```python
@dataclass
class SmtpConfig:
    smtp_host: str
    smtp_port: int
    username: str
    password: str        # loaded from env var at instantiation
    from_address: str
    to_address: str

class SmtpDelivery:
    def __init__(self, cfg: SmtpConfig): ...
    def send(self, subject: str, body: str) -> None:
        # use smtplib.SMTP with STARTTLS
        # plain text body; keep it simple for v1
        ...
```

Password must be read from the environment variable named in config (`password_env`), not
stored directly. Raise `ConfigError` at startup if the env var is not set.

### Error handling

- On SMTP failure: log the error with full exception, re-raise as `DeliveryError`
- Do not silently swallow failures

## Testing & Validation

- `SmtpDelivery.send()` tested with a mock SMTP server (use `unittest.mock.patch`)
- Missing env var raises `ConfigError` at init, not at send time
- SMTP failure raises `DeliveryError`

## Definition of Done

`SmtpDelivery` sends email via STARTTLS. Works against Gmail and Fastmail with an app password.
