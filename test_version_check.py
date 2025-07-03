#!/usr/bin/env python3
"""
Test script to demonstrate version checking functionality
"""

import sys
from pathlib import Path
from updtrr import BitaxeUpdater

def test_version_extraction():
    """Test version extraction from binary files."""
    print("🔍 Testing version extraction from binary files...")
    
    updater = BitaxeUpdater()
    
    # Test with esp-miner.bin
    esp_miner_bin = Path("esp-miner.bin")
    if esp_miner_bin.exists():
        version = updater.extract_version_from_binary(esp_miner_bin)
        print(f"ESP-Miner binary version: {version}")
    else:
        print("❌ esp-miner.bin not found")
    
    # Test with www.bin
    www_bin = Path("www.bin")
    if www_bin.exists():
        version = updater.extract_version_from_binary(www_bin)
        print(f"WWW binary version: {version}")
    else:
        print("❌ www.bin not found")


def test_version_comparison():
    """Test version comparison logic."""
    print("\n🔍 Testing version comparison logic...")
    
    updater = BitaxeUpdater()
    
    test_cases = [
        ("v2.9.0", "2.9.0", False),   # Same version
        ("v2.9.0", "2.9.1", True),   # Minor update needed
        ("v2.9.0", "2.10.0", True),  # Major update needed
        ("v2.9.1", "2.9.0", False),  # Device newer than binary
        ("v2.8.0", "2.9.0", True),   # Update needed
        ("2.9.0", "v2.9.0", False),  # Same version, different format
    ]
    
    for current, binary, expected in test_cases:
        result = updater.compare_versions(current, binary)
        status = "✅" if result == expected else "❌"
        print(f"{status} {current} vs {binary} -> {'Update needed' if result else 'Up to date'}")


def test_device_communication():
    """Test communication with actual device."""
    print("\n🔍 Testing device communication...")
    
    updater = BitaxeUpdater()
    
    # Test with device from sample_devices.csv
    try:
        with open("sample_devices.csv", "r") as f:
            lines = f.readlines()
            test_ip = None
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    test_ip = line
                    break
        
        if test_ip:
            print(f"Testing communication with {test_ip}...")
            device_info = updater.get_device_version(test_ip)
            if device_info:
                print(f"Device version: {device_info['version']}")
                print(f"AxeOS version: {device_info['axeOSVersion']}")
            else:
                print("❌ Could not get device version")
        else:
            print("❌ No test IP found in sample_devices.csv")
            
    except Exception as e:
        print(f"❌ Error testing device communication: {e}")


if __name__ == "__main__":
    print("🧪 Bitaxe Updater Version Checking Test")
    print("=" * 50)
    
    test_version_extraction()
    test_version_comparison()
    test_device_communication()
    
    print("\n✅ Test completed!")
