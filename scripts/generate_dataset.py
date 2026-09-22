"""Generates the ReliefMesh synthetic flood dataset (Phase 2).

Run from the project root:  python scripts/generate_dataset.py
"""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataset.build import IMAGES_DIR, SEED_DIR, build_dataset, validate, write_dataset  # noqa: E402


def main() -> int:
    ds = build_dataset()

    errors = validate(ds)
    if errors:
        print("Dataset validation FAILED:")
        for error in errors:
            print("  -", error)
        return 1

    write_dataset(ds)

    langs = Counter(r["language"] for r in ds["reports"])
    prios = Counter(i["expected_priority"] for i in ds["incidents"])
    with_image = sum(1 for r in ds["reports"] if r["image_id"])
    structured = sum(1 for r in ds["reports"] if r["structured"])
    demo = sum(1 for r in ds["reports"] if r["batch"] == "demo")
    available = sum(1 for r in ds["resources"] if r["status"] == "available")

    print("ReliefMesh AI - Phase 2 dataset generator")
    print("-" * 42)
    print(f"Seed files:     {SEED_DIR.relative_to(ROOT)}")
    print(f"Images:         {IMAGES_DIR.relative_to(ROOT)}")
    print(f"Reports:        {len(ds['reports'])}  "
          f"(en={langs['en']}, roman_ur={langs['roman_ur']}, ur={langs['ur']})")
    print(f"  with image: {with_image} | structured: {structured} | demo batch: {demo}")
    print(f"Incidents:      {len(ds['incidents'])}  "
          f"(Critical={prios['Critical']}, High={prios['High']}, "
          f"Medium={prios['Medium']}, Low={prios['Low']})")
    print(f"Resources:      {len(ds['resources'])}  (available: {available})")
    print(f"Shelters:       {len(ds['shelters'])}")
    print(f"Hospitals:      {len(ds['hospitals'])}")
    print(f"Places:         {len(ds['places'])}  (gazetteer)")
    print(f"Blocked roads:  {len(ds['blocked_roads'])}")
    print("-" * 42)
    print("Validation passed. Dataset is ready for Phase 3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
