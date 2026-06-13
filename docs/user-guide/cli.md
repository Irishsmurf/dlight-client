# CLI Reference

dlight-client ships a command-line tool for quick discovery and device interaction. It's useful for scripting, debugging, and initial setup.

## Invocation

```bash
python -m dlightclient.cli [options]
```

If you install dlight-client with the `dlight` entry point (available from v1.7.0):

```bash
dlight [options]
```

## Options

| Flag | Description |
|---|---|
| `--discover` | Scan the network and print all discovered lamps. |
| `--discover-duration SECS` | How long to listen for responses (default: `3.0`). |
| `--first` | Combined with `--discover`, interact with the first lamp found. |
| `--ip IP` | Target a specific lamp by IP address. |
| `--id ID` | Device ID of the target lamp. |
| `--connect-wifi` | Send Wi-Fi credentials to a lamp in SoftAP mode. |
| `--ssid SSID` | Wi-Fi network name (used with `--connect-wifi`). |
| `--password PASS` | Wi-Fi password (used with `--connect-wifi`). |
| `--timeout SECS` | Command timeout in seconds (default: `5.0`). |
| `--ssl` | Enable TLS using the system CA store. |
| `--insecure` | Enable TLS but skip certificate verification (testing only). |
| `-v` | Verbose logging (INFO level). |
| `-vv` | Very verbose logging (DEBUG level). |

## Examples

**Discover all lamps on the network:**

```bash
python -m dlightclient.cli --discover
```

**Discover with a longer window and interact with the first lamp:**

```bash
python -m dlightclient.cli --discover --discover-duration 5 --first
```

**Run the demo interaction sequence on a known lamp:**

```bash
python -m dlightclient.cli --ip 192.168.1.123 --id DL12345
```

**Provision a factory-reset lamp with Wi-Fi credentials:**

```bash
python -m dlightclient.cli --connect-wifi --id DL12345 --ssid MyNetwork --password s3cret
```

**Debug a connection problem:**

```bash
python -m dlightclient.cli --ip 192.168.1.123 --id DL12345 --timeout 10 -vv
```

!!! info "Granular subcommands coming in DL-002"
    Individual subcommands (`on`, `off`, `brightness`, `color-temp`) are planned — see the [Roadmap](../roadmap.md). The current CLI runs a fixed interaction sequence that demonstrates all major features.
