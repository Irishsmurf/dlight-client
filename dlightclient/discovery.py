# dlightclient/discovery.py
"""Handles UDP discovery of dLight devices."""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

from .constants import (
    BROADCAST_ADDRESS,
    DEFAULT_UDP_DISCOVERY_PORT,
    DEFAULT_UDP_RESPONSE_PORT,
    UDP_DISCOVERY_PAYLOAD,
)

# Logger specific to discovery, inheriting from the base logger if needed
_LOGGER = logging.getLogger(__name__)

# Upper bound on how long discovery waits, during cleanup, for the listener socket to close.
_LISTENER_CLOSE_TIMEOUT = 1.0


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """An asyncio datagram protocol for handling dLight discovery responses.

    This protocol is used internally by `discover_devices` and `discover_devices_stream`.
    It processes incoming UDP datagrams, decodes them as JSON, and pushes information about
    discovered devices onto a queue, ensuring no duplicates are added.

    Args:
        discovered_devices_set: A set to store the IP addresses of devices
            that have already been discovered, used for deduplication.
        queue: An asyncio.Queue to push newly discovered devices to.
    """

    def __init__(
        self,
        discovered_devices_set: Set[str],
        queue: asyncio.Queue[Dict[str, Any]],
    ):
        self.discovered_devices_set = discovered_devices_set
        self.queue = queue
        # Resolved by connection_lost, once the listener socket has actually been closed.
        self.closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        super().__init__()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        _LOGGER.debug("Discovery listener connection made (transport ready)")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        ip_address = addr[0]
        _LOGGER.debug("Received %d bytes from %s", len(data), ip_address)

        # Avoid processing duplicates immediately
        if ip_address in self.discovered_devices_set:
            _LOGGER.debug("Ignoring duplicate discovery response from %s", ip_address)
            return

        try:
            # Attempt to decode JSON, add IP address
            device_info = json.loads(data.decode("utf-8"))
            device_info["ip_address"] = ip_address  # Add IP to the result dict
            _LOGGER.info("Discovered dLight: %s at %s", device_info.get("deviceId", "Unknown ID"), ip_address)
            _LOGGER.debug("Full discovery info from %s: %s", ip_address, device_info)

            # Add to results if successfully parsed
            self.discovered_devices_set.add(ip_address)
            self.queue.put_nowait(device_info)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            _LOGGER.warning("Error decoding discovery response from %s: %s. Raw data: %r", ip_address, e, data)
        except Exception:
            _LOGGER.exception("Unexpected error processing datagram from %s", ip_address)

    def error_received(self, exc: Exception) -> None:
        # This is called for ICMP errors etc.
        _LOGGER.error(f"Discovery listener error: {exc}")

    def connection_lost(self, exc: Optional[Exception]) -> None:
        # Called when the listening transport is closed.
        if exc:
            _LOGGER.error(f"Discovery listener connection lost unexpectedly: {exc}")
        else:
            _LOGGER.debug("Discovery listener connection closed normally.")
        if not self.closed.done():
            self.closed.set_result(None)


async def discover_devices(
    discovery_duration: float = 3.0,
    response_port: int = DEFAULT_UDP_RESPONSE_PORT,
    discovery_port: int = DEFAULT_UDP_DISCOVERY_PORT,
    broadcast_address: str = BROADCAST_ADDRESS,
) -> List[Dict[str, Any]]:
    """Discovers dLight devices on the local network using UDP broadcast.

    This function sends a broadcast UDP probe to the network and listens for
    responses from dLight devices for a specified duration. It collects
    everything `discover_devices_stream` yields.

    Args:
        discovery_duration: The number of seconds to listen for responses.
        response_port: The local UDP port to listen on for responses.
        discovery_port: The UDP port dLight devices listen on for discovery probes.
        broadcast_address: The network broadcast address to send the probe to.

    Returns:
        A list of dictionaries, where each dictionary contains information
        about a discovered device, including its IP address. Returns an empty
        list if no devices are found or if an error occurs.
    """
    stream = discover_devices_stream(
        timeout=discovery_duration,
        response_port=response_port,
        discovery_port=discovery_port,
        broadcast_address=broadcast_address,
    )
    try:
        return [device async for device in stream]
    finally:
        # Release the sockets now rather than whenever the generator is collected.
        await stream.aclose()


async def discover_devices_stream(
    timeout: float = 3.0,
    response_port: int = DEFAULT_UDP_RESPONSE_PORT,
    discovery_port: int = DEFAULT_UDP_DISCOVERY_PORT,
    broadcast_address: str = BROADCAST_ADDRESS,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Discovers dLight devices on the local network using UDP broadcast, yielding results as they arrive.

    This function sends a broadcast UDP probe to the network and listens for
    responses from dLight devices, yielding each unique device as it is discovered
    until the timeout is reached.

    The sockets are released when the generator finishes or is closed. A caller
    that stops iterating early should close it (``contextlib.aclosing`` or
    ``await gen.aclose()``); otherwise ``response_port`` stays bound until the
    generator is garbage-collected.

    Args:
        timeout: The number of seconds to listen for responses before stopping.
        response_port: The local UDP port to listen on for responses.
        discovery_port: The UDP port dLight devices listen on for discovery probes.
        broadcast_address: The network broadcast address to send the probe to.

    Yields:
        A dictionary containing information about a discovered device,
        including its IP address.
    """
    loop = asyncio.get_running_loop()
    discovered_devices_set: Set[str] = set()
    queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    listen_transport: Optional[asyncio.DatagramTransport] = None
    listener: Optional[_DiscoveryProtocol] = None
    send_transport: Optional[asyncio.DatagramTransport] = None

    try:
        # 1. Create the listening endpoint
        listen_transport, listener = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(discovered_devices_set, queue=queue),
            local_addr=("0.0.0.0", response_port),
        )
        _LOGGER.debug(f"Listening for discovery responses on 0.0.0.0:{response_port}")

        # 2. Create a separate sending endpoint for broadcast
        send_transport, _ = await loop.create_datagram_endpoint(
            lambda: asyncio.DatagramProtocol(),  # Simple protocol for sending only
            remote_addr=(broadcast_address, discovery_port),
            allow_broadcast=True,  # Sets SO_BROADCAST on the socket
        )

        # 3. Send the broadcast probe
        _LOGGER.info(f"Sending discovery probe to {broadcast_address}:{discovery_port}")
        send_transport.sendto(UDP_DISCOVERY_PAYLOAD)

        # 4. Read from the queue until timeout is reached
        start_time = loop.time()
        while True:
            elapsed = loop.time() - start_time
            remaining = timeout - elapsed
            if remaining <= 0:
                break

            try:
                # Wait for next discovery item, up to remaining timeout
                device = await asyncio.wait_for(queue.get(), timeout=remaining)
                yield device
            except asyncio.TimeoutError:
                break

        # Yield any remaining devices that responded and were queued up but not yet yielded
        while not queue.empty():
            try:
                yield queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        _LOGGER.info(f"Discovery stream finished. Found {len(discovered_devices_set)} potential device(s).")

    except PermissionError as e:
        _LOGGER.error(
            f"Permission denied for UDP broadcast or binding to port {response_port}. "
            f"Try running with higher privileges if necessary. Error: {e}"
        )
    except OSError as e:
        _LOGGER.error(
            f"Network error during discovery (e.g., port {response_port} in use, "
            f"or cannot bind/broadcast on network): {e}"
        )
    except Exception as e:
        _LOGGER.exception(f"An unexpected error occurred during async discovery stream: {e}")
    finally:
        # Clean up transports
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
            if listener is not None:
                # close() frees response_port on a later loop iteration; wait for that so a
                # discovery started straight after this one can bind the port again.
                try:
                    await asyncio.wait_for(listener.closed, timeout=_LISTENER_CLOSE_TIMEOUT)
                except asyncio.TimeoutError:
                    _LOGGER.debug("Timed out waiting for the discovery listener socket to close.")
