#!/usr/bin/env python3
"""
updtrr - Bitaxe Firmware and Web Interface Updater

This script updates ESP-Miner firmware and web interface files on multiple Bitaxe devices
by reading IP addresses from a CSV file and sending the binary files via HTTP POST requests
to the respective OTA endpoints.

Usage:
    python updtrr.py <csv_file> <esp-miner.bin> <www.bin>

Arguments:
    csv_file: Path to CSV file containing IP addresses (one per line or in first column)
    esp-miner.bin: Path to the ESP-Miner firmware binary file
    www.bin: Path to the web interface binary file
"""

import sys
import csv
import requests
import argparse
import time
import re
import struct
import subprocess
import socket
import nmap
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import logging
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('updtrr.log')
    ]
)
logger = logging.getLogger(__name__)


class BitaxeUpdater:
    """Handles firmware and web interface updates for Bitaxe devices."""
    
    def __init__(self, timeout: int = 60):
        """
        Initialize the updater.
        
        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        # Set headers for binary uploads
        self.session.headers.update({
            'Content-Type': 'application/octet-stream'
        })
    
    def load_ip_addresses(self, csv_file: Path) -> List[str]:
        """
        Load IP addresses from CSV file.
        
        Args:
            csv_file: Path to the CSV file
            
        Returns:
            List of IP addresses
            
        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV file is empty or malformed
        """
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        
        ip_addresses = []
        
        try:
            with open(csv_file, 'r', newline='') as file:
                # Try to detect if it's a simple list (one IP per line) or CSV format
                content = file.read().strip()
                file.seek(0)
                
                # Check if it looks like a simple list (no commas)
                if ',' not in content:
                    for line_num, line in enumerate(file, 1):
                        line = line.strip()
                        if line and not line.startswith('#'):  # Skip empty lines and comments
                            ip_addresses.append(line)
                else:
                    # Parse as CSV, take first column
                    reader = csv.reader(file)
                    for row_num, row in enumerate(reader, 1):
                        if row and row[0].strip() and not row[0].strip().startswith('#'):
                            ip_addresses.append(row[0].strip())
                            
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
        
        if not ip_addresses:
            raise ValueError("No IP addresses found in CSV file")
        
        logger.info(f"Loaded {len(ip_addresses)} IP addresses from {csv_file}")
        return ip_addresses
    
    def validate_binary_file(self, bin_file: Path) -> None:
        """
        Validate that binary file exists and is readable.
        
        Args:
            bin_file: Path to binary file
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is empty or not readable
        """
        if not bin_file.exists():
            raise FileNotFoundError(f"Binary file not found: {bin_file}")
        
        if bin_file.stat().st_size == 0:
            raise ValueError(f"Binary file is empty: {bin_file}")
        
        try:
            with open(bin_file, 'rb') as f:
                f.read(1)  # Try to read one byte
        except Exception as e:
            raise ValueError(f"Cannot read binary file {bin_file}: {e}")
    
    def upload_with_progress(self, url: str, file_path: Path, description: str) -> requests.Response:
        """
        Upload a file with progress bar.
        
        Args:
            url: Upload URL
            file_path: Path to file to upload
            description: Description for progress bar
            
        Returns:
            requests.Response object
        """
        file_size = file_path.stat().st_size
        
        with open(file_path, 'rb') as f:
            # Create progress bar
            with tqdm(total=file_size, unit='B', unit_scale=True, 
                     desc=description, ascii=True, leave=False) as pbar:
                
                # Create a custom file-like object that updates progress
                class ProgressFileReader:
                    def __init__(self, file_obj, progress_bar):
                        self.file_obj = file_obj
                        self.progress_bar = progress_bar
                        self._total_read = 0
                    
                    def read(self, size=-1):
                        chunk = self.file_obj.read(size)
                        if chunk:
                            self.progress_bar.update(len(chunk))
                            self._total_read += len(chunk)
                        return chunk
                    
                    def __len__(self):
                        return file_size
                
                progress_reader = ProgressFileReader(f, pbar)
                
                # Upload with progress tracking
                response = self.session.post(
                    url,
                    data=progress_reader,
                    timeout=self.timeout
                )
                
                return response
    
    def upload_firmware(self, ip: str, firmware_file: Path) -> bool:
        """
        Upload ESP-Miner firmware to a device.
        
        Args:
            ip: Device IP address
            firmware_file: Path to ESP-Miner firmware binary
            
        Returns:
            True if successful, False otherwise
        """
        url = f"http://{ip}/api/system/OTA"
        
        try:
            file_size = firmware_file.stat().st_size
            logger.info(f"Uploading firmware to {ip} ({file_size} bytes)")
            
            response = self.upload_with_progress(
                url, 
                firmware_file, 
                f"FW {ip}"
            )
            
            if response.status_code == 200:
                logger.info(f"✓ Firmware upload successful to {ip}")
                return True
            elif response.status_code == 401:
                logger.error(f"✗ Unauthorized access to {ip} - check network permissions")
                return False
            else:
                logger.error(f"✗ Firmware upload failed to {ip}: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"✗ Timeout uploading firmware to {ip}")
            return False
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Connection error to {ip}")
            return False
        except Exception as e:
            logger.error(f"✗ Error uploading firmware to {ip}: {e}")
            return False
    
    def upload_web_interface(self, ip: str, www_file: Path) -> bool:
        """
        Upload web interface to a device.
        
        Args:
            ip: Device IP address
            www_file: Path to web interface binary
            
        Returns:
            True if successful, False otherwise
        """
        url = f"http://{ip}/api/system/OTAWWW"
        
        try:
            file_size = www_file.stat().st_size
            logger.info(f"Uploading web interface to {ip} ({file_size} bytes)")
            
            response = self.upload_with_progress(
                url, 
                www_file, 
                f"WWW {ip}"
            )
            
            if response.status_code == 200:
                logger.info(f"✓ Web interface upload successful to {ip}")
                return True
            elif response.status_code == 401:
                logger.error(f"✗ Unauthorized access to {ip} - check network permissions")
                return False
            else:
                logger.error(f"✗ Web interface upload failed to {ip}: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"✗ Timeout uploading web interface to {ip}")
            return False
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Connection error to {ip}")
            return False
        except Exception as e:
            logger.error(f"✗ Error uploading web interface to {ip}: {e}")
            return False
    
    def update_device(self, ip: str, firmware_file: Path, www_file: Path, delay: int = 5, force: bool = False) -> Tuple[bool, bool]:
        """
        Update both web interface and firmware on a device.
        
        Args:
            ip: Device IP address
            firmware_file: Path to ESP-Miner firmware binary
            www_file: Path to web interface binary
            delay: Delay between web interface and firmware upload (seconds)
            force: Force update even if versions match
            
        Returns:
            Tuple of (www_success, firmware_success)
        """
        logger.info(f"Starting update for device {ip}")
        
        # Check if firmware update is needed (unless forced)
        if not force:
            update_needed, status_msg = self.check_if_update_needed(ip, firmware_file)
            logger.info(f"Version check for {ip}: {status_msg}")
            
            if not update_needed:
                logger.info(f"Skipping {ip} - already up to date")
                return True, True  # Consider as success since no update needed
        
        # Upload web interface first
        www_success = self.upload_web_interface(ip, www_file)
        
        if www_success and delay > 0:
            logger.info(f"Waiting {delay} seconds before firmware upload...")
            time.sleep(delay)
        
        # Upload firmware second
        firmware_success = self.upload_firmware(ip, firmware_file)
        
        if firmware_success and www_success:
            logger.info(f"✓ Device {ip} updated successfully")
        else:
            logger.warning(f"⚠ Device {ip} partially updated (WWW: {'✓' if www_success else '✗'}, FW: {'✓' if firmware_success else '✗'})")
        
        return www_success, firmware_success
    
    def update_all_devices(self, ip_addresses: List[str], firmware_file: Path, www_file: Path, 
                          device_delay: int = 10, force: bool = False) -> dict:
        """
        Update all devices in the list.
        
        Args:
            ip_addresses: List of device IP addresses
            firmware_file: Path to ESP-Miner firmware binary
            www_file: Path to web interface binary
            device_delay: Delay between device updates (seconds)
            force: Force update even if versions match
            
        Returns:
            Dictionary with update results
        """
        results = {
            'total': len(ip_addresses),
            'firmware_success': 0,
            'www_success': 0,
            'both_success': 0,
            'failed': [],
            'up_to_date': 0
        }
        
        for i, ip in enumerate(ip_addresses, 1):
            logger.info(f"\n--- Updating device {i}/{len(ip_addresses)}: {ip} ---")
            
            www_success, firmware_success = self.update_device(ip, firmware_file, www_file, force=force)
            
            if firmware_success:
                results['firmware_success'] += 1
            if www_success:
                results['www_success'] += 1
            if firmware_success and www_success:
                results['both_success'] += 1
            if not firmware_success and not www_success:
                results['failed'].append(ip)
            
            # Delay between devices (except for the last one)
            if i < len(ip_addresses) and device_delay > 0:
                logger.info(f"Waiting {device_delay} seconds before next device...")
                time.sleep(device_delay)
        
        return results
    
    def get_device_version(self, ip: str) -> Optional[Dict[str, str]]:
        """
        Get version information from a device via API.
        
        Args:
            ip: Device IP address
            
        Returns:
            Dictionary containing version info or None if failed
        """
        try:
            response = self.session.get(
                f"http://{ip}/api/system/info",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                info = response.json()
                return {
                    'version': info.get('version', 'unknown'),
                    'axeOSVersion': info.get('axeOSVersion', 'unknown')
                }
            else:
                logger.warning(f"Failed to get version info from {ip}: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get version info from {ip}: {e}")
            return None
    
    def extract_version_from_binary(self, binary_file: Path) -> Optional[str]:
        """
        Extract version information from ESP-Miner firmware binary.
        
        Args:
            binary_file: Path to the firmware binary
            
        Returns:
            Version string or None if not found
        """
        try:
            with open(binary_file, 'rb') as f:
                data = f.read()
            
            # Look for version patterns in the binary
            # ESP-Miner typically embeds version strings in the binary
            version_patterns = [
                rb'v(\d+\.\d+\.\d+)',  # Standard version format
                rb'version[:\s]*(\d+\.\d+\.\d+)',  # Version with label
                rb'ESP-Miner[:\s]*v?(\d+\.\d+\.\d+)',  # ESP-Miner specific
                rb'FW[:\s]*v?(\d+\.\d+\.\d+)',  # Firmware version
                rb'(\d+\.\d+\.\d+)',  # Generic version pattern
            ]
            
            for pattern in version_patterns:
                matches = re.findall(pattern, data, re.IGNORECASE)
                if matches:
                    # Return the first match, decoded
                    version = matches[0].decode('utf-8', errors='ignore')
                    logger.info(f"Found version in {binary_file.name}: {version}")
                    return version
            
            logger.warning(f"No version information found in {binary_file.name}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting version from {binary_file}: {e}")
            return None
    
    def compare_versions(self, current_version: str, binary_version: str) -> bool:
        """
        Compare version strings to determine if update is needed.
        
        Args:
            current_version: Version currently running on device
            binary_version: Version in the binary file
            
        Returns:
            True if update is needed (binary version is newer), False otherwise
        """
        def parse_version(version_str: str) -> Tuple[int, int, int]:
            """Parse version string into tuple of integers."""
            # Remove 'v' prefix if present and extract numbers
            clean_version = re.sub(r'^v', '', version_str.strip())
            parts = re.findall(r'\d+', clean_version)
            
            if len(parts) >= 3:
                return (int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                return (int(parts[0]), int(parts[1]), 0)
            elif len(parts) == 1:
                return (int(parts[0]), 0, 0)
            else:
                return (0, 0, 0)
        
        try:
            current_tuple = parse_version(current_version)
            binary_tuple = parse_version(binary_version)
            
            logger.info(f"Version comparison: current={current_tuple} vs binary={binary_tuple}")
            
            # Return True if binary version is newer
            return binary_tuple > current_tuple
            
        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            # If we can't compare versions, assume update is needed
            return True
    
    def check_if_update_needed(self, ip: str, firmware_file: Path) -> Tuple[bool, str]:
        """
        Check if a device needs a firmware update.
        
        Args:
            ip: Device IP address
            firmware_file: Path to firmware binary
            
        Returns:
            Tuple of (update_needed, status_message)
        """
        # Get device version
        device_info = self.get_device_version(ip)
        if not device_info:
            return True, "Unable to get device version - proceeding with update"
        
        current_version = device_info.get('version', 'unknown')
        
        # Extract version from binary
        binary_version = self.extract_version_from_binary(firmware_file)
        if not binary_version:
            return True, f"Unable to extract binary version - proceeding with update (current: {current_version})"
        
        # Compare versions
        update_needed = self.compare_versions(current_version, binary_version)
        
        if update_needed:
            status_msg = f"Update needed: {current_version} -> {binary_version}"
        else:
            status_msg = f"Already up to date: {current_version} (binary: {binary_version})"
        
        return update_needed, status_msg
    
    def get_local_network_cidr(self) -> Optional[str]:
        """Get the local network CIDR for scanning."""
        try:
            # Get the default gateway
            if sys.platform == "darwin":  # macOS
                result = subprocess.run(['route', '-n', 'get', 'default'], 
                                      capture_output=True, text=True)
                gateway = None
                for line in result.stdout.split('\n'):
                    if 'gateway:' in line:
                        gateway = line.split(':')[1].strip()
                        break
            else:  # Linux
                result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                      capture_output=True, text=True)
                gateway = None
                for line in result.stdout.split('\n'):
                    if 'default via' in line:
                        gateway = line.split()[2]
                        break
            
            if not gateway:
                logger.warning("Could not determine default gateway")
                return None
                
            # Convert gateway to network CIDR (assume /24)
            network_parts = gateway.split('.')
            if len(network_parts) == 4:
                network_cidr = f"{network_parts[0]}.{network_parts[1]}.{network_parts[2]}.0/24"
                logger.info(f"Detected local network: {network_cidr}")
                return network_cidr
            else:
                logger.warning(f"Invalid gateway format: {gateway}")
                return None
                
        except Exception as e:
            logger.error(f"Error detecting local network: {e}")
            return None
    
    def scan_for_bitaxes(self, network_cidr: str = None, timeout: int = 60) -> List[str]:
        """
        Scan the local network for Bitaxe devices.
        
        Args:
            network_cidr: Network CIDR to scan (e.g., "192.168.1.0/24")
            timeout: Timeout for network scan in seconds
            
        Returns:
            List of IP addresses of discovered Bitaxe devices
        """
        logger.info("🔍 Scanning local network for Bitaxe devices...")
        
        if not network_cidr:
            network_cidr = self.get_local_network_cidr()
            if not network_cidr:
                logger.error("Could not determine network to scan")
                return []
        
        logger.info(f"Scanning network: {network_cidr} (timeout: {timeout}s)")
        
        try:
            # Initialize nmap scanner
            nm = nmap.PortScanner()
            
            # Scan for devices with port 80 open (web interface)
            # Use optimized arguments for faster scanning
            logger.info("Scanning for devices with HTTP service on port 80...")
            scan_args = f"-T4 --host-timeout {timeout}s --open"
            scan_result = nm.scan(network_cidr, '80', arguments=scan_args)
            
            potential_bitaxes = []
            
            # Check each host with port 80 open
            for host in nm.all_hosts():
                if nm[host].state() == 'up':
                    tcp_ports = nm[host]['tcp'] if 'tcp' in nm[host] else {}
                    if 80 in tcp_ports and tcp_ports[80]['state'] == 'open':
                        potential_bitaxes.append(host)
            
            logger.info(f"Found {len(potential_bitaxes)} devices with HTTP service")
            
            if not potential_bitaxes:
                logger.info("No devices with HTTP service found")
                return []
            
            # Verify each potential device is actually a Bitaxe
            verified_bitaxes = []
            
            logger.info("Verifying devices are Bitaxe miners...")
            for ip in potential_bitaxes:
                if self.verify_bitaxe_device(ip):
                    verified_bitaxes.append(ip)
                    logger.info(f"✓ Verified Bitaxe at {ip}")
                else:
                    logger.debug(f"✗ Not a Bitaxe: {ip}")
            
            logger.info(f"🎯 Found {len(verified_bitaxes)} Bitaxe devices")
            
            return verified_bitaxes
            
        except Exception as e:
            logger.error(f"Error scanning network: {e}")
            return []
    
    def verify_bitaxe_device(self, ip: str) -> bool:
        """
        Verify that a device is actually a Bitaxe by checking its API.
        
        Args:
            ip: IP address to check
            
        Returns:
            True if device is a Bitaxe, False otherwise
        """
        try:
            # Try to get system info from the device
            response = self.session.get(
                f"http://{ip}/api/system/info",
                timeout=5  # Short timeout for discovery
            )
            
            if response.status_code == 200:
                info = response.json()
                
                # Check for Bitaxe-specific fields
                bitaxe_indicators = [
                    'version',        # ESP-Miner version
                    'asicModel',      # ASIC model (BM1366, BM1368, etc.)
                    'boardVersion',   # Board version
                    'chipTemp',       # Chip temperature
                    'hashRate',       # Hash rate
                    'power',          # Power consumption
                ]
                
                # Check if device has Bitaxe-specific fields
                found_indicators = sum(1 for field in bitaxe_indicators if field in info)
                
                if found_indicators >= 3:  # Must have at least 3 indicators
                    # Additional check: look for known ASIC models
                    asic_model = info.get('asicModel', '').upper()
                    known_asics = ['BM1366', 'BM1368', 'BM1370', 'BM1397']
                    
                    if asic_model in known_asics:
                        logger.debug(f"Verified Bitaxe at {ip}: {asic_model}")
                        return True
                    elif found_indicators >= 4:  # High confidence even without ASIC model
                        logger.debug(f"Likely Bitaxe at {ip}: {found_indicators} indicators")
                        return True
                
                logger.debug(f"Device at {ip} has {found_indicators} indicators, not a Bitaxe")
                return False
            else:
                logger.debug(f"Device at {ip} returned HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.debug(f"Error verifying device at {ip}: {e}")
            return False
    
    def auto_discover_bitaxes(self, network_cidr: str = None, scan_timeout: int = 60) -> List[str]:
        """
        Automatically discover Bitaxe devices on the local network.
        
        Args:
            network_cidr: Network CIDR to scan (auto-detected if not provided)
            scan_timeout: Timeout for network scan in seconds
            
        Returns:
            List of discovered Bitaxe IP addresses
        """
        logger.info("🚀 Starting automatic Bitaxe discovery...")
        
        bitaxes = self.scan_for_bitaxes(network_cidr, scan_timeout)
        
        if bitaxes:
            logger.info(f"✅ Discovery complete! Found {len(bitaxes)} Bitaxe devices:")
            for ip in bitaxes:
                logger.info(f"  - {ip}")
        else:
            logger.warning("❌ No Bitaxe devices found on the network")
            
        return bitaxes


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Update ESP-Miner firmware and web interface on multiple Bitaxe devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python updtrr.py devices.csv esp-miner.bin www.bin
  python updtrr.py --timeout 120 --device-delay 15 devices.csv firmware.bin web.bin
  python updtrr.py --discover --network 192.168.1.0/24 esp-miner.bin www.bin
  python updtrr.py --check-versions devices.csv esp-miner.bin www.bin
        """
    )
    
    parser.add_argument('csv_file', type=Path, nargs='?', help='CSV file containing IP addresses (optional with --discover)')
    parser.add_argument('esp_miner_bin', type=Path, help='ESP-Miner firmware binary file')
    parser.add_argument('www_bin', type=Path, help='Web interface binary file')
    parser.add_argument('--timeout', type=int, default=60, 
                       help='HTTP request timeout in seconds (default: 60)')
    parser.add_argument('--device-delay', type=int, default=10,
                       help='Delay between device updates in seconds (default: 10)')
    parser.add_argument('--upload-delay', type=int, default=5,
                       help='Delay between web interface and firmware uploads in seconds (default: 5)')
    parser.add_argument('--force', action='store_true',
                       help='Force update even if device firmware is already up to date')
    parser.add_argument('--check-versions', action='store_true',
                       help='Only check versions without updating devices')
    parser.add_argument('--discover', action='store_true',
                       help='Automatically discover Bitaxe devices on the network')
    parser.add_argument('--network', type=str,
                       help='Network CIDR to scan for discovery (e.g., 192.168.1.0/24)')
    parser.add_argument('--save-discovered', type=Path,
                       help='Save discovered devices to CSV file')
    parser.add_argument('--scan-timeout', type=int, default=60,
                       help='Timeout for network scan in seconds (default: 60)')
    
    args = parser.parse_args()
    
    try:
        # Initialize updater
        updater = BitaxeUpdater(timeout=args.timeout)
        
        # Validate input files
        logger.info("Validating input files...")
        updater.validate_binary_file(args.esp_miner_bin)
        updater.validate_binary_file(args.www_bin)
        
        # Handle discovery mode
        if args.discover:
            logger.info("🔍 Discovery mode enabled")
            ip_addresses = updater.auto_discover_bitaxes(args.network, args.scan_timeout)
            
            if not ip_addresses:
                logger.error("No Bitaxe devices discovered")
                sys.exit(1)
            
            # Save discovered devices if requested
            if args.save_discovered:
                logger.info(f"Saving discovered devices to {args.save_discovered}")
                with open(args.save_discovered, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['# Discovered Bitaxe devices'])
                    for ip in ip_addresses:
                        writer.writerow([ip])
                logger.info(f"✓ Saved {len(ip_addresses)} devices to {args.save_discovered}")
        else:
            # Load IP addresses from CSV file
            if not args.csv_file:
                logger.error("CSV file is required unless using --discover")
                sys.exit(1)
            ip_addresses = updater.load_ip_addresses(args.csv_file)
        
        # Check if we're only checking versions
        if args.check_versions:
            logger.info(f"\nChecking versions for {len(ip_addresses)} devices...")
            binary_version = updater.extract_version_from_binary(args.esp_miner_bin)
            if binary_version:
                logger.info(f"Binary version: {binary_version}")
            else:
                logger.warning("Could not extract version from binary")
            
            for ip in ip_addresses:
                update_needed, status_msg = updater.check_if_update_needed(ip, args.esp_miner_bin)
                logger.info(f"{ip}: {status_msg}")
            
            return
        
        # Start updates
        logger.info(f"\nStarting updates for {len(ip_addresses)} devices...")
        logger.info(f"Firmware file: {args.esp_miner_bin} ({args.esp_miner_bin.stat().st_size} bytes)")
        logger.info(f"Web interface file: {args.www_bin} ({args.www_bin.stat().st_size} bytes)")
        
        if args.force:
            logger.info("Force update enabled - will update all devices regardless of version")
        
        # Extract binary version for logging
        binary_version = updater.extract_version_from_binary(args.esp_miner_bin)
        if binary_version:
            logger.info(f"Binary version: {binary_version}")
        
        # Modify the update_device call to use the upload delay
        original_update_device = updater.update_device
        def update_device_with_delay(ip, fw_file, www_file):
            return original_update_device(ip, fw_file, www_file, delay=args.upload_delay, force=args.force)
        updater.update_device = update_device_with_delay
        
        # Update all devices
        results = updater.update_all_devices(ip_addresses, args.esp_miner_bin, args.www_bin, 
                                           device_delay=args.device_delay, force=args.force)
        
        # Print summary
        logger.info(f"\n{'='*50}")
        logger.info("UPDATE SUMMARY")
        logger.info(f"{'='*50}")
        logger.info(f"Total devices: {results['total']}")
        logger.info(f"Firmware uploads successful: {results['firmware_success']}")
        logger.info(f"Web interface uploads successful: {results['www_success']}")
        logger.info(f"Both uploads successful: {results['both_success']}")
        logger.info(f"Up to date (skipped): {results.get('up_to_date', 0)}")
        logger.info(f"Failed: {len(results['failed'])}")
        
        if results['failed']:
            logger.info(f"Failed devices: {', '.join(results['failed'])}")
        
        # Exit with appropriate code
        if results['both_success'] == results['total']:
            logger.info("✓ All devices updated successfully!")
            sys.exit(0)
        elif results['both_success'] > 0:
            logger.warning("⚠ Some devices updated successfully, others failed")
            sys.exit(1)
        else:
            logger.error("✗ All device updates failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\nUpdate interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
