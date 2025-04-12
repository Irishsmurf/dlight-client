# dlightclient/cli.py
"""Command-line interface / Example usage script for dlightclient."""

import asyncio
import logging
import argparse
import time # For sleep in example sequence

# Import the public interface from the package's __init__
from . import (
    AsyncDLightClient,
    DLightDevice, # <-- Import DLightDevice
    discover_devices,
    DLightError,
    DLightTimeoutError,
    DLightConnectionError,
    DLightResponseError,
    DLightCommandError,
)
# Import constants if needed directly (e.g., for FACTORY_RESET_IP in wifi connect)
from . import constants

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
        devices_info = await discover_devices(discovery_duration=duration)
        if not devices_info:
            log.warning("\nNo dLight devices found on the network.")
            log.warning("Ensure dLight is powered on and connected to the same network.")
            log.warning("Firewall rules might also block UDP broadcast/responses.")
        else:
            log.info(f"\n--- Discovered {len(devices_info)} Device(s) ---")
            for i, device_info in enumerate(devices_info):
                ip = device_info.get('ip_address', 'N/A')
                dev_id = device_info.get('deviceId', device_info.get('deviceid', 'N/A')) # Handle case variations
                model = device_info.get('deviceModel', 'N/A')
                print(f"  Device {i+1}: ID={dev_id}, IP={ip}, Model={model}")
                log.debug(f"  Full info Device {i+1}: {device_info}")
        return devices_info # Return the list of dicts
    except Exception as e:
         log.exception(f"Discovery failed with an unexpected error: {e}")
         return []


async def run_interaction(client: AsyncDLightClient, target_ip: str, device_id: str):
    """
    Runs a sequence of interactions with a specific device using DLightDevice.
    """
    log.info(f"\n--- Interacting with: {device_id} at {target_ip} using DLightDevice ---")

    # Create a DLightDevice instance
    device = DLightDevice(ip_address=target_ip, device_id=device_id, client=client)
    print(f"Created device object: {device}") # Uses __str__

    try:
        print("\nQuerying Device Info...")
        info = await device.get_info() # Use device method
        print(f"  Info Response: {info}")
        # Info might be directly in the response payload, not nested
        log.info(f"  Device Info: Model={info.get('deviceModel')}, SW={info.get('swVersion')}, HW={info.get('hwVersion')}")

        print("\nQuerying Device State...")
        current_state = await device.get_state() # Use device method
        print(f"  State Response: {current_state}") # Already extracted 'states' dict
        log.info(f"  Current State: {current_state}")

        print("\nTurning Light ON...")
        await device.turn_on() # Use device method
        await asyncio.sleep(0.5)

        print("\nSetting Brightness to 30%...")
        await device.set_brightness(30) # Use device method
        await asyncio.sleep(0.5)

        print("\nSetting Color Temperature to 5000K...")
        await device.set_color_temperature(5000) # Use device method
        await asyncio.sleep(0.5)

        print("\nQuerying Device State Again...")
        new_state = await device.get_state() # Use device method
        print(f"  New State Response: {new_state}")
        log.info(f"  New State: {new_state}")

        print("\nFlashing light for notification...")
        flash_ok = await device.flash(flashes=2, on_duration=0.2, off_duration=0.2)
        if flash_ok:
            log.info("Flash completed successfully.")
        else:
            log.warning("Flash sequence encountered issues (check logs).")
        await asyncio.sleep(1.0) # Wait after flash to observe restored state

        print("\nTurning Light OFF...")
        await device.turn_off() # Use device method
        log.info("Interaction sequence complete.")

    except (DLightTimeoutError, DLightConnectionError) as e:
        log.error(f"\n--- Network Error during interaction with {device.id} ---")
        log.error(e)
    except (DLightResponseError, DLightCommandError) as e:
        log.error(f"\n--- Device Command/Response Error during interaction with {device.id} ---")
        log.error(e)
    except DLightError as e:
        log.error(f"\n--- A dLight error occurred during interaction with {device.id} ---")
        log.error(e)
    except ValueError as e:
         log.error(f"\n--- Invalid value provided during interaction with {device.id} ---")
         log.error(e)
    except Exception as e:
         log.exception(f"Unexpected error during interaction example with {device.id}")


async def run_wifi_connect(client: AsyncDLightClient, device_id: str, ssid: str, password: str):
    """Attempts to send Wi-Fi credentials to a device (assumed in SoftAP mode)."""
    log.info(f"\n--- Attempting Wi-Fi Connection for {device_id} ---")
    log.warning("Ensure you are connected to the device's SoftAP network.")
    # Access constant via imported constants module
    log.warning(f"Targeting default SoftAP IP: {constants.FACTORY_RESET_IP}")
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
        '--first', action='store_true',
        help="Automatically interact with the first discovered device (use with --discover)."
    )
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase logging verbosity (-v for INFO, -vv for DEBUG)."
    )

    args = parser.parse_args()

    # Adjust logging level based on verbosity
    # Set library logger level (covers client, discovery, device)
    lib_logger = logging.getLogger('dlightclient')
    if args.verbose == 1:
        lib_logger.setLevel(logging.INFO)
        log.setLevel(logging.INFO) # Set script level
    elif args.verbose >= 2:
        lib_logger.setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG) # Set script level
        log.info("Debug logging enabled.")
    else:
        lib_logger.setLevel(logging.WARNING) # Default library level if not verbose


    # --- Execute requested action ---
    client = AsyncDLightClient(default_timeout=args.timeout)
    discovered_devices_info = [] # Store discovery results if needed

    if args.discover:
        discovered_devices_info = await run_discovery(args.discover_duration)
        # If --first is specified, proceed to interact
        if args.first and discovered_devices_info:
            first_device_info = discovered_devices_info[0]
            target_ip = first_device_info.get('ip_address')
            target_id = first_device_info.get('deviceId') or first_device_info.get('deviceid')
            if target_ip and target_id:
                await run_interaction(client, target_ip, target_id)
            else:
                log.error("Could not extract IP and ID from the first discovered device.")
        elif args.first:
            log.warning("Discovery ran with --first, but no devices were found.")

    elif args.connect_wifi:
        if not all([args.device_id, args.ssid, args.password]):
            parser.error("--connect-wifi requires --id, --ssid, and --password.")
        else:
            await run_wifi_connect(client, args.device_id, args.ssid, args.password)

    elif args.ip and args.device_id:
        # Interact with explicitly specified device
        await run_interaction(client, args.ip, args.device_id)

    elif args.ip or args.device_id:
         # User provided one but not both for interaction
         parser.error("Both --ip and --id are required for interaction (unless using --discover --first).")

    else:
        # No specific action requested other than potentially setting verbosity
        log.info("No action specified (or discovery ran without --first). Use --discover, --connect-wifi, or provide --ip and --id.")
        log.info("Run with -h or --help for usage details.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    # Catching general Exception here can hide specific issues handled in main()
    # Consider letting main handle its specific errors unless there's setup/teardown needed here.

