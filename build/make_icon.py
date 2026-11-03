"""生成 exe 图标：数据库圆柱图形，多尺寸 ico。"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
OUTPUT = Path(__file__).resolve().parent / "app.ico"


def draw(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    margin = max(1, size // 10)
    width = size - margin * 2
    top = margin
    height = size - margin * 2
    body = (32, 110, 190, 255)
    edge = (255, 255, 255, 255)
    pen.rectangle([margin, top + width // 5, margin + width, top + height - width // 5],
                  fill=body)
    for offset in (0, height - width // 3):
        pen.ellipse([margin, top + offset, margin + width, top + offset + width // 3],
                    fill=body, outline=edge)
    return image


def main() -> None:
    draw(256).save(OUTPUT, format="ICO", sizes=SIZES)
    print("已生成 %s" % OUTPUT)


if __name__ == "__main__":
    main()
