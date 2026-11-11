"""앱 아이콘 생성: 플라스크(Lab) 안에 상승하는 막대(Meta) + 반짝임(조커 발견).

    python tools/make_icon.py

Pillow만 사용한다. 웹/안드로이드/윈도우 아이콘과 앱 내 로고(app/assets/logo.png)를 한 번에 만든다.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent / "app"
S = 2  # 슈퍼샘플 배율 (1024 기준 좌표 × S)
N = 1024 * S

BG_TOP, BG_BOTTOM = (24, 36, 72), (9, 13, 28)
TEAL, AMBER, INK = (79, 209, 197), (246, 185, 74), (234, 242, 255)


def p(*xy):
    return [v * S for v in xy]


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background() -> Image.Image:
    img = Image.new("RGB", (N, N))
    d = ImageDraw.Draw(img)
    for y in range(N):
        d.line([(0, y), (N, y)], fill=lerp(BG_TOP, BG_BOTTOM, y / N))
    # 아래쪽 청록 글로우
    glow = Image.new("L", (N, N), 0)
    ImageDraw.Draw(glow).ellipse(p(212, 520, 812, 1010), fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(90 * S))
    img = Image.composite(Image.new("RGB", (N, N), TEAL), img, glow.point(lambda v: v * 0.45))
    return img.convert("RGBA")


def star(d: ImageDraw.ImageDraw, cx, cy, r, color):
    k = r * 0.26
    d.polygon(p(cx, cy - r, cx + k, cy - k, cx + r, cy, cx + k, cy + k,
                cx, cy + r, cx - k, cy + k, cx - r, cy, cx - k, cy - k), fill=color)


def artwork() -> Image.Image:
    """투명 배경 위의 플라스크 그림 (1024 좌표계)."""
    art = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)
    body = p(440, 236, 440, 430, 262, 748, 762, 748, 584, 430, 584, 236)

    # 플라스크 안쪽을 살짝 채워 유리 느낌
    glass = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(glass).polygon(body, fill=(*TEAL, 34))
    art.alpha_composite(glass)

    # 막대 3개 (왼쪽 → 오른쪽으로 상승)
    bars = [(372, 680, TEAL), (477, 636, lerp(TEAL, AMBER, 0.5)), (582, 592, AMBER)]
    for x, top, color in bars:
        d.rounded_rectangle(p(x, top, x + 70, 744), radius=16 * S, fill=color)

    # 외곽선
    w = 40 * S
    d.line(body + body[:2], fill=INK, width=w, joint="curve")
    r = w // 2
    for i in range(0, len(body), 2):  # 꺾이는 점을 둥글게
        x, y = body[i], body[i + 1]
        d.ellipse([x - r, y - r, x + r, y + r], fill=INK)
    d.rounded_rectangle(p(396, 196, 628, 250), radius=27 * S, fill=INK)  # 입구 테두리
    # 목 안쪽은 비워 둔다 (외곽선이 닫히며 생긴 윗변 제거)
    d.rectangle(p(461, 251, 563, 300), fill=(0, 0, 0, 0))

    star(d, 748, 300, 78, AMBER)
    star(d, 826, 420, 34, TEAL)
    star(d, 250, 330, 30, INK)
    return art


def rounded_mask(radius: int) -> Image.Image:
    m = Image.new("L", (N, N), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, N - 1, N - 1], radius=radius * S, fill=255)
    return m


def compose(scale: float = 1.0, radius: int | None = 224) -> Image.Image:
    img = background()
    art = artwork()
    if scale != 1.0:
        size = round(N * scale)
        small = art.resize((size, size), Image.LANCZOS)
        art = Image.new("RGBA", (N, N), (0, 0, 0, 0))
        art.paste(small, ((N - size) // 2, (N - size) // 2))
    img.alpha_composite(art)
    if radius is not None:
        img.putalpha(ImageChops.multiply(img.getchannel("A"), rounded_mask(radius)))
    return img


def save(img: Image.Image, path: Path, size: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(path)


def main():
    icon = compose()                          # 둥근 사각형 (일반)
    full = compose(scale=0.78, radius=None)   # 여백 있는 정사각형 (maskable)

    save(icon, ROOT / "assets" / "logo.png", 256)
    save(icon, ROOT / "web" / "favicon.png", 64)
    save(icon, ROOT / "web" / "icons" / "Icon-192.png", 192)
    save(icon, ROOT / "web" / "icons" / "Icon-512.png", 512)
    save(full, ROOT / "web" / "icons" / "Icon-maskable-192.png", 192)
    save(full, ROOT / "web" / "icons" / "Icon-maskable-512.png", 512)
    for name, size in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        save(icon, ROOT / "android" / "app" / "src" / "main" / "res" / f"mipmap-{name}" / "ic_launcher.png", size)
    ico = ROOT / "windows" / "runner" / "resources" / "app_icon.ico"
    icon.resize((256, 256), Image.LANCZOS).save(
        ico, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("아이콘 생성 완료")


if __name__ == "__main__":
    main()
