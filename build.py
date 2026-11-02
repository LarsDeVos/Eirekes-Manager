#!/usr/bin/env python3
"""
Build Eirekes Manager for the OS you run this on (macOS, Windows or Linux).

    python build.py                # tests + build + zip
    python build.py --install      # first install the build requirements
    python build.py --skip-tests

PyInstaller can't cross-compile: build the Windows app on Windows, the Linux
app on Linux.

Result in src/dist/:
  macOS    Eirekes-manager.app   + Eirekes-Manager-macos-<arch>.zip
  Windows  Eirekes-Manager\\Eirekes-Manager.exe + Eirekes-Manager-windows-<arch>.zip
  Linux    Eirekes-Manager/Eirekes-Manager      + Eirekes-Manager-linux-<arch>.zip
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
DIST = os.path.join(SRC, "dist")
WORK = os.path.join(SRC, "build")
APP_NAME = "Eirekes-Manager"
MAC_APP = "Eirekes-manager.app"


def os_name():
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def run(*cmd, **kwargs):
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def install():
    run(sys.executable, "-m", "pip", "install", "-r",
        os.path.join(ROOT, "requirements-build.txt"))


def run_tests():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    run(sys.executable, "-m", "pytest", "-q", cwd=ROOT, env=env)


def build():
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK, os.path.join(SRC, "main.spec"), cwd=SRC)


def package():
    """Zip the result; returns the zip path."""
    arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    zip_path = os.path.join(DIST, f"{APP_NAME}-{os_name()}-{arch}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    if os_name() == "macos":
        # ditto keeps the symlinks inside the Qt frameworks (zipfile doesn't)
        run("ditto", "-c", "-k", "--keepParent", os.path.join(DIST, MAC_APP), zip_path)
    else:
        shutil.make_archive(zip_path[:-4], "zip", DIST, APP_NAME)
    return zip_path


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--install", action="store_true", help="pip install the build requirements first")
    parser.add_argument("--skip-tests", action="store_true", help="don't run the tests before building")
    parser.add_argument("--no-zip", action="store_true", help="don't make a zip of the result")
    args = parser.parse_args()

    if args.install:
        install()
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller is not installed - run: python build.py --install")

    if not args.skip_tests:
        run_tests()
    build()
    print(f"\nBuilt for {os_name()} in {DIST}")
    if not args.no_zip:
        print(f"Zip: {package()}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"\nFailed: {' '.join(e.cmd)} (exit code {e.returncode})")
