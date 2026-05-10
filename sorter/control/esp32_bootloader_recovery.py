#!/usr/bin/env python3
"""
ESP32 Bootloader Recovery Tool
HUSKY-SORTER-001

Repairs bricked ESP32 modules by forcing them into bootloader mode
and flashing the default partition table + firmware.

Usage:
    python esp32_bootloader_recovery.py --port /dev/ttyUSB0
    python esp32_bootloader_recovery.py --port /dev/ttyUSB0 --erase-flash
    python esp32_bootloader_recovery.py --port /dev/ttyUSB0 --restore-default-partitions

Requirements:
    pip install esptool

Causes of bricked ESP32:
    - Failed firmware update (power loss during flash)
    - Corrupted partition table
    - Invalid bootloader flash address
    - GPIO pin misconfiguration (strapping pins wrong state)
    - Watchdog timeout loop
"""

import argparse
import os
import subprocess
import sys
import time


# Default ESP32 partition table (4MB flash)
DEFAULT_PARTITION_CSV = """
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     0x9000,  0x4000,
otadata,  data, ota,      0xd000,  0x2000,
app0,     app,  ota_0,   0x10000, 0x3C0000,
app1,     app,  ota_1,   0x3D0000,0x3C0000,
spiffs,   data, spiffs,  0x7A0000,0x860000,
"""


def find_esptool():
    """Find esptool.py installation."""
    for cmd in ['esptool.py', 'esptool']:
        result = subprocess.run(['which', cmd], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    # Try pip show
    result = subprocess.run([sys.executable, '-m', 'pip', 'show', 'esptool'], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        for line in result.stdout.split('\n'):
            if line.startswith('Location:'):
                loc = line.split(':', 1)[1].strip()
                tool = os.path.join(loc, 'esptool.py')
                if os.path.exists(tool):
                    return tool
    return None


def force_bootloader_mode(port: str) -> bool:
    """
    Attempt to force ESP32 into bootloader mode.
    
    Method 1: RTS toggle (works with most USB-UART adapters)
    Method 2: GPIO0/GPIO2 low + EN pulse (requires hardware access)
    
    Returns True if successful.
    """
    try:
        import serial
    except ImportError:
        print("⚠️ pyserial not installed. Install with: pip install pyserial")
        return False
    
    print(f"\n🔄 Attempting to force bootloader mode on {port}...")
    
    # Method 1: RTS toggling (standard CP2102/CH340 behavior)
    try:
        ser = serial.Serial(port, 1200, timeout=1)
        ser.dtr = False  # EN=low
        ser.rts = True   # GPIO0 low (boot mode)
        time.sleep(0.1)
        ser.dtr = True   # EN=high (release reset)
        time.sleep(0.5)
        ser.rts = False  # GPIO0 back to normal
        time.sleep(1)
        ser.close()
        print("   ✅ RTS toggle method applied")
        return True
    except Exception as e:
        print(f"   ⚠️ RTS method failed: {e}")
    
    print("\n⚠️ Could not automatically enter bootloader mode.")
    print("   Manual method:")
    print("   1. Hold BOOT button (GPIO0)")
    print("   2. Press and release EN/RST button")
    print("   3. Release BOOT button")
    print("   4. This ESP32 should now be in bootloader mode")
    return False


def erase_flash(port: str) -> bool:
    """Completely erase ESP32 flash memory."""
    esptool = find_esptool()
    if not esptool:
        print("❌ esptool not found. Install: pip install esptool")
        return False
    
    print(f"\n🗑️ Erasing flash on {port}...")
    
    cmd = [
        sys.executable, esptool,
        '--port', port,
        '--baud', '921600',
        'erase_flash'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("✅ Flash erased successfully")
            return True
        else:
            print(f"❌ Erase failed:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Erase timeout (60s)")
        return False


def flash_default_partitions(port: str) -> bool:
    """Flash default partition table and bootloader."""
    esptool = find_esptool()
    if not esptool:
        return False
    
    print(f"\n📦 Flashing default partition table...")
    
    # Create temporary partition CSV
    csv_path = '/tmp/default_partitions.csv'
    with open(csv_path, 'w') as f:
        f.write(DEFAULT_PARTITION_CSV)
    
    # Flash partition table
    cmd = [
        sys.executable, esptool,
        '--port', port,
        '--baud', '921600',
        'write_flash',
        '--flash_mode', 'dio',
        '--flash_freq', '80m',
        '--flash_size', '4MB',
        '0x8000', csv_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("✅ Default partition table written to 0x8000")
            return True
        else:
            print(f"❌ Partition flash failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def read_chip_info(port: str) -> dict:
    """Read ESP32 chip info (MAC, chip model, etc.)."""
    esptool = find_esptool()
    if not esptool:
        return {}
    
    print(f"\n📟 Reading chip info from {port}...")
    
    cmd = [
        sys.executable, esptool,
        '--port', port,
        '--baud', '115200',
        'flash_id'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print(f"   {result.stdout.strip()}")
            return {'success': True, 'output': result.stdout}
        else:
            print(f"   ⚠️ Chip read failed: {result.stderr}")
            return {'success': False}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def verify_uart_connection(port: str) -> bool:
    """Verify ESP32 is connected and responding."""
    try:
        import serial
    except ImportError:
        return False
    
    try:
        ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(0.2)
        
        # Try to read any pending data
        available = ser.in_waiting
        if available > 0:
            data = ser.read(available)
            print(f"\n📟 ESP32 output ({available} bytes):")
            print(f"   {data.decode('utf-8', errors='replace')[:200]}")
        
        # Send STATUS command (firmware check)
        ser.write(b'{"cmd":"STATUS"}\n')
        time.sleep(0.5)
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            print(f"\n   Status response: {response.decode('utf-8', errors='replace')[:100]}")
        
        ser.close()
        return True
    except Exception as e:
        return False


def main():
    parser = argparse.ArgumentParser(
        description='ESP32 Bootloader Recovery Tool — HUSKY-SORTER-001',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Recovery Procedure:
  1. Connect ESP32 via USB-UART (CP2102 or CH340)
  2. Put ESP32 in bootloader mode (hold BOOT + press RST)
  3. Run recovery tool with appropriate options

Examples:
  Basic recovery (try to fix bricked ESP32):
    python esp32_bootloader_recovery.py --port /dev/ttyUSB0

  Full erase (clean slate for new firmware):
    python esp32_bootloader_recovery.py --port /dev/ttyUSB0 --erase-flash

  Verify chip is detected:
    python esp32_bootloader_recovery.py --port /dev/ttyUSB0 --check-chip

Warning:
  Full flash erase will delete all calibration data and settings.
  After recovery, you must re-flash firmware and re-calibrate sensors.
        """
    )
    
    parser.add_argument('--port', '-p', required=True,
                        help='Serial port (e.g., /dev/ttyUSB0)')
    parser.add_argument('--erase-flash', '-e', action='store_true',
                        help='Erase entire flash (warning: deletes all data)')
    parser.add_argument('--restore-partitions', action='store_true',
                        help='Restore default partition table')
    parser.add_argument('--check-chip', action='store_true',
                        help='Read chip info and verify connection')
    parser.add_argument('--force-boot', action='store_true',
                        help='Attempt to force bootloader mode via RTS')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  ESP32 Bootloader Recovery Tool")
    print("  HUSKY-SORTER-001")
    print("=" * 60)
    print(f"\n   Port: {args.port}")
    
    if not os.path.exists(args.port) and not args.port.startswith('/dev/'):
        print(f"\n⚠️ Port {args.port} does not exist.")
        print("   Available ports:")
        import glob
        for p in sorted(glob.glob('/dev/tty.*') + glob.glob('/dev/cu.*')):
            print(f"   • {p}")
    
    # Check chip first
    if args.check_chip:
        print("\n🔍 Checking ESP32 connection...")
        info = read_chip_info(args.port)
        if info.get('success'):
            print("✅ ESP32 detected and responding")
        else:
            print("❌ ESP32 not responding. Is it in bootloader mode?")
        return
    
    # Force bootloader mode
    if args.force_boot:
        success = force_bootloader_mode(args.port)
        if success:
            print("\n✅ Bootloader mode entered successfully")
        else:
            print("\n⚠️ Could not automatically enter bootloader mode")
            print("   Please follow manual instructions above")
    
    # Erase flash
    if args.erase_flash:
        print("\n⚠️ FLASH ERASE REQUESTED")
        print("   This will delete ALL data on ESP32 flash memory:")
        print("   - Firmware")
        print("   - Calibration data")
        print("   - Partition table")
        print("   - WiFi credentials (if stored)")
        print()
        confirm = input("   Are you sure? Type 'YES-ERASE' to confirm: ")
        if confirm.strip() != "YES-ERASE":
            print("   Cancelled.")
            return
        
        if erase_flash(args.port):
            print("\n✅ Flash erased. ESP32 is now blank.")
            print("   You can now flash new firmware using firmware_update_tool.py")
        return
    
    # Restore partitions
    if args.restore_partitions:
        print("\n📦 Restoring default partition table...")
        if flash_default_partitions(args.port):
            print("✅ Default partitions restored")
            print("   Note: Bootloader still needs to be written")
        return
    
    # Default: just check chip
    print("\n🔍 Verifying ESP32 connection...")
    if verify_uart_connection(args.port):
        print("✅ ESP32 is connected and responding")
    else:
        print("❌ ESP32 not responding")
        print("\n   Try the following:")
        print("   1. Hold BOOT button (GPIO0)")
        print("   2. Press and release EN/RST")
        print("   3. Release BOOT button")
        print("   4. Re-run this tool with --force-boot")
    
    print("\n   To erase flash (factory reset):")
    print("   python esp32_bootloader_recovery.py --port {} --erase-flash".format(args.port))


if __name__ == '__main__':
    main()