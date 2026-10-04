"""Pre-deployment safety check. Run from the project root:  python preflight.py
Exit code 0 = ready, 1 = something must be fixed first.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SECRET_PATTERNS = {
    "Groq API key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "Hugging Face token": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".db", ".sqlite", ".pyc", ".pdf",
                 ".zip", ".ico", ".woff", ".woff2", ".ttf", ".parquet", ".duckdb"}
REQUIRED_PACKAGES = ["fastapi", "uvicorn", "httpx", "mcp", "ortools", "pillow", "python-multipart"]
WANTED_PACKAGES = ["streamlit", "python-dotenv", "pytest"]

results = []


def record(level, message):
    results.append((level, message))
    print(f"[{level}] {message}")


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        return None


def package_names(text):
    names = set()
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[=<>~!;\[ ]", line)[0]
        names.add(name.lower().replace("_", "-"))
    return names


def main():
    # 1. documentation of settings
    if (ROOT / ".env.example").exists():
        record("OK", ".env.example exists")
    else:
        record("FAIL", ".env.example is missing (it documents the settings without secrets)")

    # 2. requirements
    req = ROOT / "requirements.txt"
    if req.exists():
        names = package_names(req.read_text(encoding="utf-8", errors="ignore"))
        missing = [p for p in REQUIRED_PACKAGES if p not in names]
        record("FAIL" if missing else "OK",
               f"requirements.txt is missing: {', '.join(missing)}" if missing
               else "requirements.txt lists the core packages")
        wanted = [p for p in WANTED_PACKAGES if p not in names]
        if wanted:
            record("WARN", f"requirements.txt does not list: {', '.join(wanted)}")
    else:
        record("FAIL", "requirements.txt is missing")

    # 3. git checks
    inside = git("rev-parse", "--is-inside-work-tree")
    if inside is None:
        record("WARN", "git is not installed, so the secret checks were skipped")
    elif inside.returncode != 0:
        record("WARN", "This folder is not a git repository yet (run: git init). Secret checks skipped")
    else:
        ignored = git("check-ignore", "-q", ".env")
        record("OK" if ignored.returncode == 0 else "FAIL",
               ".env is ignored by git" if ignored.returncode == 0
               else ".env is NOT ignored. Add a line '.env' to .gitignore")

        tracked_env = git("ls-files", "--error-unmatch", ".env")
        record("FAIL" if tracked_env.returncode == 0 else "OK",
               ".env is tracked by git! Run: git rm --cached .env" if tracked_env.returncode == 0
               else ".env is not tracked")

        files = git("ls-files").stdout.splitlines()
        found = []
        for name in files:
            path = ROOT / name
            if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                for label, pattern in SECRET_PATTERNS.items():
                    if pattern.search(line):
                        found.append(f"{name}:{number} looks like a {label}")
        if found:
            for item in found:
                record("FAIL", item)
            record("FAIL", "Remove these secrets, and rotate (replace) any key that was ever committed")
        else:
            record("OK", f"No secret-looking text in {len(files)} tracked files")

        photos = git("ls-files", "data/sample_images").stdout.split()
        record("WARN" if photos else "OK",
               "Sample photos are tracked by git (check you have the rights to publish them)" if photos
               else "No sample photos are tracked")
        databases = [f for f in files if f.endswith((".db", ".sqlite"))]
        record("OK", "Database files tracked by git: " + (", ".join(databases) or "none"))

        gitignore = (ROOT / ".gitignore")
        if gitignore.exists() and ".venv" in gitignore.read_text(encoding="utf-8", errors="ignore"):
            record("OK", ".venv is ignored")
        else:
            record("WARN", ".gitignore does not mention .venv")

    failed = sum(1 for level, _ in results if level == "FAIL")
    warned = sum(1 for level, _ in results if level == "WARN")
    print(f"\n{failed} problem(s), {warned} warning(s).")
    print("READY to publish." if failed == 0 else "FIX the problems above before you publish.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())