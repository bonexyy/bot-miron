import random
from io import BytesIO
from PIL import Image, ImageDraw


def make_puzzle(image_bytes: bytes, grid: int = 3, tile_size: int = 300):
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = img.resize((tile_size * grid, tile_size * grid))

    tiles = []
    for y in range(grid):
        for x in range(grid):
            box = (x * tile_size, y * tile_size,
                   (x + 1) * tile_size, (y + 1) * tile_size)
            tiles.append((y * grid + x + 1, img.crop(box)))

    shuffled = tiles.copy()
    random.shuffle(shuffled)

    canvas = Image.new("RGB", (tile_size * grid, tile_size * grid))
    draw = ImageDraw.Draw(canvas)

    for i, (num, tile) in enumerate(shuffled):
        x = (i % grid) * tile_size
        y = (i // grid) * tile_size
        canvas.paste(tile, (x, y))
        draw.rectangle([x, y, x + 45, y + 45], fill="black")
        draw.text((x + 12, y + 10), str(num), fill="white")

    out = BytesIO()
    canvas.save(out, format="JPEG", quality=85)

    correct_order = list(range(1, grid * grid + 1))
    return out.getvalue(), correct_order


def check_puzzle(user_answer: str, correct_order) -> bool:
    try:
        nums = [int(x) for x in user_answer.split()]
    except ValueError:
        return False
    return nums == correct_order