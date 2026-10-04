import os
import subprocess
import sys


def main() -> None:
    subprocess.run([sys.executable, "scripts/init_db.py"], check=False)
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()