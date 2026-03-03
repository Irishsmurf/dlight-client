# Issue DL-001: Connection Pooling and Persistent TCP Connections

## Description
Currently, `AsyncDLightClient` opens a new TCP connection for every command sent to a device and closes it immediately after receiving the response. For operations requiring multiple sequential commands (e.g., the `DLightDevice.flash()` sequence or rapid brightness adjustments), this introduces significant overhead and latency.

## Reasoning
- **Performance**: Eliminating the TCP handshake for every command significantly reduces total execution time for sequences.
- **Resource Efficiency**: Reducing the number of connection setups/teardowns is gentler on the microcontroller resources of the dLight lamp.
- **Responsiveness**: Lower latency leads to a better user experience, especially in interactive applications.

## Proposed Implementation
- Introduce a connection management layer within `AsyncDLightClient`.
- Implement an optional `persistent=True` flag for the client or a context manager to hold a connection open.
- Add an idle timeout to automatically close persistent connections after a period of inactivity.
