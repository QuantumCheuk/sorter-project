#!/usr/bin/env python3
"""
ESP32 Firmware Update Tool
HUSKY-SORTER-001

Uploads compiled firmware to ESP32 via UART (esptool.py wrapper).
Also validates firmware integrity and can check current version on device.

Usage:
    python firmware_update_tool.py --port /dev/ttyUSB0 --bin firmware.bin
    python firmware_update_tool.py --port /dev/ttyUSB0 --check-version
    python firmware_update_tool.py --port /dev/ttyUSB0 --verify firmware.bin

Requirements:
    pip install esptool
"""

import argparse
import os
import sys
import subprocess
import re
import time
import hashlib


def compute_sha256(filepath: str) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def find_esptool():
    """Locate esptool.py."""
    paths = [
        os.path.expanduser('~/.arduino/packages/esp32/tools/esptool_py/'),
        '/usr/local/bin/esptool.py',
        '/usr/bin/esptool.py',
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    # Check PATH
    result = subprocess.run(['which', 'esptool.py'], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    result = subprocess.run(['pip', 'show', 'esptool'], capture_output=True, text=True)
    if result.returncode == 0:
        # esptool installed via pip - find location
        for line in result.stdout.split('\n'):
            if line.startswith('Location:'):
                loc = line.split(':', 1)[1].strip()
                tool = os.path.join(loc, 'esptool.py')
                if os.path.exists(tool):
                    return tool
    return None


def check_esptool_installed():
    """Check if esptool is available."""
    tool = find_esptool()
    if tool:
        print(f"✅ esptool found: {tool}")
        return True
    print("❌ esptool not found.")
    print("   Install with: pip install esptool")
    print("   Or: sudo apt install esptool-js (Debian/Ubuntu)")
    return False


def parse_version_from_ino(ino_path: str) -> tuple:
    """Extract version and build date from .ino file."""
    with open(ino_path, 'r') as f:
        content = f.read()
    
    version_match = re.search(r'#define\s+FIRMWARE_VERSION\s+"([^"]+)"', content)
    build_match = re.search(r'#define\s+FIRMWARE_BUILD\s+"([^"]+)"', content)
    
    version = version_match.group(1) if version_match else "unknown"
    build = build_match.group(1) if build_match else "unknown"
    return version, build


def upload_firmware(port: str, bin_path: str, esp32_partition: str = "app0") -> bool:
    """
    Upload firmware to ESP32 via UART.
    
    Args:
        port: Serial port (e.g., /dev/ttyUSB0 or COM3)
        bin_path: Path to compiled .bin file
        esp32_partition: Target partition (default: app0 / 0x10000)
    """
    if not os.path.exists(bin_path):
        print(f"❌ Firmware binary not found: {bin_path}")
        return False
    
    esptool = find_esptool()
    if not esptool:
        print("❌ esptool not found. Cannot upload firmware.")
        return False
    
    # Get file size and SHA256
    size = os.path.getsize(bin_path)
    sha256 = compute_sha256(bin_path)
    print(f"   Binary: {bin_path}")
    print(f"   Size: {size:,} bytes ({size/1024:.1f} KB)")
    print(f"   SHA256: {sha256[:16]}...")
    
    # Address for app0 partition (standard ESP32 partition table)
    address = 0x10000  # 64KB offset for app0
    
    print(f"\n🚀 Uploading firmware to {port} @ 0x{address:x}...")
    
    cmd = [
        sys.executable, esptool,
        '--port', port,
        '--baud', '921600',
        'write_flash',
        '--flash_mode', 'dio',
        '--flash_freq', '80m',
        '--flash_size', '4MB',
        str(hex(address)), bin_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("✅ Firmware upload complete!")
            print("\n   Now flashing firmware...")
            print(result.stdout)
            return True
        else:
            print(f"❌ Upload failed:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Upload timeout (120s). ESP32 may not be in bootloader mode.")
        print("   Put ESP32 in bootloader mode: hold BOOT button, press and release RST")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_current_version(port: str) -> bool:
    """
    Query current firmware version from ESP32 via serial.
    The device should respond to {"cmd":"STATUS"} with firmware info.
    """
    try:
        import serial
    except ImportError:
        print("⚠️ pyserial not installed. Run: pip install pyserial")
        print("   Skipping version check.")
        return False
    
    try:
        ser = serial.Serial(port, 115200, timeout=2)
        time.sleep(0.5)
        ser.write(b'{"cmd":"STATUS"}\n')
        time.sleep(1)
        response = ser.read(256)
        ser.close()
        
        if response:
            print(f"📟 Device response: {response.decode('utf-8', errors='replace')}")
            return True
        else:
            print("⚠️ No response from device. Is the Pi→ESP32 UART connected?")
            return False
    except Exception as e:
        print(f"⚠️ Cannot connect to {port}: {e}")
        return False


def verify_firmware(bin_path: str) -> bool:
    """Verify firmware binary integrity."""
    if not os.path.exists(bin_path):
        print(f"❌ Binary not found: {bin_path}")
        return False
    
    size = os.path.getsize(bin_path)
    sha256 = compute_sha256(bin_path)
    
    # Check reasonable size (256KB - 4MB for ESP32)
    if size < 256 * 1024:
        print(f"⚠️ Binary seems too small ({size} bytes). Expected ≥256KB.")
    elif size > 4 * 1024 * 1024:
        print(f"⚠️ Binary seems too large ({size} bytes). Expected ≤4MB.")
    else:
        print(f"✅ Binary size OK: {size:,} bytes ({size/1024:.1f} KB)")
    
    print(f"✅ SHA256: {sha256}")
    return True


def build_firmware(ino_path: str, board: str = "esp32:esp32:esp32wroom") -> bool:
    """
    Compile firmware using Arduino CLI.
    Requires Arduino CLI to be installed.
    """
    arduino_cli = None
    for path in ['/usr/local/bin/arduino-cli', '/usr/bin/arduino-cli',
                 os.path.expanduser('~/.arduino/packages/esp32/tools/arduino-cli/')]:
        if os.path.exists(path):
            arduino_cli = path
            break
    
    # Check if arduino-cli exists
    result = subprocess.run(['which', 'arduino-cli'], capture_output=True, text=True)
    if result.returncode != 0:
        print("⚠️ arduino-cli not found. Install from: https://arduino.github.io/arduino-cli/latest/")
        print("   On Raspberry Pi: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh")
        return False
    
    sketch_dir = os.path.dirname(ino_path)
    
    print(f"🔨 Compiling {os.path.basename(ino_path)} for {board}...")
    
    # Compile sketch
    compile_cmd = [
        'arduino-cli', 'compile',
        '--fqbn', board,
        '--sketch', sketch_dir,
        '--output-dir', os.path.join(sketch_dir, 'build')
    ]
    
    try:
        result = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            # Find compiled binary
            build_dir = os.path.join(sketch_dir, 'build')
            bin_files = []
            for root, dirs, files in os.walk(build_dir):
                for f in files:
                    if f.endswith('.bin'):
                        bin_files.append(os.path.join(root, f))
            
            if bin_files:
                print(f"✅ Compilation successful: {bin_files[0]}")
                return True
            else:
                print("⚠️ Compilation OK but no .bin found in build directory")
                return False
        else:
            print(f"❌ Compilation failed:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Compilation timeout (300s)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='ESP32 Firmware Update Tool for HUSKY-SORTER-001',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Upload firmware:
    python firmware_update_tool.py --port /dev/ttyUSB0 --bin build/sorter_esp32.ino.bin

  Check device version:
    python firmware_update_tool.py --port /dev/ttyUSB0 --check-version

  Verify binary:
    python firmware_update_tool.py --bin firmware.bin --verify

  Compile + upload (if arduino-cli installed):
    python firmware_update_tool.py --port /dev/ttyUSB0 --compile --board esp32:esp32:esp32wroom

Notes:
  - Put ESP32 in bootloader mode before uploading: hold BOOT, press RST, release BOOT
  - Default upload speed: 921600 baud
  - Target partition: 0x10000 (app0, standard ESP32 partition)
        """
    )
    
    parser.add_argument('--port', '-p', default='/dev/ttyUSB0',
                        help='Serial port (default: /dev/ttyUSB0)')
    parser.add_argument('--bin', '-b',
                        help='Firmware binary to upload (.bin file)')
    parser.add_argument('--check-version', '-v', action='store_true',
                        help='Query current firmware version on device')
    parser.add_argument('--verify', '-V', metavar='BIN',
                        help='Verify firmware binary integrity')
    parser.add_argument('--compile', '-c', action='store_true',
                        help='Compile sketch before uploading')
    parser.add_argument('--board', default='esp32:esp32:esp32wroom',
                        help='Arduino FQBN (default: esp32:esp32:esp32wroom)')
    parser.add_argument('--sketch',
                        default='firmware/sorter_esp32/sorter_esp32.ino',
                        help='Path to sketch (default: firmware/sorter_esp32/sorter_esp32.ino)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  ESP32 Firmware Update Tool — HUSKY-SORTER-001")
    print("=" * 60)
    print()
    
    if args.check_version:
        print("📋 Checking current firmware version...")
        check_current_version(args.port)
        return
    
    if args.verify:
        print("🔍 Verifying firmware binary...")
        verify_firmware(args.verify)
        return
    
    if args.bin:
        verify_firmware(args.bin)
        print()
        
        if args.compile:
            print("🔨 Compile step requested...")
            sketch_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                args.sketch
            )
            if not build_firmware(sketch_path, args.board):
                print("❌ Build failed. Upload cancelled.")
                return
        
        print("📤 Uploading firmware...")
        if upload_firmware(args.port, args.bin):
            print("\n✅ Firmware update complete!")
            print("   Press RST button on ESP32 to restart.")
        else:
            print("\n❌ Firmware update failed.")
            sys.exit(1)
        return
    
    if args.compile:
        print("🔨 Compile only (no upload)...")
        sketch_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            args.sketch
        )
        build_firmware(sketch_path, args.board)
        return
    
    # No action specified - show help
    parser.print_help()


if __name__ == '__main__':
    main()