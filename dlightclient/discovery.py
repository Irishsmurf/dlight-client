# dlightclient/discovery.py
"""Handles UDP discovery of dLight devices."""

import asyncio
import socket # Still needed for socket errors, constants
import json
import binascii
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

# Import constants and exceptions from within the package
from .constants import (
    DEFAULT_UDP_DISCOVERY_PORT,
    DEFAULT_UDP_RESPONSE_PORT,
    UDP_DISCOVERY_PAYLOAD_HEX,
    BROADCAST_ADDRESS,
    _LOGGER, # Use the logger defined in constants or define one here
)
# Exceptions are not directly raised here but might be useful for context
# from .exceptions import DLightError

# Logger specific to discovery, inheriting from the base logger if needed
_LOGGER = logging.getLogger(__name__)


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Asyncio Protocol to handle incoming discovery responses."""
    def __init__(self, discovered_devices_set: Set[str], results_list: List[Dict]):
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.discovered_devices_set = discovered_devices_set
        self.results_list = results_list
        super().__init__()

    def connection_made(self, transport: asyncio.DatagramTransport):
        _LOGGER.debug("Discovery listener connection made (transport ready)")
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        ip_address = addr[0]
        _LOGGER.debug("Received %d bytes from %s", len(data), ip_address)

        # Avoid processing duplicates immediately
        if ip_address in self.discovered_devices_set:
            _LOGGER.debug("Ignoring duplicate discovery response from %s", ip_address)
            return

        try:
            # Attempt to decode JSON, add IP address
            device_info = json.loads(data.decode('utf-8'))
            device_info['ip_address'] = ip_address # Add IP to the result dict
            _LOGGER.info("Discovered dLight: %s at %s",
                         device_info.get('deviceId', 'Unknown ID'), ip_address)
            _LOGGER.debug("Full discovery info from %s: %s", ip_address, device_info)

            # Add to results if successfully parsed
            self.discovered_devices_set.add(ip_address)
            self.results_list.append(device_info)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            _LOGGER.warning("Error decoding discovery response from %s: %s. Raw data: %r",
                            ip_address, e, data)
        except Exception as e:
             _LOGGER.exception("Unexpected error processing datagram from %s", ip_address)


    def error_received(self, exc: Exception):
        # This is called for ICMP errors etc.
        _LOGGER.error(f"Discovery listener error: {exc}")

    def connection_lost(self, exc: Optional[Exception]):
        # Called when the listening transport is closed.
        if exc:
            _LOGGER.error(f"Discovery listener connection lost unexpectedly: {exc}")
        else:
            _LOGGER.debug("Discovery listener connection closed normally.")


async def discover_devices(
    discovery_duration: float = 3.0,
    response_port: int = DEFAULT_UDP_RESPONSE_PORT,
    discovery_port: int = DEFAULT_UDP_DISCOVERY_PORT,
    broadcast_address: str = BROADCAST_ADDRESS
) -> List[Dict[str, Any]]:
    """
    Discovers dLight devices on the network using asyncio UDP.

    Sends a UDP broadcast probe and listens for JSON responses.

    Args:
        discovery_duration: How long to listen for responses (in seconds).
        response_port: The local UDP port to listen on for responses.
        discovery_port: The UDP port dLights listen on for discovery probes.
        broadcast_address: The broadcast address to send the probe to.

    Returns:
        A list of dictionaries, each representing a discovered device
        including its 'ip_address'. Returns an empty list if none found or on error.
    """
    loop = asyncio.get_running_loop()
    discovered_devices_set: Set[str] = set()
    results_list: List[Dict] = []
    listen_transport: Optional[asyncio.DatagramTransport] = None
    send_transport: Optional[asyncio.DatagramTransport] = None

    try:
        # Decode the hex payload (synchronous)
        try:
            probe_payload = binascii.unhexlify(UDP_DISCOVERY_PAYLOAD_HEX)
        except binascii.Error as e:
             _LOGGER.error(f"Internal error: failed to decode UDP probe payload hex: {e}")
             return [] # Cannot proceed without payload

        # 1. Create the listening endpoint
        # Need await as create_datagram_endpoint is a coroutine
        listen_transport, _ = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(discovered_devices_set, results_list),
            local_addr=('0.0.0.0', response_port),
            # allow_broadcast=False # Not needed for listener
        )
        _LOGGER.debug(f"Listening for discovery responses on 0.0.0.0:{response_port}")

        # 2. Create a separate sending endpoint for broadcast
        # Need await here too
        send_transport, _ = await loop.create_datagram_endpoint(
            lambda: asyncio.DatagramProtocol(), # Simple protocol for sending only
            remote_addr=(broadcast_address, discovery_port),
            allow_broadcast=True # Request broadcast permission
        )

        # Enable broadcasting on the sending socket (best effort, might be redundant
        # if allow_broadcast=True worked, but good practice)
        sending_socket = send_transport.get_extra_info('socket')
        if sending_socket and isinstance(sending_socket, socket.socket):
             try:
                 sending_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                 _LOGGER.debug("Broadcast explicitly enabled for sending socket.")
             except OSError as e:
                  # May fail if allow_broadcast=True wasn't enough or OS restricts
                  _LOGGER.warning(f"Could not enable broadcast on sending socket: {e}. "
                                  "Discovery might fail if allow_broadcast=True was insufficient.")
        else:
             _LOGGER.warning("Could not get underlying socket for sending transport to enable broadcast.")


        # 3. Send the broadcast probe
        _LOGGER.info(f"Sending discovery probe to {broadcast_address}:{discovery_port}")
        send_transport.sendto(probe_payload)

        # 4. Wait for responses
        _LOGGER.debug(f"Waiting {discovery_duration} seconds for responses...")
        await asyncio.sleep(discovery_duration)

        _LOGGER.info(f"Discovery finished. Found {len(results_list)} potential device(s).")

    except PermissionError as e:
        # Common issue if not running with sufficient privileges for broadcast/bind
        _LOGGER.error(f"Permission denied for UDP broadcast or binding to port {response_port}. "
                      f"Try running with higher privileges if necessary. Error: {e}")
        return []
    except OSError as e:
         # Common issue if port is already in use or network interface issue
         _LOGGER.error(f"Network error during discovery (e.g., port {response_port} in use, "
                       f"or cannot bind/broadcast on network): {e}")
         return []
    except Exception as e:
        # Catch any other unexpected errors during setup or sleep
        _LOGGER.exception(f"An unexpected error occurred during async discovery: {e}")
        return []
    finally:
        # 5. Clean up transports
        if send_transport:
             try:
                 send_transport.close()
                 _LOGGER.debug("Discovery sender transport closed.")
             except Exception as e_close:
                 _LOGGER.debug(f"Error closing send transport: {e_close}")
        if listen_transport:
            try:
                listen_transport.close()
                _LOGGER.debug("Discovery listener transport closed.")
            except Exception as e_close:
                _LOGGER.debug(f"Error closing listen transport: {e_close}")

    return results_list

