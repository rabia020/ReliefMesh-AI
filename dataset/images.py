"""Draws simple placeholder 'photos' for the demo (SIMULATED).

They are cartoon-style illustrations, so there are no copyright problems.
In Phase 18 you may replace them with real Creative-Commons flood photos
using the same file names.
"""

from pathlib import Path

from PIL import Image, ImageDraw

W, H = 640, 400
SKY = (198, 219, 235)
WATER = (70, 130, 180)
MUD = (139, 115, 85)
SKIN = (230, 190, 150)


def _water(d, top):
    d.rectangle([0, top, W, H - 24], fill=WATER)
    for x in range(0, W, 48):
        d.arc([x, top + 8, x + 32, top + 24], 0, 180, fill=(210, 230, 245))


def _person(d, x, y):
    d.ellipse([x - 5, y - 14, x + 5, y - 4], fill=SKIN)
    d.rectangle([x - 4, y - 4, x + 4, y + 10], fill=(200, 60, 60))


def _car(d, x, y, color):
    d.rectangle([x, y, x + 50, y + 18], fill=color)
    d.rectangle([x + 10, y - 10, x + 38, y], fill=color)


def _scene_bridge(d):
    _water(d, 190)
    d.rectangle([40, 150, 600, 172], fill=(90, 90, 90))
    for x in (120, 300, 480):
        d.rectangle([x, 172, x + 18, 190], fill=(70, 70, 70))
    _car(d, 80, 132, (200, 40, 40))
    _car(d, 170, 132, (40, 80, 200))
    for x in (400, 420, 440, 460, 480, 500):
        _person(d, x, 148)


def _scene_rooftops(d):
    _water(d, 230)
    for x in (40, 240, 440):
        d.rectangle([x, 200, x + 140, 260], fill=(200, 180, 150))
        d.polygon([(x - 10, 200), (x + 70, 150), (x + 150, 200)], fill=(150, 60, 50))
        _person(d, x + 55, 180)
        _person(d, x + 80, 184)
    _water(d, 250)


def _scene_wall(d):
    d.rectangle([0, 260, W, H - 24], fill=MUD)
    d.rectangle([40, 170, 260, 260], fill=(160, 160, 160))
    d.rectangle([380, 170, 600, 260], fill=(160, 160, 160))
    for i in range(12):
        x = 270 + (i % 6) * 17
        y = 240 + (i // 6) * 12
        d.rectangle([x, y, x + 14, y + 10], fill=(120, 120, 120))
    _person(d, 320, 232)
    _person(d, 350, 232)
    _water(d, 340)


def _scene_bus(d):
    d.rectangle([0, 60, W, H - 24], fill=(60, 60, 70))
    d.rectangle([150, 150, 470, 250], fill=(240, 190, 30))
    for x in range(165, 455, 55):
        d.rectangle([x, 165, x + 40, 195], fill=(180, 220, 240))
    _water(d, 205)
    for x in (180, 235, 290, 345, 400):
        d.ellipse([x + 12, 172, x + 28, 188], fill=SKIN)


def _scene_embankment(d):
    _water(d, 300)
    d.polygon([(0, 300), (120, 150), (520, 150), (640, 300)], fill=MUD)
    d.line([(300, 150), (310, 190), (292, 225), (308, 260), (298, 300)], fill=(40, 30, 20), width=4)
    for y in (225, 260, 285):
        d.line([(296, y), (290, y + 15)], fill=WATER, width=3)


def _scene_debris(d):
    d.rectangle([0, 220, W, 330], fill=(85, 85, 85))
    for x in range(0, W, 60):
        d.rectangle([x, 272, x + 30, 278], fill=(240, 240, 240))
    _water(d, 330)
    d.polygon([(200, 240), (440, 300), (440, 316), (200, 256)], fill=(101, 67, 33))
    for x, y in ((230, 235), (280, 250), (340, 270)):
        d.ellipse([x - 30, y - 30, x + 30, y + 20], fill=(40, 120, 50))
    for x in (450, 480, 510):
        d.rectangle([x, 300, x + 18, 312], fill=(120, 100, 80))


SCENES = {
    "bridge": _scene_bridge,
    "rooftops": _scene_rooftops,
    "wall": _scene_wall,
    "bus": _scene_bus,
    "embankment": _scene_embankment,
    "debris": _scene_debris,
}

# 'expected' is what a perfect image analyser should find (used in Phase 18).
IMAGE_SPECS = [
    {"id": "IMG-01", "file": "bridge_flood.png", "report_id": "R-004", "scene": "bridge",
     "caption": "Flooded bridge, cars stuck, people on the deck (simulated illustration)",
     "expected": {"flood_water": True, "blocked_road": True, "damaged_structure": False,
                  "vehicles": True, "crowding": True,
                  "hazards": ["rising water", "stranded people"]}},
    {"id": "IMG-02", "file": "rooftops_flood.png", "report_id": "R-011", "scene": "rooftops",
     "caption": "Village flooded up to the roofs, people on rooftops (simulated illustration)",
     "expected": {"flood_water": True, "blocked_road": True, "damaged_structure": False,
                  "vehicles": False, "crowding": True,
                  "hazards": ["deep water", "stranded people"]}},
    {"id": "IMG-03", "file": "wall_collapse.png", "report_id": "R-019", "scene": "wall",
     "caption": "Collapsed boundary wall with rubble and people nearby (simulated illustration)",
     "expected": {"flood_water": True, "blocked_road": False, "damaged_structure": True,
                  "vehicles": False, "crowding": False,
                  "hazards": ["rubble", "possible injuries"]}},
    {"id": "IMG-04", "file": "bus_underpass.png", "report_id": "R-022", "scene": "bus",
     "caption": "Bus in flooded underpass, water up to the windows (simulated illustration)",
     "expected": {"flood_water": True, "blocked_road": True, "damaged_structure": False,
                  "vehicles": True, "crowding": True,
                  "hazards": ["passengers trapped", "rising water"]}},
    {"id": "IMG-05", "file": "embankment_crack.png", "report_id": "R-028", "scene": "embankment",
     "caption": "Embankment with a crack and seepage, NOT a full breach (simulated illustration)",
     "expected": {"flood_water": True, "blocked_road": False, "damaged_structure": True,
                  "vehicles": False, "crowding": False,
                  "hazards": ["crack", "seepage", "possible breach"]}},
    {"id": "IMG-06", "file": "blocked_road_debris.png", "report_id": "R-039", "scene": "debris",
     "caption": "Road blocked by a fallen tree and debris (simulated illustration)",
     "expected": {"flood_water": True, "blocked_road": True, "damaged_structure": False,
                  "vehicles": False, "crowding": False,
                  "hazards": ["fallen tree", "debris"]}},
]


def generate_images(images_dir: Path) -> None:
    images_dir.mkdir(parents=True, exist_ok=True)
    for spec in IMAGE_SPECS:
        img = Image.new("RGB", (W, H), SKY)
        d = ImageDraw.Draw(img)
        SCENES[spec["scene"]](d)
        d.rectangle([0, 0, W, 26], fill=(30, 30, 30))
        d.text((8, 8), "SIMULATED IMAGE - ReliefMesh demo data", fill=(255, 255, 255))
        d.rectangle([0, H - 24, W, H], fill=(30, 30, 30))
        d.text((8, H - 17), spec["caption"], fill=(255, 255, 255))
        img.save(images_dir / spec["file"])
