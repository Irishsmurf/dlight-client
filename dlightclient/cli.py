# dlightclient/cli.py
"""Command-line interface / Example usage script for dlightclient."""

import asyncio
import logging
import argparse
import time # For sleep in example sequence

# Import the public interface from the package's __init__
from . import (
    AsyncDLightClient,
    discover_devices,
    DLightError,
    DLightTimeoutError,
    DLightConnectionError,
    DLightResponseError,
    DLightCommandError,
)

# Configure logging for the example script
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__) # Use __name__ for the script's logger


async def run_discovery(duration: float):
    """Runs the discovery process and prints results."""
    log.info(f"\n--- Discovering Devices ({duration} seconds) ---")
    try:
        devices = await discover_devices(discovery_duration=duration)
        if not devices:
            log.warning("\nNo dLight devices found on the network.")
            log.warning("Ensure dLight is powered on and connected to the same network.")
            log.warning("Firewall rules might also block UDP broadcast/responses.")
        else:
            log.info(f"\n--- Discovered {len(devices)} Device(s) ---")
            for i, device in enumerate(devices):
                ip = device.get('ip_address', 'N/A')
                dev_id = device.get('deviceId', device.get('deviceid', 'N/A')) # Handle case variations
                model = device.get('deviceModel', 'N/A')
                print(f"  Device {i+1}: ID={dev_id}, IP={ip}, Model={model}")
                log.debug(f"  Full info Device {i+1}: {device}")
        return devices
    except Exception as e:
         log.exception(f"Discovery failed with an unexpected error: {e}")
         return []


async def run_interaction(client: AsyncDLightClient, target_ip: str, device_id: str):
    """Runs a sequence of interactions with a specific device."""
    log.info(f"\n--- Interacting with: {device_id} at {target_ip} ---")
    try:
        print("\nQuerying Device Info...")
        info = await client.query_device_info(target_ip, device_id)
        print(f"  Info Response: {info}")
        log.info(f"  Device Info: Model={info.get('deviceModel')}, SW={info.get('swVersion')}, HW={info.get('hwVersion')}")

        print("\nQuerying Device State...")
        state_resp = await client.query_device_state(target_ip, device_id)
        print(f"  State Response: {state_resp}")
        current_state = state_resp.get('states', {})
        log.info(f"  Current State: {current_state}")

        print("\nTurning Light ON...")
        await client.set_light_state(target_ip, device_id, True)
        await asyncio.sleep(0.5)

        print("\nSetting Brightness to 30%...")
        await client.set_brightness(target_ip, device_id, 30)
        await asyncio.sleep(0.5)

        print("\nSetting Color Temperature to 5000K...")
        await client.set_color_temperature(target_ip, device_id, 5000)
        await asyncio.sleep(0.5)

        print("\nQuerying Device State Again...")
        state_resp = await client.query_device_state(target_ip, device_id)
        print(f"  New State Response: {state_resp}")
        new_state = state_resp.get('states', {})
        log.info(f"  New State: {new_state}")

        print("\nTurning Light OFF...")
        await client.set_light_state(target_ip, device_id, False)
        log.info("Interaction sequence complete.")

    except (DLightTimeoutError, DLightConnectionError) as e:
        log.error(f"\n--- Network Error during interaction ---")
        log.error(e)
    except (DLightResponseError, DLightCommandError) as e:
        log.error(f"\n--- Device Command/Response Error during interaction ---")
        log.error(e)
    except DLightError as e:
        log.error(f"\n--- A dLight error occurred during interaction ---")
        log.error(e)
    except ValueError as e:
         log.error(f"\n--- Invalid value provided during interaction ---")
         log.error(e)
    except Exception as e:
         log.exception("Unexpected error during interaction example")


async def run_wifi_connect(client: AsyncDLightClient, device_id: str, ssid: str, password: str):
    """Attempts to send Wi-Fi credentials to a device (assumed in SoftAP mode)."""
    log.info(f"\n--- Attempting Wi-Fi Connection for {device_id} ---")
    log.warning("Ensure you are connected to the device's SoftAP network.")
    log.warning(f"Targeting default SoftAP IP: {client.FACTORY_RESET_IP}") # Access constant via client instance or import
    try:
        # Use the specific method from the client
        wifi_resp = await client.connect_to_wifi(device_id, ssid, password)
        log.info(f"Wi-Fi connect command sent. Response: {wifi_resp}")
        log.info("Device should now attempt to connect to your Wi-Fi.")
        log.info("Wait a minute and then try discovery again on your main network.")
    except DLightCommandError as e:
         # Catch the specific error wrapper from connect_to_wifi
         log.error(f"Failed to send Wi-Fi connect command: {e}")
    except DLightError as e:
         log.error(f"A dLight error occurred during Wi-Fi connect attempt: {e}")
    except Exception as e:
         log.exception("Unexpected error during Wi-Fi connect attempt")


async def main():
    """Main entry point for the CLI/example script."""
    parser = argparse.ArgumentParser(description="dLight Client CLI / Example Runner")
    parser.add_argument(
        '--discover', action='store_true',
        help="Discover dLight devices on the network."
    )
    parser.add_argument(
        '--discover-duration', type=float, default=3.0,
        help="Duration (seconds) to listen for discovery responses."
    )
    parser.add_argument(
        '--ip', type=str, default=None,
        help="IP address of the target dLight device for interaction."
    )
    parser.add_argument(
        '--id', type=str, default=None, dest='device_id', # Use dest for clarity
        help="Device ID of the target dLight device for interaction."
    )
    parser.add_argument(
        '--timeout', type=float, default=5.0,
        help="Network timeout (seconds) for TCP commands."
    )
    parser.add_argument(
        '--connect-wifi', action='store_true',
        help="Attempt to send Wi-Fi credentials (requires --id, --ssid, --password)."
    )
    parser.add_argument(
        '--ssid', type=str, default=None,
        help="Target Wi-Fi SSID for --connect-wifi."
    )
    parser.add_argument(
        '--password', type=str, default=None,
        help="Target Wi-Fi password for --connect-wifi."
    )
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase logging verbosity (-v for INFO, -vv for DEBUG)."
    )

    args = parser.parse_args()

    # Adjust logging level based on verbosity
    if args.verbose == 1:
        logging.getLogger('dlightclient').setLevel(logging.INFO) # Set library level
        log.setLevel(logging.INFO) # Set script level
    elif args.verbose >= 2:
        logging.getLogger('dlightclient').setLevel(logging.DEBUG) # Set library level
        log.setLevel(logging.DEBUG) # Set script level
        log.info("Debug logging enabled.")

    # --- Execute requested action ---
    client = AsyncDLightClient(default_timeout=args.timeout)

    if args.discover:
        await run_discovery(args.discover_duration)

    elif args.connect_wifi:
        if not all([args.device_id, args.ssid, args.password]):
            parser.error("--connect-wifi requires --id, --ssid, and --password.")
        else:
            await run_wifi_connect(client, args.device_id, args.ssid, args.password)

    elif args.ip and args.device_id:
        await run_interaction(client, args.ip, args.device_id)

    elif args.ip or args.device_id:
         parser.error("Both --ip and --id are required for interaction.")

    else:
        log.info("No action specified. Use --discover, --connect-wifi, or provide --ip and --id.")
        log.info("Run with -h or --help for usage details.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    # Catching general Exception here can hide specific issues handled in main()
    # Consider letting main handle its specific errors unless there's setup/teardown needed here.

