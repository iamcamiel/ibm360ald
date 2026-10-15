import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops

root = Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/native-three-review/independent-review")
manifest = json.loads(Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/native-three-review/unified-stage/Unified native three correction manifest.json").read_text(encoding="utf-8"))
width, height = 600, 360
out = Image.new("RGB", (width, height * 3), "white")
draw = ImageDraw.Draw(out)
for i, page in enumerate(manifest["pages"]):
    before = Image.open(page["before_quartet"]["preview"]["path"]).convert("RGB")
    after = Image.open(page["candidate_quartet"]["preview"]["path"]).convert("RGB")
    x0, y0, x1, y1 = ImageChops.difference(before, after).getbbox()
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    box = (cx - 145, cy - 120, cx + 145, cy + 120)
    out.paste(before.crop(box), (0, i * height + 30))
    out.paste(after.crop(box), (300, i * height + 30))
    draw.text((5, i * height + 5), page["page"] + " predecessor", fill="black")
    draw.text((305, i * height + 5), page["page"] + " candidate", fill="black")
out.save(root / "Three page preview before-after contact.png")
