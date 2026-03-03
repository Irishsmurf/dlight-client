# Project Roadmap: dlight-client

This document outlines the planned enhancements and future direction for the `dlight-client` library.

## Short-Term Goals (v1.3.0 - v1.4.0)

- **[DL-001] Connection Pooling and Persistent TCP Connections**: Optimize communication by reusing TCP connections for sequential commands.
- **[DL-002] Granular CLI Subcommands**: Enhance the CLI to allow individual control commands (e.g., `dlight-client set-brightness 50`) instead of just an interaction sequence.

## Medium-Term Goals (v1.5.0+)

- **[DL-003] Automatic Retry Logic**: Implement configurable retry mechanisms for transient network failures.
- **[DL-004] mDNS/Zeroconf Discovery Support**: Add support for industry-standard discovery to complement the proprietary UDP broadcast.
- **[DL-005] State Caching and Optimistic Updates**: Improve responsiveness by maintaining a local state cache in `DLightDevice`.

---
*For detailed specifications of each feature, please refer to the corresponding tracking issues in the `issues/` directory.*
