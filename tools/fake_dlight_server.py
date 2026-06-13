#!/usr/bin/env python3
"""A standalone fake dLight device for integration testing (e.g. Home Assistant).

Speaks the real dLight wire protocol on the network, with persistent light
state, so anything using dlight-client (like the HA integration) can connect
to it as if it were a physical lamp:

- TCP command server (default port 3333): accepts bare-JSON commands and
  replies with 4-byte big-endian length-prefixed JSON.
- UDP discovery responder (default port 9478): answers the dLight discovery
  probe with device info sent back to the prober on port 9487.
- Control port (default TCP 3334): line-based runtime control for failure
  injection and out-of-band state changes, so you can make the "device"
  misbehave while a client is using it:

      echo "hang"          | nc 127.0.0.1 3334   # stop replying (client timeouts)
      echo "reset 3"       | nc 127.0.0.1 3334   # TCP RST the next 3 commands
      echo "drop"          | nc 127.0.0.1 3334   # close without replying
      echo "delay 2.5"     | nc 127.0.0.1 3334   # add latency to every response
      echo "normal"        | nc 127.0.0.1 3334   # clear all failure modes
      echo "brightness 30" | nc 127.0.0.1 3334   # change state behind the client's back
      echo "status"        | nc 127.0.0.1 3334   # JSON: modes + current lamp state

  `hang`/`reset`/`drop` take an optional count (apply to the next N commands,
  then revert to normal); without one they persist until `normal`.

Stdlib only — run it directly:

    python tools/fake_dlight_server.py --device-id fake-dlight-1 -v
"""

import argparse
import asyncio
import binascii
import json
import logging
import socket
import struct
import sys
from typing import Any, Dict, Optional, Tuple

DEFAULT_TCP_PORT = 3333
DEFAULT_CONTROL_PORT = 3334
DISCOVERY_PORT = 9478
DISCOVERY_RESPONSE_PORT = 9487
DISCOVERY_PROBE = binascii.unhexlify("476f6f676c654e50455f457269635f5761796e65")

_LOGGER = logging.getLogger("fake_dlight")


class FailureModes:
    """Runtime-switchable failure injection, shared by all connections.

    ``mode`` applies per received command; a counted mode reverts to normal
    after ``remaining`` commands. ``delay`` is orthogonal and applies to every
    successful response.
    """

    MODES = ("normal", "hang", "reset", "drop")

    def __init__(self):
        self.delay = 0.0
        self.mode = "normal"
        self.remaining: Optional[int] = None

    def set_mode(self, mode: str, count: Optional[int] = None) -> None:
        self.mode = mode
        self.remaining = count if mode != "normal" else None

    def take(self) -> str:
        """Returns the mode for the current command, consuming one count."""
        mode = self.mode
        if mode != "normal" and self.remaining is not None:
            self.remaining -= 1
            if self.remaining <= 0:
                self.set_mode("normal")
        return mode

    def describe(self) -> Dict[str, Any]:
        return {"mode": self.mode, "remaining": self.remaining, "delay": self.delay}


class FakeDLight:
    """A stateful emulated dLight lamp."""

    def __init__(self, device_id: str, model: str, sw_version: str, hw_version: str):
        self.device_id = device_id
        self.model = model
        self.sw_version = sw_version
        self.hw_version = hw_version
        self.state: Dict[str, Any] = {
            "on": False,
            "brightness": 100,
            "color": {"temperature": 4000},
        }

    @property
    def info(self) -> Dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "deviceModel": self.model,
            "swVersion": self.sw_version,
            "hwVersion": self.hw_version,
        }

    def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        command_type = command.get("commandType")
        response: Dict[str, Any] = {"status": "SUCCESS"}
        command_id = command.get("commandId")
        if command_id is not None:
            response["commandId"] = command_id

        if command_type == "QUERY_DEVICE_INFO":
            response.update(self.info)
        elif command_type == "QUERY_DEVICE_STATES":
            response["states"] = json.loads(json.dumps(self.state))  # deep copy
        elif command_type == "EXECUTE":
            for execution in command.get("commands", []):
                self._apply(execution)
            _LOGGER.info("State is now %s", self.state)
        else:
            _LOGGER.warning("Unknown commandType %r; replying SUCCESS anyway", command_type)
        return response

    def _apply(self, execution: Dict[str, Any]) -> None:
        if "on" in execution:
            self.state["on"] = bool(execution["on"])
        if "brightness" in execution:
            self.state["brightness"] = int(execution["brightness"])
        if "color" in execution and "temperature" in execution["color"]:
            self.state["color"]["temperature"] = int(execution["color"]["temperature"])


class _DiscoveryResponder(asyncio.DatagramProtocol):
    """Answers dLight UDP discovery probes with this device's info."""

    def __init__(self, device: FakeDLight):
        self.device = device
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        if data != DISCOVERY_PROBE:
            _LOGGER.debug("Ignoring non-probe datagram from %s: %r", addr, data)
            return
        _LOGGER.info("Discovery probe from %s; announcing %s", addr[0], self.device.device_id)
        payload = json.dumps(self.device.info).encode("utf-8")
        # Real devices answer to the fixed response port; also answer the
        # probe's source port in case a client listens there instead.
        self.transport.sendto(payload, (addr[0], DISCOVERY_RESPONSE_PORT))
        if addr[1] != DISCOVERY_RESPONSE_PORT:
            self.transport.sendto(payload, addr)


async def _handle_tcp(
    device: FakeDLight,
    failures: FailureModes,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
):
    peer = writer.get_extra_info("peername")
    _LOGGER.info("Connection from %s", peer)
    buf = bytearray()
    decoder = json.JSONDecoder()
    try:
        while True:
            # Commands arrive as bare JSON with no length prefix; decode
            # incrementally so back-to-back commands on one connection work.
            command = None
            while command is None:
                try:
                    text = bytes(buf).decode("utf-8")
                    command, end = decoder.raw_decode(text)
                    del buf[: len(text[:end].encode("utf-8"))]
                except (UnicodeDecodeError, json.JSONDecodeError):
                    chunk = await reader.read(4096)
                    if not chunk:
                        _LOGGER.info("Connection from %s closed", peer)
                        return
                    buf.extend(chunk)

            _LOGGER.info("<- %s", json.dumps(command))

            mode = failures.take()
            if mode == "hang":
                _LOGGER.info("(hang) not replying to %s; holding until client gives up", peer)
                # Swallow anything else the client sends; exit when it disconnects.
                while await reader.read(4096):
                    pass
                _LOGGER.info("Connection from %s closed (was hanging)", peer)
                return
            if mode == "reset":
                _LOGGER.info("(reset) sending TCP RST to %s", peer)
                sock = writer.get_extra_info("socket")
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                return
            if mode == "drop":
                _LOGGER.info("(drop) closing %s without replying", peer)
                return

            if failures.delay:
                _LOGGER.info("(delay) sleeping %.2fs before replying", failures.delay)
                await asyncio.sleep(failures.delay)

            response = device.handle_command(command)
            _LOGGER.info("-> %s", json.dumps(response))
            payload = json.dumps(response).encode("utf-8")
            writer.write(struct.pack(">I", len(payload)) + payload)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


def _control_command(device: FakeDLight, failures: FailureModes, line: str) -> str:
    parts = line.split()
    if not parts:
        return "error: empty command (try: help)"
    cmd, args = parts[0].lower(), parts[1:]

    try:
        if cmd == "status":
            return json.dumps({**failures.describe(), "state": device.state, "info": device.info})
        if cmd == "help":
            return (
                "commands: status | normal | hang [N] | reset [N] | drop [N] | "
                "delay SECONDS | on | off | brightness 0-100 | temperature KELVIN | help"
            )
        if cmd == "normal":
            failures.set_mode("normal")
            failures.delay = 0.0
            return "ok: all failure modes cleared"
        if cmd in ("hang", "reset", "drop"):
            count = int(args[0]) if args else None
            failures.set_mode(cmd, count)
            scope = f"next {count} command(s)" if count else "until 'normal'"
            return f"ok: {cmd} {scope}"
        if cmd == "delay":
            failures.delay = float(args[0])
            return f"ok: delay {failures.delay}s per response"
        if cmd in ("on", "off"):
            device.state["on"] = cmd == "on"
        elif cmd == "brightness":
            device.state["brightness"] = int(args[0])
        elif cmd == "temperature":
            device.state["color"]["temperature"] = int(args[0])
        else:
            return f"error: unknown command {cmd!r} (try: help)"
        _LOGGER.info("(control) state is now %s", device.state)
        return f"ok: state {json.dumps(device.state)}"
    except (IndexError, ValueError):
        return f"error: bad arguments for {cmd!r} (try: help)"


async def _handle_control(
    device: FakeDLight,
    failures: FailureModes,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
):
    try:
        while line := await reader.readline():
            reply = _control_command(device, failures, line.decode("utf-8", "replace").strip())
            _LOGGER.info("(control) %s -> %s", line.decode("utf-8", "replace").strip(), reply)
            writer.write((reply + "\n").encode("utf-8"))
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0", help="address to bind (default: all interfaces)")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    parser.add_argument("--control-port", type=int, default=DEFAULT_CONTROL_PORT)
    parser.add_argument("--device-id", default="fake-dlight-1")
    parser.add_argument("--model", default="dLight-Fake")
    parser.add_argument("--sw-version", default="1.0.0-fake")
    parser.add_argument("--hw-version", default="rev1")
    parser.add_argument("--no-discovery", action="store_true", help="disable the UDP discovery responder")
    parser.add_argument("--no-control", action="store_true", help="disable the runtime control port")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    device = FakeDLight(args.device_id, args.model, args.sw_version, args.hw_version)
    failures = FailureModes()

    server = await asyncio.start_server(
        lambda r, w: _handle_tcp(device, failures, r, w), args.host, args.tcp_port
    )
    _LOGGER.info("Fake dLight %r (TCP) listening on %s:%d", device.device_id, args.host, args.tcp_port)

    control_server = None
    if not args.no_control:
        control_server = await asyncio.start_server(
            lambda r, w: _handle_control(device, failures, r, w), args.host, args.control_port
        )
        _LOGGER.info("Control port (TCP) listening on %s:%d", args.host, args.control_port)

    transport = None
    if not args.no_discovery:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((args.host, DISCOVERY_PORT))
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _DiscoveryResponder(device), sock=sock
        )
        _LOGGER.info("Discovery responder (UDP) listening on %s:%d", args.host, DISCOVERY_PORT)

    try:
        async with server:
            await server.serve_forever()
    finally:
        if control_server is not None:
            control_server.close()
        if transport is not None:
            transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
