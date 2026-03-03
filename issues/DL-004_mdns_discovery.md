# Issue DL-004: mDNS/Zeroconf Discovery Support

## Description
The current discovery mechanism relies on a proprietary UDP broadcast probe. While effective, many modern IoT devices also announce themselves via mDNS (Multicast DNS).

## Reasoning
- **Compatibility**: mDNS is a cross-platform standard supported by almost all modern networking stacks and discovery tools (like Home Assistant).
- **Network Resilience**: UDP broadcasts are sometimes blocked by aggressive firewall rules or complex network topologies where mDNS might still function.
- **Efficiency**: mDNS discovery can often be faster and more "passive" than active probing.

## Proposed Implementation
- Integrate a library like `zeroconf`.
- Add a new discovery method (or update `discover_devices`) to listen for `_dlight._tcp.local.` (or the actual service type used by the hardware).
- Fall back to UDP broadcast if mDNS fails to find devices.
