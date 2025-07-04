#!/usr/bin/env python3
"""
Test script for Bitaxe discovery functionality.
"""

import sys
import requests
import logging
from pathlib import Path
from updtrr import BitaxeUpdater

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_single_device_verification():
    """Test verifying a known Bitaxe device."""
    print("🧪 Testing Bitaxe Device Verification")
    print("=" * 50)
    
    updater = BitaxeUpdater()
    
    # Test with known Bitaxe IP
    test_ip = "192.168.1.45"
    
    print(f"Testing device verification for {test_ip}...")
    
    # Test device version retrieval
    version_info = updater.get_device_version(test_ip)
    if version_info:
        print(f"✅ Device info retrieved:")
        print(f"  - Firmware version: {version_info.get('version', 'unknown')}")
        print(f"  - AxeOS version: {version_info.get('axeOSVersion', 'unknown')}")
    else:
        print(f"❌ Could not retrieve device info")
        return False
    
    # Test Bitaxe verification
    is_bitaxe = updater.verify_bitaxe_device(test_ip)
    if is_bitaxe:
        print(f"✅ Device verified as Bitaxe")
    else:
        print(f"❌ Device not recognized as Bitaxe")
        return False
    
    return True

def test_network_detection():
    """Test network CIDR detection."""
    print("\n🧪 Testing Network Detection")
    print("=" * 50)
    
    updater = BitaxeUpdater()
    
    network_cidr = updater.get_local_network_cidr()
    if network_cidr:
        print(f"✅ Detected network: {network_cidr}")
        return True
    else:
        print(f"❌ Could not detect network")
        return False

def test_discovery_components():
    """Test individual components of discovery."""
    print("\n🧪 Testing Discovery Components")
    print("=" * 50)
    
    success = True
    
    # Test network detection
    if not test_network_detection():
        success = False
    
    # Test device verification
    if not test_single_device_verification():
        success = False
    
    return success

def main():
    """Main test function."""
    print("🔍 Bitaxe Discovery Test Suite")
    print("=" * 50)
    
    try:
        # Test individual components
        if test_discovery_components():
            print("\n✅ All discovery components working!")
            print("\nNote: Full network scanning requires nmap and may take time.")
            print("To test full discovery, run:")
            print("  python updtrr.py --discover --check-versions esp-miner.bin www.bin")
        else:
            print("\n❌ Some discovery components failed")
            return 1
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
