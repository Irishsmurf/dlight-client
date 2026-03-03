# Issue DL-002: Granular CLI Subcommands

## Description
The current CLI (`cli.py`) is primarily an example runner that executes a fixed "interaction sequence." It lacks the ability for users to perform specific, individual actions from the command line.

## Reasoning
- **Scriptability**: Users should be able to incorporate dLight control into shell scripts or cron jobs (e.g., `dlight-client --id <ID> --ip <IP> turn-off`).
- **Utility**: Provides a quick way for users to control their lights without needing to write Python code.
- **Parity**: Brings the CLI in line with other standard IoT control tools.

## Proposed Implementation
- Refactor argument parsing to use subcommands (e.g., `discover`, `on`, `off`, `brightness`, `color-temp`).
- Ensure each subcommand supports targeting by IP/ID.
- Maintain backward compatibility for the existing `--discover` and interaction flags where possible.
