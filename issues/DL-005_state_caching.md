# Issue DL-005: State Caching and Optimistic Updates

## Description
`DLightDevice` currently queries the device state over the network every time `get_state()` is called. It does not track state changes locally.

## Reasoning
- **Reduced Traffic**: Many applications poll for state. If the library knows the last set value, it can reduce the frequency of network queries.
- **UI Responsiveness**: For applications with a UI, "optimistic updates" (showing the new brightness immediately before the network call completes) make the system feel instantaneous.
- **Fallback**: Provides a "last known good" state if the device becomes temporarily unreachable.

## Proposed Implementation
- Add a `_state` attribute to `DLightDevice`.
- Update the cache whenever a control command (`turn_on`, `set_brightness`, etc.) succeeds.
- Provide a `force_update=True` flag for `get_state()` to bypass the cache.
