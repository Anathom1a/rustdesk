#!/usr/bin/env python3
"""Иконки сайта и картинка для превью ссылок — из фирменного знака.

Рисует Chromium (тот же, что у Playwright) по HTML-шаблонам, PIL собирает
favicon.ico. Результат кладётся в репозиторий, поэтому при сборке сайта
ничего не генерируется:

    app/icon.svg          значок вкладки (современные браузеры)
    app/favicon.ico       16/32/48 — старые браузеры и Яндекс
    app/apple-icon.png    180×180 — ярлык на iPhone/iPad
    public/icon-192.png   иконки для manifest.webmanifest (Android)
    public/icon-512.png
    public/og.png         1200×630 — превью ссылки в мессенджерах и соцсетях
    public/email-logo.png логотип в шапке писем (белый, 2×)
    public/bimi.svg       значок отправителя для BIMI (SVG Tiny PS)

Запуск из корня репозитория:

    python3 client/brand/generate-site-assets.py [--chrome путь/к/chrome]
"""

from __future__ import annotations

import argparse
import base64
import glob
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BRAND = Path(__file__).resolve().parent

INK = '#0c0e10'
TEAL_DARK = '#0d9488'
TEAL = '#2dd4bf'

# Знак из client/brand/icon.svg, обрезанный по контуру: в маленьком значке
# вкладки каждый пиксель на счету.
GLYPH = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="46 46 164 164">
  <defs>
    <linearGradient id="remit" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{TEAL_DARK}"/>
      <stop offset="1" stop-color="{TEAL}"/>
    </linearGradient>
  </defs>
  <rect x="51.2" y="65.8" width="153.6" height="112.6" rx="19.2" fill="url(#remit)"/>
  <rect x="94.7" y="178.4" width="66.6" height="14.1" rx="5.1" fill="url(#remit)"/>
  <rect x="90.9" y="114.2" width="48.6" height="15.9" rx="7.9" fill="{INK}"/>
  <path d="M169.0 122.1 133.1 95.2v53.8Z" fill="{INK}"/>
</svg>
'''


def glyph_uri() -> str:
    return 'data:image/svg+xml;base64,' + base64.b64encode(GLYPH.encode()).decode()


def font_face() -> str:
    faces = []
    for weight, name in [(400, 'Regular'), (500, 'Medium'), (600, 'SemiBold'), (700, 'Bold')]:
        data = base64.b64encode((BRAND / 'fonts' / f'Inter-{name}.ttf').read_bytes()).decode()
        faces.append(
            f"@font-face{{font-family:Inter;font-weight:{weight};src:url(data:font/ttf;base64,{data}) format('truetype')}}"
        )
    return '\n'.join(faces)


def tile_html(size: int, padding: float, background: str | None) -> str:
    """Знак на квадрате: прозрачном (значок вкладки) или тёмном (ярлыки)."""
    inner = size * (1 - 2 * padding)
    bg = f'background:{background};' if background else 'background:transparent;'
    return f'''<!doctype html><html><head><style>
html,body{{margin:0;width:{size}px;height:{size}px;overflow:hidden;{bg}}}
body{{display:flex;align-items:center;justify-content:center}}
img{{width:{inner}px;height:{inner}px}}
</style></head><body><img src="{glyph_uri()}"></body></html>'''


def og_html() -> str:
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
{font_face()}
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
body{{
  font-family:Inter,sans-serif;color:#e9ecef;background:{INK};position:relative;
  background-image:
    radial-gradient(640px 360px at 12% 0%, rgba(20,184,166,.30), transparent 70%),
    radial-gradient(560px 340px at 92% 100%, rgba(94,234,212,.18), transparent 70%);
}}
.grid{{position:absolute;inset:0;
  background-image:linear-gradient(to right,rgba(233,236,239,.05) 1px,transparent 1px),
                   linear-gradient(to bottom,rgba(233,236,239,.05) 1px,transparent 1px);
  background-size:48px 48px;
  -webkit-mask-image:radial-gradient(900px 520px at 30% 30%,#000 40%,transparent 100%)}}
.wrap{{position:absolute;inset:0;padding:72px 80px;display:flex;flex-direction:column}}
.brand{{display:flex;align-items:center;gap:20px}}
.brand .domain{{font-size:30px}}
.brand img{{width:76px;height:76px}}
.brand span{{font-size:46px;font-weight:700;letter-spacing:-.5px}}
h1{{margin:56px 0 0;font-size:74px;line-height:1.05;font-weight:700;letter-spacing:-1.5px;
  background:linear-gradient(120deg,#e9ecef 15%,{TEAL} 65%,#5eead4 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;max-width:980px}}
p{{margin:26px 0 0;font-size:31px;line-height:1.35;color:#a8b0ba;max-width:960px}}
.chips{{margin-top:auto;display:flex;gap:14px;align-items:center}}
.chip{{font-size:24px;font-weight:500;padding:12px 22px;border-radius:999px;white-space:nowrap;flex-shrink:0;
  border:1px solid rgba(45,212,191,.35);background:rgba(20,184,166,.10);color:#d6f5f0}}
.domain{{margin-left:auto;font-size:30px;font-weight:600;color:{TEAL}}}
</style></head><body><div class="grid"></div><div class="wrap">
<div class="brand"><img src="{glyph_uri()}"><span>RemIT</span><span class="domain">remit.su</span></div>
<h1>Удалённый доступ к&nbsp;компьютеру</h1>
<p>Подключение по ID и паролю без VPN. Техподдержка, работа из дома, помощь близким.</p>
<div class="chips">
  <span class="chip">Windows · macOS · Linux</span>
  <span class="chip">Серверы в России</span>
  <span class="chip">Есть бесплатный тариф</span>
</div>
</div></body></html>'''


def email_logo_html() -> str:
    """Логотип для шапки писем: знак и «RemIT» белым, прозрачный фон, 2×."""
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
{font_face()}
html,body{{margin:0;width:280px;height:72px;overflow:hidden;background:transparent}}
body{{display:flex;align-items:center;gap:16px;font-family:Inter,sans-serif}}
img{{width:64px;height:64px}}
span{{font-size:44px;font-weight:700;color:#ffffff;letter-spacing:-.5px}}
</style></head><body><img src="{glyph_uri()}"><span>RemIT</span></body></html>'''


# Логотип для BIMI (значок отправителя в почтовых сервисах): SVG Tiny PS —
# квадрат, сплошные цвета, <title>, без скриптов и внешних ссылок.
BIMI = f'''<svg xmlns="http://www.w3.org/2000/svg" version="1.2" baseProfile="tiny-ps" viewBox="0 0 512 512">
  <title>RemIT</title>
  <rect width="512" height="512" fill="{INK}"/>
  <g transform="translate(58 58) scale(1.55)">
    <rect x="51.2" y="65.8" width="153.6" height="112.6" rx="19.2" fill="#14b8a6"/>
    <rect x="94.7" y="178.4" width="66.6" height="14.1" rx="5.1" fill="#14b8a6"/>
    <rect x="90.9" y="114.2" width="48.6" height="15.9" rx="7.9" fill="{INK}"/>
    <path d="M169.0 122.1 133.1 95.2v53.8Z" fill="{INK}"/>
  </g>
</svg>
'''


def find_chrome(explicit: str | None) -> str:
    candidates = [explicit] if explicit else []
    candidates += glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')
    candidates += [shutil.which(name) for name in ('chromium', 'chromium-browser', 'google-chrome')]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise SystemExit('Не найден Chromium: укажите --chrome')


def render(chrome: str, html: str, width: int, height: int, out: Path, transparent: bool = False) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / 'page.html'
        page.write_text(html, encoding='utf-8')
        shot = Path(tmp) / 'shot.png'
        # У headless-окна есть минимальный размер, а видимая область меньше
        # заданной на высоту служебной панели. Рисуем в заведомо большом окне
        # (страница — фиксированного размера в левом верхнем углу) и вырезаем.
        args = [
            chrome, '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
            '--force-device-scale-factor=1', f'--window-size={max(width, 800) + 200},{height + 400}',
            f'--screenshot={shot}', page.as_uri(),
        ]
        if transparent:
            args.insert(1, '--default-background-color=00000000')
        subprocess.run(args, check=True, capture_output=True, timeout=60)
        with Image.open(shot) as image:
            image.crop((0, 0, width, height)).save(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--chrome')
    args = parser.parse_args()
    chrome = find_chrome(args.chrome)

    app = ROOT / 'app'
    public = ROOT / 'public'
    (app / 'icon.svg').write_text(GLYPH, encoding='utf-8')

    with tempfile.TemporaryDirectory() as tmp:
        big = Path(tmp) / 'glyph.png'
        render(chrome, tile_html(256, 0.02, None), 256, 256, big, transparent=True)
        with Image.open(big) as image:
            image = image.convert('RGBA')
            buffer = io.BytesIO()
            image.save(buffer, format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
            (app / 'favicon.ico').write_bytes(buffer.getvalue())

    # Ярлыки — на тёмном фоне: iOS и Android сами скругляют углы, а прозрачный
    # фон iOS заливает чёрным. Отступы — с запасом для «maskable» на Android.
    render(chrome, tile_html(180, 0.14, INK), 180, 180, app / 'apple-icon.png')
    render(chrome, tile_html(192, 0.2, INK), 192, 192, public / 'icon-192.png')
    render(chrome, tile_html(512, 0.2, INK), 512, 512, public / 'icon-512.png')
    render(chrome, og_html(), 1200, 630, public / 'og.png')
    render(chrome, email_logo_html(), 280, 72, public / 'email-logo.png', transparent=True)
    (public / 'bimi.svg').write_text(BIMI, encoding='utf-8')

    for path in [app / 'icon.svg', app / 'favicon.ico', app / 'apple-icon.png',
                 public / 'icon-192.png', public / 'icon-512.png', public / 'og.png',
                 public / 'email-logo.png', public / 'bimi.svg']:
        print(f'{path.relative_to(ROOT)}: {path.stat().st_size} байт')


if __name__ == '__main__':
    main()
