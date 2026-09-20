"""Checks that your machine is ready for ReliefMesh AI (Phase 1)."""

import sys
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# module name -> pip package name
PACKAGES = {
    "streamlit": "streamlit",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "dotenv": "python-dotenv",
    "requests": "requests",
    "httpx": "httpx",
    "pytest": "pytest",
}


def main() -> int:
    problems = 0
    print("ReliefMesh AI - Phase 1 setup check")
    print("-" * 40)

    # 1. Python version
    py = sys.version_info
    py_text = f"{py.major}.{py.minor}.{py.micro}"
    if py < (3, 10):
        print(f"[FAIL] Python {py_text} is too old. Use 3.11 or 3.12.")
        problems += 1
    elif py >= (3, 13):
        print(f"[WARN] Python {py_text}: works now, but some later libraries may lag.")
    else:
        print(f"[ OK ] Python {py_text}")

    # 2. Virtual environment active?
    if sys.prefix != sys.base_prefix:
        print("[ OK ] Virtual environment is active")
    else:
        print("[FAIL] Virtual environment is NOT active. Run: .venv\\Scripts\\Activate.ps1")
        problems += 1

    # 3. Packages
    for module, package in PACKAGES.items():
        try:
            import_module(module)
            print(f"[ OK ] {package} {version(package)}")
        except (ImportError, PackageNotFoundError):
            print(f"[FAIL] {package} is missing. Run: pip install -r requirements.txt")
            problems += 1

    # 4. .env file
    if Path(".env").exists():
        print("[ OK ] .env file found")
    else:
        print("[WARN] .env not found. Run: copy .env.example .env")

    print("-" * 40)
    if problems == 0:
        print("All checks passed. You are ready for Phase 2.")
        return 0
    print(f"{problems} problem(s) found. Fix them and run this script again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())