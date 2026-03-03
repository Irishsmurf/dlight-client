# Issue DL-003: Automatic Retry Logic

## Description
Network operations in the current library are "one-shot." If a transient network issue occurs (common on Wi-Fi), a `DLightTimeoutError` or `DLightConnectionError` is raised immediately.

## Reasoning
- **Reliability**: Smart home environments are prone to temporary Wi-Fi interference.
- **User Experience**: Automatically recovering from a "Connection Reset" or a brief timeout makes the library feel much more robust and "production-ready."

## Proposed Implementation
- Add a `max_retries` parameter to `AsyncDLightClient` (defaulting to 0 for backward compatibility, but recommended as 2 or 3).
- Implement exponential backoff between retries.
- Only retry on idempotent operations or specific "safe" network errors.
