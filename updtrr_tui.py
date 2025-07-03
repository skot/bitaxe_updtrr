#!/usr/bin/env python3
"""
updtrr_tui.py - Bitaxe Firmware and Web Interface Updater with TUI

A beautiful terminal user interface for updating ESP-Miner firmware and web interface 
files on multiple Bitaxe devices simultaneously.

Usage:
    python updtrr_tui.py <csv_file> <esp-miner.bin> <www.bin>
"""

import sys
import csv
import requests
import argparse
import time
import curses
import threading
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from queue import Queue, Empty
from datetime import datetime
import json


class DeviceStatus:
    """Represents the status of a device update."""
    PENDING = "PENDING"
    WWW_UPLOADING = "WWW_UPLOADING"
    WWW_SUCCESS = "WWW_SUCCESS"
    WWW_FAILED = "WWW_FAILED"
    FW_UPLOADING = "FW_UPLOADING"
    FW_SUCCESS = "FW_SUCCESS"
    FW_FAILED = "FW_FAILED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UpdateEvent:
    """Represents an update event for the TUI."""
    def __init__(self, event_type: str, device_ip: str, message: str, status: str = None):
        self.timestamp = datetime.now()
        self.event_type = event_type
        self.device_ip = device_ip
        self.message = message
        self.status = status


class BitaxeUpdaterTUI:
    """TUI version of the Bitaxe updater with real-time status display."""
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/octet-stream'})
        
        # TUI state
        self.devices: Dict[str, str] = {}  # ip -> status
        self.event_queue = Queue()
        self.log_messages = []
        self.current_device = 0
        self.total_devices = 0
        self.start_time = None
        self.is_running = False
        
        # Statistics
        self.stats = {
            'total': 0,
            'completed': 0,
            'www_success': 0,
            'fw_success': 0,
            'failed': 0
        }
    
    def load_ip_addresses(self, csv_file: Path) -> List[str]:
        """Load IP addresses from CSV file."""
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        
        ip_addresses = []
        
        try:
            with open(csv_file, 'r', newline='') as file:
                content = file.read().strip()
                file.seek(0)
                
                if ',' not in content:
                    for line in file:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            ip_addresses.append(line)
                else:
                    reader = csv.reader(file)
                    for row in reader:
                        if row and row[0].strip() and not row[0].strip().startswith('#'):
                            ip_addresses.append(row[0].strip())
                            
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
        
        if not ip_addresses:
            raise ValueError("No IP addresses found in CSV file")
        
        return ip_addresses
    
    def validate_binary_file(self, bin_file: Path) -> None:
        """Validate that binary file exists and is readable."""
        if not bin_file.exists():
            raise FileNotFoundError(f"Binary file not found: {bin_file}")
        
        if bin_file.stat().st_size == 0:
            raise ValueError(f"Binary file is empty: {bin_file}")
    
    def add_event(self, event_type: str, device_ip: str, message: str, status: str = None):
        """Add an event to the queue for TUI display."""
        event = UpdateEvent(event_type, device_ip, message, status)
        self.event_queue.put(event)
    
    def upload_www(self, ip: str, www_file: Path) -> bool:
        """Upload web interface to a device."""
        url = f"http://{ip}/api/system/OTAWWW"
        
        try:
            self.devices[ip] = DeviceStatus.WWW_UPLOADING
            self.add_event("WWW_START", ip, f"Uploading web interface...")
            
            with open(www_file, 'rb') as f:
                www_data = f.read()
            
            response = self.session.post(url, data=www_data, timeout=self.timeout)
            
            if response.status_code == 200:
                self.devices[ip] = DeviceStatus.WWW_SUCCESS
                self.add_event("WWW_SUCCESS", ip, f"Web interface uploaded successfully ({len(www_data)} bytes)")
                self.stats['www_success'] += 1
                return True
            else:
                self.devices[ip] = DeviceStatus.WWW_FAILED
                self.add_event("WWW_FAILED", ip, f"Upload failed: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            self.devices[ip] = DeviceStatus.WWW_FAILED
            self.add_event("WWW_FAILED", ip, "Upload timeout")
            return False
        except requests.exceptions.ConnectionError:
            self.devices[ip] = DeviceStatus.WWW_FAILED
            self.add_event("WWW_FAILED", ip, "Connection error")
            return False
        except Exception as e:
            self.devices[ip] = DeviceStatus.WWW_FAILED
            self.add_event("WWW_FAILED", ip, f"Error: {str(e)}")
            return False
    
    def upload_firmware(self, ip: str, firmware_file: Path) -> bool:
        """Upload ESP-Miner firmware to a device."""
        url = f"http://{ip}/api/system/OTA"
        
        try:
            self.devices[ip] = DeviceStatus.FW_UPLOADING
            self.add_event("FW_START", ip, f"Uploading firmware...")
            
            with open(firmware_file, 'rb') as f:
                firmware_data = f.read()
            
            response = self.session.post(url, data=firmware_data, timeout=self.timeout)
            
            if response.status_code == 200:
                self.devices[ip] = DeviceStatus.FW_SUCCESS
                self.add_event("FW_SUCCESS", ip, f"Firmware uploaded successfully ({len(firmware_data)} bytes)")
                self.stats['fw_success'] += 1
                return True
            else:
                self.devices[ip] = DeviceStatus.FW_FAILED
                self.add_event("FW_FAILED", ip, f"Upload failed: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            self.devices[ip] = DeviceStatus.FW_FAILED
            self.add_event("FW_FAILED", ip, "Upload timeout")
            return False
        except requests.exceptions.ConnectionError:
            self.devices[ip] = DeviceStatus.FW_FAILED
            self.add_event("FW_FAILED", ip, "Connection error")
            return False
        except Exception as e:
            self.devices[ip] = DeviceStatus.FW_FAILED
            self.add_event("FW_FAILED", ip, f"Error: {str(e)}")
            return False
    
    def update_device(self, ip: str, firmware_file: Path, www_file: Path, delay: int = 5) -> Tuple[bool, bool]:
        """Update both web interface and firmware on a device."""
        self.add_event("DEVICE_START", ip, "Starting device update...")
        
        # Upload web interface first
        www_success = self.upload_www(ip, www_file)
        
        if www_success and delay > 0:
            self.add_event("DELAY", ip, f"Waiting {delay} seconds before firmware upload...")
            time.sleep(delay)
        
        # Upload firmware second
        firmware_success = self.upload_firmware(ip, firmware_file)
        
        # Update final status
        if www_success and firmware_success:
            self.devices[ip] = DeviceStatus.COMPLETED
            self.add_event("DEVICE_SUCCESS", ip, "Device updated successfully!")
            self.stats['completed'] += 1
        else:
            self.devices[ip] = DeviceStatus.FAILED
            self.add_event("DEVICE_FAILED", ip, f"Device update failed (WWW: {'✓' if www_success else '✗'}, FW: {'✓' if firmware_success else '✗'})")
            self.stats['failed'] += 1
        
        return www_success, firmware_success
    
    def update_worker(self, ip_addresses: List[str], firmware_file: Path, www_file: Path, 
                     device_delay: int = 10, upload_delay: int = 5):
        """Worker thread that performs the actual updates."""
        self.is_running = True
        self.start_time = datetime.now()
        
        for i, ip in enumerate(ip_addresses, 1):
            if not self.is_running:
                break
                
            self.current_device = i
            self.devices[ip] = DeviceStatus.PENDING
            
            self.add_event("PROGRESS", ip, f"Starting device {i}/{len(ip_addresses)}")
            
            www_success, firmware_success = self.update_device(ip, firmware_file, www_file, upload_delay)
            
            # Delay between devices (except for the last one)
            if i < len(ip_addresses) and device_delay > 0 and self.is_running:
                self.add_event("DELAY", ip, f"Waiting {device_delay} seconds before next device...")
                time.sleep(device_delay)
        
        self.is_running = False
        self.add_event("COMPLETE", "", "All updates completed!")


class TUIRenderer:
    """Handles the curses-based TUI rendering."""
    
    def __init__(self, stdscr, updater: BitaxeUpdaterTUI):
        self.stdscr = stdscr
        self.updater = updater
        self.height, self.width = stdscr.getmaxyx()
        
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Success
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)     # Error
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Warning
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)    # Info
        curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Progress
        curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Header
        
        # Configure cursor
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.timeout(100)
    
    def get_status_color(self, status: str) -> int:
        """Get color pair for status."""
        color_map = {
            DeviceStatus.PENDING: 3,           # Yellow
            DeviceStatus.WWW_UPLOADING: 5,     # Cyan
            DeviceStatus.WWW_SUCCESS: 1,       # Green
            DeviceStatus.WWW_FAILED: 2,        # Red
            DeviceStatus.FW_UPLOADING: 5,      # Cyan
            DeviceStatus.FW_SUCCESS: 1,        # Green
            DeviceStatus.FW_FAILED: 2,         # Red
            DeviceStatus.COMPLETED: 1,         # Green
            DeviceStatus.FAILED: 2,            # Red
        }
        return color_map.get(status, 0)
    
    def get_status_symbol(self, status: str) -> str:
        """Get symbol for status."""
        symbol_map = {
            DeviceStatus.PENDING: "...",
            DeviceStatus.WWW_UPLOADING: "WWW",
            DeviceStatus.WWW_SUCCESS: " + ",
            DeviceStatus.WWW_FAILED: " X ",
            DeviceStatus.FW_UPLOADING: " FW",
            DeviceStatus.FW_SUCCESS: " + ",
            DeviceStatus.FW_FAILED: " X ",
            DeviceStatus.COMPLETED: "OK!",
            DeviceStatus.FAILED: "ERR",
        }
        return symbol_map.get(status, "??")
    
    def draw_header(self):
        """Draw the header section."""
        title = "=== Bitaxe Firmware Updater TUI ==="
        title_x = max(0, (self.width - len(title)) // 2)
        
        self.safe_addstr(0, title_x, title, curses.color_pair(6) | curses.A_BOLD)
        
        # Draw horizontal line
        line = "-" * min(self.width - 1, 80)
        self.safe_addstr(1, 0, line)
    
    def draw_stats(self, y_start: int) -> int:
        """Draw statistics section."""
        stats = self.updater.stats
        elapsed = ""
        
        if self.updater.start_time:
            elapsed_time = datetime.now() - self.updater.start_time
            elapsed = f" | Elapsed: {str(elapsed_time).split('.')[0]}"
        
        status_text = "RUNNING" if self.updater.is_running else "COMPLETED"
        status_color = 5 if self.updater.is_running else 1
        
        self.safe_addstr(y_start, 0, "Statistics:", curses.color_pair(4) | curses.A_BOLD)
        
        # Progress
        progress = f"{self.updater.current_device}/{stats['total']}"
        self.safe_addstr(y_start + 1, 2, f"Progress: {progress}{elapsed}")
        
        # Status
        self.safe_addstr(y_start + 2, 2, f"Status: ")
        status_x = 2 + len("Status: ")
        self.safe_addstr(y_start + 2, status_x, status_text, curses.color_pair(status_color) | curses.A_BOLD)
        
        # Results
        results_line = f"Completed: {stats['completed']} | WWW Success: {stats['www_success']} | FW Success: {stats['fw_success']} | Failed: {stats['failed']}"
        self.safe_addstr(y_start + 3, 2, results_line)
        
        return y_start + 5
    
    def draw_devices(self, y_start: int) -> int:
        """Draw device status section."""
        if not self.updater.devices:
            return y_start
        
        self.stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
        self.stdscr.addstr(y_start, 0, "Device Status:")
        self.stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
        
        y = y_start + 1
        max_devices = min(len(self.updater.devices), self.height - y - 8)  # Leave space for logs
        
        devices_list = list(self.updater.devices.items())
        start_idx = max(0, len(devices_list) - max_devices)
        
        for ip, status in devices_list[start_idx:]:
            if y >= self.height - 8:
                break
                
            symbol = self.get_status_symbol(status)
            color = self.get_status_color(status)
            
            # Format IP address
            ip_display = f"{ip:<15}"
            
            self.stdscr.addstr(y, 2, f"{symbol} {ip_display} ")
            
            self.stdscr.attron(curses.color_pair(color))
            self.stdscr.addstr(f"{status}")
            self.stdscr.attroff(curses.color_pair(color))
            
            y += 1
        
        return y + 1
    
    def draw_logs(self, y_start: int):
        """Draw log messages section."""
        if y_start >= self.height - 2:
            return
        
        self.stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
        self.stdscr.addstr(y_start, 0, "Recent Activity:")
        self.stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
        
        log_height = self.height - y_start - 3
        if log_height <= 0:
            return
        
        # Show recent log messages
        recent_logs = self.updater.log_messages[-log_height:]
        
        for i, log_msg in enumerate(recent_logs):
            y = y_start + 1 + i
            if y >= self.height - 1:
                break
            
            # Truncate message to fit screen
            max_msg_width = self.width - 4
            display_msg = log_msg[:max_msg_width] if len(log_msg) > max_msg_width else log_msg
            
            self.stdscr.addstr(y, 2, display_msg)
    
    def safe_addstr(self, y: int, x: int, text: str, attr: int = 0):
        """Safely add string to screen, handling terminal size limits."""
        try:
            # Make sure we're within screen bounds
            if y >= self.height or x >= self.width:
                return
            
            # Truncate text to fit within screen width
            max_width = self.width - x - 1
            if max_width <= 0:
                return
                
            safe_text = text[:max_width] if len(text) > max_width else text
            
            if attr:
                self.stdscr.attron(attr)
            self.stdscr.addstr(y, x, safe_text)
            if attr:
                self.stdscr.attroff(attr)
        except curses.error:
            # Ignore curses errors (like trying to write to bottom-right corner)
            pass
    
    def draw_footer(self):
        """Draw the footer with controls."""
        footer_y = self.height - 1
        footer_text = "Press 'q' to quit | 'r' to refresh"
        
        # Clear the line and add footer text
        spaces = " " * min(self.width - 1, 80)
        self.safe_addstr(footer_y, 0, spaces, curses.color_pair(6))
        
        text_x = max(0, (self.width - len(footer_text)) // 2)
        self.safe_addstr(footer_y, text_x, footer_text, curses.color_pair(6))
    
    def render(self):
        """Main render function."""
        self.stdscr.clear()
        
        # Draw sections
        self.draw_header()
        
        y = 3
        y = self.draw_stats(y)
        y = self.draw_devices(y)
        self.draw_logs(y)
        
        self.draw_footer()
        
        self.stdscr.refresh()
    
    def process_events(self):
        """Process events from the updater."""
        try:
            while True:
                event = self.updater.event_queue.get_nowait()
                
                # Format log message
                timestamp = event.timestamp.strftime("%H:%M:%S")
                log_msg = f"[{timestamp}] {event.device_ip}: {event.message}"
                
                self.updater.log_messages.append(log_msg)
                
                # Keep only recent messages
                if len(self.updater.log_messages) > 100:
                    self.updater.log_messages = self.updater.log_messages[-50:]
                    
        except Empty:
            pass
    
    def run(self, ip_addresses: List[str], firmware_file: Path, www_file: Path, 
            device_delay: int = 10, upload_delay: int = 5):
        """Main TUI loop."""
        # Initialize device list
        for ip in ip_addresses:
            self.updater.devices[ip] = DeviceStatus.PENDING
        
        self.updater.stats['total'] = len(ip_addresses)
        
        # Start update worker thread
        update_thread = threading.Thread(
            target=self.updater.update_worker,
            args=(ip_addresses, firmware_file, www_file, device_delay, upload_delay)
        )
        update_thread.daemon = True
        update_thread.start()
        
        # Main loop
        try:
            while True:
                # Process events
                self.process_events()
                
                # Render screen
                self.render()
                
                # Handle input
                key = self.stdscr.getch()
                if key == ord('q') or key == ord('Q'):
                    self.updater.is_running = False
                    break
                elif key == ord('r') or key == ord('R'):
                    # Force refresh
                    continue
                
                # Check if updates are complete
                if not self.updater.is_running and not update_thread.is_alive():
                    # Wait a bit more to show final status
                    time.sleep(2)
                    break
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self.updater.is_running = False


def main_tui(stdscr, args):
    """Main TUI function."""
    try:
        # Check terminal size
        height, width = stdscr.getmaxyx()
        if height < 20 or width < 80:
            stdscr.clear()
            stdscr.addstr(0, 0, f"Terminal too small! Need at least 80x20, got {width}x{height}")
            stdscr.addstr(1, 0, "Please resize your terminal and try again.")
            stdscr.addstr(2, 0, "Press any key to exit...")
            stdscr.refresh()
            stdscr.getch()
            return
        
        # Initialize updater
        updater = BitaxeUpdaterTUI(timeout=args.timeout)
        
        # Validate input files
        updater.validate_binary_file(args.esp_miner_bin)
        updater.validate_binary_file(args.www_bin)
        
        # Load IP addresses
        ip_addresses = updater.load_ip_addresses(args.csv_file)
        
        # Initialize TUI
        tui = TUIRenderer(stdscr, updater)
        
        # Run TUI
        tui.run(ip_addresses, args.esp_miner_bin, args.www_bin, 
               device_delay=args.device_delay, upload_delay=args.upload_delay)
        
        # Show final results
        stdscr.clear()
        stdscr.addstr(0, 0, "🎉 Update Complete! 🎉\n\n")
        stdscr.addstr(f"Total devices: {updater.stats['total']}\n")
        stdscr.addstr(f"Completed successfully: {updater.stats['completed']}\n")
        stdscr.addstr(f"WWW uploads successful: {updater.stats['www_success']}\n")
        stdscr.addstr(f"Firmware uploads successful: {updater.stats['fw_success']}\n")
        stdscr.addstr(f"Failed: {updater.stats['failed']}\n\n")
        stdscr.addstr("Press any key to exit...")
        stdscr.refresh()
        stdscr.getch()
        
    except Exception as e:
        # Make sure we can see errors even in curses mode
        stdscr.clear()
        stdscr.addstr(0, 0, f"❌ Error: {str(e)}\n\n")
        stdscr.addstr("Stack trace:\n")
        
        import traceback
        error_lines = traceback.format_exc().split('\n')
        for i, line in enumerate(error_lines[:15]):  # Show first 15 lines
            try:
                stdscr.addstr(3 + i, 0, line[:stdscr.getmaxyx()[1]-1])
            except:
                break
        
        stdscr.addstr("\nPress any key to exit...")
        stdscr.refresh()
        stdscr.getch()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Update ESP-Miner firmware and web interface on multiple Bitaxe devices with TUI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('csv_file', type=Path, help='CSV file containing IP addresses')
    parser.add_argument('esp_miner_bin', type=Path, help='ESP-Miner firmware binary file')
    parser.add_argument('www_bin', type=Path, help='Web interface binary file')
    parser.add_argument('--timeout', type=int, default=60, 
                       help='HTTP request timeout in seconds (default: 60)')
    parser.add_argument('--device-delay', type=int, default=10,
                       help='Delay between device updates in seconds (default: 10)')
    parser.add_argument('--upload-delay', type=int, default=5,
                       help='Delay between web interface and firmware uploads in seconds (default: 5)')
    parser.add_argument('--debug', action='store_true',
                       help='Run in debug mode (show errors instead of TUI)')
    
    args = parser.parse_args()
    
    # Debug mode - run without TUI to see errors
    if args.debug:
        try:
            print("🔧 Bitaxe Firmware Updater - Debug Mode 🔧")
            print("=" * 50)
            
            # Initialize updater
            updater = BitaxeUpdaterTUI(timeout=args.timeout)
            
            # Validate input files
            print(f"Validating files...")
            updater.validate_binary_file(args.esp_miner_bin)
            updater.validate_binary_file(args.www_bin)
            print(f"✓ Files validated successfully")
            
            # Load IP addresses
            print(f"Loading IP addresses from {args.csv_file}...")
            ip_addresses = updater.load_ip_addresses(args.csv_file)
            print(f"✓ Loaded {len(ip_addresses)} IP addresses: {ip_addresses}")
            
            print("Debug mode complete. Use without --debug to run TUI.")
            return 0
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    # Run TUI
    try:
        curses.wrapper(main_tui, args)
    except KeyboardInterrupt:
        print("\nUpdate interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ TUI Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
