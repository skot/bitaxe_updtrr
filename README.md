# updtrr - Bitaxe Firmware and Web Interface Updater

A Python script to update ESP-Miner firmware and web interface files on multiple Bitaxe devices simultaneously.

## Features

- Updates multiple Bitaxe devices from a CSV file of IP addresses
- **Version checking** - Automatically detects if devices are already up to date
- Uploads ESP-Miner firmware via `/api/system/OTA` endpoint
- Uploads web interface files via `/api/system/OTAWWW` endpoint
- Comprehensive logging with both console and file output
- Configurable timeouts and delays
- Progress tracking and detailed error reporting
- Supports both simple IP list and CSV formats
- **Force update** option to update even if versions match

## Requirements

- Python 3.6+
- `requests` library

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Make the script executable (optional):
```bash
chmod +x updtrr.py
```

## Usage

### Basic Usage

```bash
python updtrr.py devices.csv esp-miner.bin www.bin
```

### Advanced Usage with Options

```bash
python updtrr.py --timeout 120 --device-delay 15 --upload-delay 10 devices.csv firmware.bin www.bin
```

### Command Line Arguments

- `csv_file`: Path to CSV file containing IP addresses (optional with `--discover`)
- `esp_miner_bin`: Path to the ESP-Miner firmware binary file (optional with `--save-discovered`)
- `www_bin`: Path to the web interface binary file (optional with `--save-discovered`)

### Optional Arguments

- `--timeout`: HTTP request timeout in seconds (default: 60)
- `--device-delay`: Delay between device updates in seconds (default: 10)
- `--upload-delay`: Delay between web interface and firmware uploads in seconds (default: 5)
- `--force`: Force update even if device firmware is already up to date
- `--check-versions`: Only check versions without updating devices
- `--discover`: Automatically discover Bitaxe devices on the network
- `--network`: Network CIDR to scan for discovery (e.g., 192.168.1.0/24)
- `--save-discovered`: Save discovered devices to CSV file (can be used without firmware files)
- `--scan-timeout`: Timeout for network scan in seconds (default: 60)

### Version Checking

The updater automatically checks if devices need updates by:

1. **Extracting version** from the firmware binary file
2. **Querying device** version via `/api/system/info` endpoint
3. **Comparing versions** using semantic versioning
4. **Skipping updates** if device is already up to date

Examples:
```bash
# Check versions without updating
python updtrr.py --check-versions devices.csv esp-miner.bin www.bin

# Force update even if versions match
python updtrr.py --force devices.csv esp-miner.bin www.bin
```

### Automatic Discovery

The updater can automatically discover Bitaxe devices on your network:

1. **Network scanning** using nmap to find devices with HTTP service
2. **Device verification** via API calls to confirm they are Bitaxe miners
3. **Automatic detection** of local network CIDR (usually /24)
4. **Detailed device information** including hostname, board version, device model, and ASIC model

Examples:
```bash
# Just discover and save devices (no firmware needed)
python updtrr.py --discover --save-discovered discovered_devices.csv

# Discover on specific network
python updtrr.py --discover --network 192.168.1.0/24 --save-discovered devices.csv

# Discover with extended timeout for large networks
python updtrr.py --discover --scan-timeout 120 --save-discovered devices.csv

# Discover and proceed with update
python updtrr.py --discover esp-miner.bin www.bin

# Discover, save, and update devices
python updtrr.py --discover --save-discovered devices.csv esp-miner.bin www.bin
```

**Requirements for Discovery:**
- `nmap` must be installed on your system
- Python package `python-nmap` (installed via requirements.txt)
- Network access to scan local subnet

**Note:** For large networks (e.g., /24 subnets with 254 hosts), you may need to increase the scan timeout using `--scan-timeout 120` or higher to avoid timeout errors.

### Enhanced CSV Output

When using `--save-discovered`, the script generates a detailed CSV file with comments for each discovered device:

```csv
# Discovered Bitaxe devices
# IP Address, Hostname, Board Version, Device Model, ASIC Model, Firmware Version
#
# bitaxe402 | 402 | Supra | BM1368 | v2.9.0
192.168.1.44
#
# bitaxeHydro601 | 601 | Gamma | BM1370 | v2.9.0
192.168.1.234
#
```

Each device entry includes:
- **Hostname**: Device network name
- **Board Version**: Hardware board revision
- **Device Model**: Bitaxe model (Ultra, Supra, Gamma, etc.)
- **ASIC Model**: Mining chip model (BM1366, BM1368, BM1370, etc.)
- **Firmware Version**: Current ESP-Miner version

You can quickly scan and inventory your Bitaxe devices without updating them using:
```bash
python updtrr.py --discover --save-discovered devices.csv
```

This discovery-only mode doesn't require firmware files and will exit after saving the device information.

## CSV File Format

The script supports two formats for the IP address file:

### Simple List Format
```
192.168.1.100
192.168.1.101
192.168.1.102
```

### CSV Format
```csv
IP,Device Name,Notes
192.168.1.100,Bitaxe-001,Main device
192.168.1.101,Bitaxe-002,Test device
192.168.1.102,Bitaxe-003,Spare device
```

**Note**: When using CSV format, only the first column (IP addresses) is used. Lines starting with `#` are treated as comments and ignored.

## Process Flow

For each device, the script:

1. **Uploads web interface** to `/api/system/OTAWWW`
2. **Waits** (configurable delay) 
3. **Uploads ESP-Miner firmware** to `/api/system/OTA`
4. **Waits** before proceeding to next device (configurable delay)

## Logging

The script provides detailed logging:

- **Console output**: Real-time progress and status updates
- **Log file**: Complete log saved to `updtrr.log`
- **Status indicators**: 
  - ✓ Success
  - ✗ Failure  
  - ⚠ Partial success

## Error Handling

The script handles various error conditions:

- **Network timeouts**: Configurable timeout for HTTP requests
- **Connection errors**: Device unreachable or network issues
- **Authorization errors**: HTTP 401 responses (device access restrictions)
- **File errors**: Missing or unreadable binary files
- **Invalid responses**: Non-200 HTTP status codes

## Examples

### Update 3 devices:
```bash
python updtrr.py my_devices.csv esp-miner-v2.1.0.bin www-v2.1.0.bin
```

### Update with longer timeouts for slow networks:
```bash
python updtrr.py --timeout 180 --device-delay 20 devices.csv firmware.bin web.bin
```

### Quick update with minimal delays:
```bash
python updtrr.py --device-delay 3 --upload-delay 2 devices.csv firmware.bin web.bin
```

## Exit Codes

- `0`: All devices updated successfully
- `1`: Some devices failed to update completely
- `130`: Interrupted by user (Ctrl+C)
- Other: Script error or all devices failed

## Troubleshooting

### Common Issues

1. **"Connection error"**: 
   - Verify device IP addresses are correct
   - Ensure devices are powered on and connected to network
   - Check network connectivity from script host

2. **"Unauthorized access"**:
   - Verify the script host is in the allowed network range for the devices
   - Check Bitaxe device network access settings

3. **"Timeout"**:
   - Increase timeout with `--timeout` option
   - Check network stability and speed
   - Verify devices are responsive

4. **"Invalid firmware file"**:
   - Ensure binary files exist and are readable
   - Verify file paths are correct
   - Check file permissions

### Log Analysis

Check `updtrr.log` for detailed information about:
- Which devices succeeded/failed
- Specific error messages
- Upload progress and timing
- File sizes and transfer details

## Security Notes

- The script sends binary data over HTTP (not HTTPS)
- Ensure you're on a trusted network when running updates
- Verify binary file integrity before running mass updates
- Consider testing on a single device before batch updates

## License

This tool is provided as-is for use with Bitaxe devices. Please ensure you have appropriate permissions before updating devices on your network.
