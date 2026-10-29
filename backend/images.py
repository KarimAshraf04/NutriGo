"""Photos of the dishes and healthier swaps.

Admins upload a photo per food_id from the dashboard; it is resized to max 800 px and stored as
backend/static/food_images/<food_id>.jpg. Foods without a photo get a generated PNG card
(category colour + name), so the Flutter app can always show Image.network(image_url).
"""
import io
import os
import textwrap
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.environ.get("NUTRIGO_IMAGE_DIR", os.path.join(HERE, "static", "food_images"))
MAX_SIDE = 800

CATEGORY_COLORS = {
    "Appetizer": "#c0703a", "Breakfast": "#d39b2a", "Dessert": "#c2547a", "Fast food": "#c0392b",
    "Meat": "#8e4a2f", "Pasta": "#c98a1b", "Rice & noodles": "#a5762a", "Salad": "#3f8f4f",
    "Sandwich": "#b7652f", "Seafood": "#2f7b9e", "Snack": "#7a5ba8", "Soup": "#c46a2c",
}


class ImageStore:
    def __init__(self, image_dir=IMAGE_DIR):
        self.image_dir = image_dir

    def path(self, food_id):
        return os.path.join(self.image_dir, f"{food_id}.jpg")

    def find(self, food_id):
        p = self.path(food_id)
        return p if os.path.exists(p) else None

    def version(self, food_id):
        """Changes when the photo changes, so apps don't keep showing a cached old one."""
        p = self.find(food_id)
        return int(os.path.getmtime(p)) if p else 0

    def save(self, food_id, data):
        """Check the upload is a real image, then store it as a resized JPEG (also drops EXIF/GPS)."""
        from PIL import Image, ImageOps
        Image.open(io.BytesIO(data)).verify()
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        os.makedirs(self.image_dir, exist_ok=True)
        tmp = self.path(food_id) + ".tmp"
        img.save(tmp, "JPEG", quality=85)
        os.replace(tmp, self.path(food_id))

    def delete(self, food_id):
        p = self.find(food_id)
        if p:
            os.remove(p)


@lru_cache(maxsize=512)
def placeholder_png(name, category, size=(600, 400)):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", size, CATEGORY_COLORS.get(category, "#2e7d4f"))
    draw = ImageDraw.Draw(img)
    title, small = ImageFont.load_default(size=44), ImageFont.load_default(size=24)
    lines = textwrap.wrap(name, 18)[:3]
    heights = [draw.textbbox((0, 0), l, font=title)[3] for l in lines]
    y = (size[1] - sum(heights) - 12 * (len(lines) - 1)) / 2 - 10
    for line, h in zip(lines, heights):
        w = draw.textlength(line, font=title)
        draw.text(((size[0] - w) / 2, y), line, font=title, fill="white")
        y += h + 12
    w = draw.textlength(category.upper(), font=small)
    draw.text(((size[0] - w) / 2, size[1] - 56), category.upper(), font=small, fill=(255, 255, 255, 200))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def thumbnail_data_uri(data, side=480):
    """Small JPEG of an uploaded photo for showing it back on a page (not stored)."""
    import base64
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
