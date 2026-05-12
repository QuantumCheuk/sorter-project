#!/usr/bin/env python3
"""
HUSKY-SORTER-001 - Python 3.14 Compatibility Fix
================================================
Fixes UTF-8 delta characters (Δ = U+0394) that cause parser errors in Python 3.14.

Python 3.14 appears to have a parser change that misinterprets UTF-8 encoded
\xce\x94 (Δ) in string literals within multi-line data structures, causing
"unterminated string literal" errors.

Solution: Replace \xce\x94 (UTF-8 for Δ) with \u0394 (Python unicode escape).
"""

import os
import glob
import re


def find_delta_files(root_dir='sorter'):
    """Find all Python files containing the problematic delta encoding."""
    affected = []
    for path in glob.glob(f'{root_dir}/**/*.py', recursive=True):
        with open(path, 'rb') as f:
            if b'\xce\x94' in f.read():
                affected.append(path)
    return sorted(affected)


def fix_file(path):
    """Replace UTF-8 encoded Δ with Python unicode escape \\u0394."""
    with open(path, 'rb') as f:
        content = f.read()
    
    # Check if file actually has the issue
    if b'\xce\x94' not in content:
        return False
    
    # Check if file is already using \u0394 (no fix needed)
    if b'\\u0394' in content or b'\\u0394' in content:
        return False
    
    # Replace UTF-8 Δ (CE 94) with Python unicode escape \u0394
    # In Python source, we write \u0394 which represents Δ
    fixed = content.replace(b'\xce\x94', b'\\u0394')
    
    # Verify the replacement is correct
    try:
        fixed.decode('utf-8')
    except UnicodeDecodeError:
        print(f"  WARNING: Replacement created invalid UTF-8 in {path}")
        return False
    
    # Write back
    with open(path, 'wb') as f:
        f.write(fixed)
    
    return True


def verify_file(path):
    """Verify file compiles correctly in Python 3.14."""
    import subprocess
    result = subprocess.run(
        ['/usr/local/bin/python3', '-m', 'py_compile', path],
        capture_output=True, text=True
    )
    return result.returncode == 0


def main():
    print("Python 3.14 Delta Character Compatibility Fix")
    print("=" * 50)
    
    # Find affected files
    affected = find_delta_files()
    print(f"\nFound {len(affected)} file(s) with UTF-8 Δ encoding:\n")
    for f in affected:
        print(f"  - {f}")
    
    # Fix each file
    print("\nApplying fixes...")
    fixed_count = 0
    for path in affected:
        if fix_file(path):
            print(f"  ✓ Fixed: {path}")
            fixed_count += 1
        else:
            print(f"  - Skipped: {path}")
    
    print(f"\nFixed {fixed_count}/{len(affected)} file(s)")
    
    # Verify all affected files now compile
    print("\nVerifying syntax with Python 3.14...")
    all_pass = True
    for path in affected:
        if verify_file(path):
            print(f"  ✓ {path}")
        else:
            print(f"  ✗ {path} - STILL FAILS")
            all_pass = False
    
    if all_pass:
        print("\n✅ All files now compile with Python 3.14!")
    else:
        print("\n⚠️  Some files still have issues.")
    
    # Report on remaining Python files (syntax check)
    print("\nFull project syntax check...")
    py_files = glob.glob('sorter/**/*.py', recursive=True)
    fail_count = 0
    for path in py_files:
        if not verify_file(path):
            print(f"  ✗ {path}")
            fail_count += 1
    
    if fail_count == 0:
        print(f"\n✅ All {len(py_files)} Python files pass Python 3.14 syntax check!")
    else:
        print(f"\n⚠️  {fail_count}/{len(py_files)} files still fail.")


if __name__ == '__main__':
    main()
