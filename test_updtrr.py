#!/usr/bin/env python3
"""
Test script for updtrr functionality
"""

import sys
from pathlib import Path
from updtrr import BitaxeUpdater

def test_csv_parsing():
    """Test CSV parsing functionality"""
    print("Testing CSV parsing...")
    
    updater = BitaxeUpdater()
    
    # Test with sample CSV
    try:
        ips = updater.load_ip_addresses(Path("sample_devices.csv"))
        print(f"✓ Successfully loaded {len(ips)} IP addresses:")
        for ip in ips:
            print(f"  - {ip}")
        return True
    except Exception as e:
        print(f"✗ CSV parsing failed: {e}")
        return False

def test_file_validation():
    """Test binary file validation"""
    print("\nTesting file validation...")
    
    updater = BitaxeUpdater()
    
    # Test with non-existent file
    try:
        updater.validate_binary_file(Path("nonexistent.bin"))
        print("✗ Should have failed for non-existent file")
        return False
    except FileNotFoundError:
        print("✓ Correctly detected non-existent file")
    
    # Test with the script itself (should work as it exists and is readable)
    try:
        updater.validate_binary_file(Path("updtrr.py"))
        print("✓ Correctly validated existing file")
        return True
    except Exception as e:
        print(f"✗ File validation failed: {e}")
        return False

def main():
    """Run basic tests"""
    print("Running updtrr functionality tests...\n")
    
    tests = [
        test_csv_parsing,
        test_file_validation
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
