#!/usr/bin/env python3
"""
Build script for RouteManager
Creates standalone executable for Windows, macOS, and Linux
"""

import subprocess
import sys
import platform

def main():
    print(f"\n{'='*50}")
    print("       RouteManager - Build")
    print(f"{'='*50}")
    print(f"\nPlatform: {platform.system()} ({platform.machine()})")

    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"PyInstaller: {PyInstaller.__version__}")
    except ImportError:
        print("\nPyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "RouteManager",
        "--console",
        "route_manager.py"
    ]

    # Add icon if exists (Windows)
    if platform.system() == "Windows":
        import os
        if os.path.exists("icon.ico"):
            cmd.extend(["--icon", "icon.ico"])

    print(f"\nBuilding...")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print(f"\n{'='*50}")
        print("Build successful!")
        print(f"{'='*50}")

        if platform.system() == "Windows":
            print("\nExecutable: dist/RouteManager.exe")
            print("Note: Run as Administrator (right-click -> Run as administrator)")
        elif platform.system() == "Darwin":
            print("\nExecutable: dist/RouteManager")
            print("Note: Run with sudo: sudo ./dist/RouteManager")
        else:
            print("\nExecutable: dist/RouteManager")
            print("Note: Run with sudo: sudo ./dist/RouteManager")

        print("\nTo distribute, copy the executable from the 'dist' folder.")
    else:
        print("\nBuild failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
