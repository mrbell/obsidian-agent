# 10-6 — SMTP Delivery Hardening

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 2-2

## Description

`SmtpDelivery.send()` claims to raise `DeliveryError` on SMTP failures, but currently catches
only `smtplib.SMTPException`. Network and system errors such as DNS failures, connection
refusal, socket errors, and timeouts can escape uncaught.

The delivery contract should be made true in practice: callers handle `DeliveryError`,
not a grab-bag of lower-level exceptions.

## Implementation Notes

- Update `obsidian_agent/delivery/smtp.py`
- Catch and wrap:
  - `smtplib.SMTPException`
  - `OSError`
  - timeout-related failures if they are not already covered by `OSError`
- Preserve logging with stack traces for diagnosis
- Keep the public API unchanged

## Testing & Validation

Red/green TDD:

- Add failing tests for a mocked network/system exception path
- Assert those failures are wrapped as `DeliveryError`
- Keep existing SMTP auth/protocol regression tests passing

## Definition of Done

- Callers see `DeliveryError` for both SMTP-protocol and network/system send failures
- SMTP tests cover the newly wrapped exception classes
