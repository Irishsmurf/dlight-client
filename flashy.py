import asyncio
import logging
from typing import Optional

# Assuming your client is importable like this:
from dlightclient import dlight

# Configure basic logging (optional, but helpful for debugging)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

async def flash_light_notification(
    client: dlight.AsyncDLightClient,
    target_ip: str,
    device_id: str,
    flashes: int = 3,          # Number of times to flash (on/off cycle)
    on_duration: float = 0.3,  # How long to stay ON during a flash (seconds)
    off_duration: float = 0.3, # How long to stay OFF during a flash (seconds)
) -> bool:
    """
    Flashes the dLight device on/off and restores its original state.

    Args:
        client: An initialized AsyncDLightClient instance.
        target_ip: IP address of the dLight device.
        device_id: Device ID of the dLight device.
        flashes: Number of times to flash (one flash = off then on).
        on_duration: Duration the light stays ON in each flash cycle.
        off_duration: Duration the light stays OFF in each flash cycle.

    Returns:
        True if the flashing sequence completed successfully, False otherwise.
    """
    original_state: Optional[dict] = None
    original_on: Optional[bool] = None
    original_brightness: Optional[int] = None
    original_temperature: Optional[int] = None
    success = False

    log.info(f"Starting flash sequence for {device_id} at {target_ip}")

    try:
        # 1. Get the current state to restore later
        log.debug("Querying original device state...")
        state_response = await client.query_device_state(target_ip, device_id)
        # The state is nested within the 'states' key based on dlight.py usage
        original_state = state_response.get('states')

        if original_state:
            original_on = original_state.get('on')
            original_brightness = original_state.get('brightness')
            original_temperature = original_state.get('color', {}).get('temperature')
            log.debug(f"Original state captured: on={original_on}, brightness={original_brightness}, temp={original_temperature}")
        else:
            # Handle case where state isn't returned as expected
            log.warning("Could not retrieve detailed original state. Will only restore ON/OFF status if possible.")
            # Attempt fallback by checking device info or assuming a default?
            # For now, we proceed but restoration might be incomplete.
            # Let's assume it might be off if state isn't detailed.
            original_on = False # Default assumption


        # 2. Perform the flashing sequence
        log.info(f"Flashing {flashes} times...")
        for i in range(flashes):
            log.debug(f"Flash {i+1}/{flashes}: Turning OFF")
            await client.set_light_state(target_ip, device_id, False)
            await asyncio.sleep(off_duration)

            log.debug(f"Flash {i+1}/{flashes}: Turning ON")
            await client.set_light_state(target_ip, device_id, True)
            await asyncio.sleep(on_duration)

        log.info("Flashing sequence complete.")
        success = True # Mark flashing as successful

    except dlight.DLightTimeoutError:
        log.error(f"Timeout during flash sequence for {device_id}.")
        # Restore might still be attempted in finally block
    except dlight.DLightResponseError as e:
         log.error(f"Device response error during flash sequence for {device_id}: {e}")
         # Restore might still be attempted
    except dlight.DLightError as e:
        log.error(f"A dLight error occurred during flashing for {device_id}: {e}")
        # Restore might still be attempted
    except Exception as e:
        log.exception(f"An unexpected error occurred during flashing for {device_id}")
        # Restore might still be attempted
    finally:
        # 3. Restore the original state (attempt even if flashing failed)
        if original_state is not None or original_on is not None: # Check if we have *any* state info
            log.info("Attempting to restore original state...")
            try:
                # Restore brightness and temperature first if they were set
                # Check if value is not None before attempting to set
                if original_brightness is not None:
                    log.debug(f"Restoring brightness to {original_brightness}")
                    await client.set_brightness(target_ip, device_id, original_brightness)
                    await asyncio.sleep(0.1) # Small delay between commands

                if original_temperature is not None:
                    log.debug(f"Restoring color temperature to {original_temperature}")
                    await client.set_color_temperature(target_ip, device_id, original_temperature)
                    await asyncio.sleep(0.1) # Small delay

                # Finally, set the original on/off state
                if original_on is not None:
                    log.debug(f"Restoring ON state to: {original_on}")
                    await client.set_light_state(target_ip, device_id, original_on)
                else:
                     log.warning("Original ON/OFF state unknown, leaving light ON after flash.")
                     await client.set_light_state(target_ip, device_id, True) # Default to ON if unknown

                log.info("Original state restoration attempted.")

            except dlight.DLightError as e:
                log.error(f"Error restoring original state for {device_id}: {e}")
                success = False # Mark overall operation as failed if restore fails
            except Exception as e:
                 log.exception(f"Unexpected error during state restoration for {device_id}")
                 success = False
        else:
             log.warning("No original state information was captured, cannot restore state.")
             # Might want to ensure light is left ON as a fallback?
             try:
                 await client.set_light_state(target_ip, device_id, True)
             except dlight.DLightError:
                 log.error("Failed to even turn light ON as a fallback after flashing.")
             success = False # Cannot guarantee original state

    return success

# --- Example Usage ---
async def example_main():
    # Replace with your actual device discovery or known details
    # Assumes you have discovered the device IP and ID beforehand
    discovered_ip = "192.168.0.69" # <-- Replace with actual IP
    discovered_id = "QvuTVFIw" # <-- Replace with actual Device ID

    if discovered_ip == "192.168.1.123" or discovered_id == "YOUR_DEVICE_ID":
        print("Please replace placeholder IP and Device ID in example_main()")
        return

    client = dlight.AsyncDLightClient()

    print(f"\n--- Attempting to flash {discovered_id} at {discovered_ip} ---")
    flash_successful = await flash_light_notification(
        client=client,
        target_ip=discovered_ip,
        device_id=discovered_id,
        flashes=4,          # Flash 4 times
        on_duration=0.005,    # On for 0.2s
        off_duration=0.005    # Off for 0.4s
    )

    if flash_successful:
        print("\nFlash notification sequence completed.")
    else:
        print("\nFlash notification sequence encountered errors.")

    # Add a small delay to observe the final state
    await asyncio.sleep(2)
    print("\n--- Checking state after flash sequence ---")
    try:
        final_state = await client.query_device_state(discovered_ip, discovered_id)
        print(f"Final state: {final_state.get('states')}")
    except DLightError as e:
        print(f"Could not query final state: {e}")


if __name__ == "__main__":
    # To run this example:
    # 1. Make sure dlightclient is installed or accessible in your PYTHONPATH.
    # 2. Replace the placeholder IP and Device ID in example_main().
    # 3. Run the script: python your_script_name.py
    try:
        asyncio.run(example_main())
    except KeyboardInterrupt:
        print("Example stopped.")
    except Exception as e:
         log.exception("Error running example main:")