#!/usr/bin/env python3
"""Compose The Journal's 1200×630 share card from the unchanged masthead.

Offline by default: reuse journal-og.json API receipts and local fonts/emblem.
An explicit --refresh makes two real Art API requests, with public text only:
  ART_API_KEY_FILE=/private/key python3 tools/build_og.py --refresh
PNG rasterization requires an existing Chromium executable (--chromium).
No install, service change, browser profile reuse, or image-model generation.
"""
import argparse
import base64
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from build_art import digest, request_art

ROOT = Path(__file__).resolve().parents[1]
CREDIT = 'made by × The VC Agents'
REQUESTS = (
    ('/api/art/stylize', {'text': 'Field notes', 'styles': ['smallCaps']}),
    ('/api/art/transform', {'text': 'The Journal', 'mode': 'decorate', 'style': 'box'}),
)


def data_uri(mime, raw):
    return 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii')


def compose(emblem, display_font, body_font, receipts):
    """Embed the original plate verbatim; API glyphs remain marginal accents."""
    small_caps = json.loads(receipts[0]['response'])['variants']['smallCaps']['preview']
    frame = json.loads(receipts[1]['response'])['result']
    bands = ''.join(f'<text x="56" y="{553 + i * 14}">{escape(line)}</text>'
                    for i, line in enumerate(frame.splitlines()))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="card-title card-desc">
<title id="card-title">The Journal — me·gad·ev</title>
<desc id="card-desc">{CREDIT}. The original Journal emblem, with marginal Art API glyph material.</desc>
<style>
@font-face{{font-family:JournalDisplay;src:url("{data_uri('font/woff2', display_font)}") format('woff2');font-weight:700}}
@font-face{{font-family:JournalBody;src:url("{data_uri('font/woff2', body_font)}") format('woff2');font-weight:400}}
text{{font-family:JournalBody,monospace;fill:#f2f2ee}}
.display{{font-family:JournalDisplay,monospace;font-weight:700;letter-spacing:-3px}}
</style>
<rect width="1200" height="630" fill="#0a0a0a"/>
<path d="M56 132H1144M56 526H1144" stroke="#40403b"/>
<text class="display" x="56" y="79" font-size="29" letter-spacing="-1.16">me·gad·ev<tspan fill="#ff3b30"> /</tspan></text>
<text x="56" y="104" font-size="12" fill="#a6a6af">{CREDIT}</text>
<text x="1144" y="80" text-anchor="end" font-size="15" fill="#a6a6af">{escape(small_caps)}</text>
<text class="display" x="52" y="276" font-size="86">The</text>
<text class="display" x="52" y="377" font-size="86">Journal</text>
<text x="56" y="440" font-size="17" fill="#a6a6af">Building. Working with agents.</text>
<image x="596" y="145" width="548" height="365.333333" href="{data_uri('image/svg+xml', emblem)}"/>
<g font-size="10" fill="#a6a6af">{bands}</g>
<text x="1144" y="578" text-anchor="end" font-size="14" fill="#a6a6af">megadev.div0.space</text>
</svg>
'''.encode('utf-8')


def chromium_path(explicit):
    candidates = [explicit] if explicit else [
        '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
        shutil.which('chromium'), shutil.which('google-chrome'),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError('PNG generation needs an installed Chromium; pass --chromium')


def rasterize(svg, browser, stage):
    document = stage / 'card.html'
    document.write_text('<!doctype html><meta charset="utf-8"><style>'
                        'html,body{margin:0;width:1200px;height:630px;overflow:hidden;}'
                        'svg{display:block}</style>' + svg.decode('utf-8'), encoding='utf-8')
    png = stage / 'journal-og.png'
    result = subprocess.run([
        browser, '--headless', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--disable-background-networking',
        '--force-device-scale-factor=1', '--hide-scrollbars', '--window-size=1200,630',
        '--virtual-time-budget=5000', '--run-all-compositor-stages-before-draw',
        '--user-data-dir=' + str(stage / 'profile'), '--screenshot=' + str(png),
        document.as_uri(),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
    if result.returncode or not png.is_file():
        raise ValueError('Chromium could not render the OG image')
    raw = png.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', raw[16:24]) != (1200, 630):
        raise ValueError('Chromium did not produce a 1200×630 PNG')
    return raw


def build(output, api_base, refresh, chromium):
    manifest_path = output / 'journal-og.json'
    if refresh:
        key = os.environ.get('ART_API_KEY', '')
        if not key and os.environ.get('ART_API_KEY_FILE'):
            key = Path(os.environ['ART_API_KEY_FILE']).read_text().strip()
        if not key:
            raise ValueError('Refresh requires ART_API_KEY or ART_API_KEY_FILE')
        receipts = [request_art(api_base, key, endpoint, parameters)[1]
                    for endpoint, parameters in REQUESTS]
        requested_at = datetime.now(timezone.utc).isoformat()
    else:
        cached = json.loads(manifest_path.read_text())
        if cached['schema'] != 'me-gad-ev.og.v1':
            raise ValueError('Unsupported OG provenance schema')
        receipts, requested_at = cached['requests'], cached['requested_at']
    if len(receipts) != len(REQUESTS):
        raise ValueError('Expected two Art API receipts')
    for receipt, (endpoint, parameters) in zip(receipts, REQUESTS, strict=True):
        if (receipt['endpoint'] != endpoint or receipt['parameters'] != parameters
                or digest(receipt['response'].encode()) != receipt['response_sha256']
                or json.loads(receipt['response']).get('status') != 'ok'):
            raise ValueError('Invalid Art API receipt')
    source_paths = ['docs/assets/art/masthead.svg',
                    'docs/assets/fonts/MonaspaceXenon-Bold.woff2',
                    'docs/assets/fonts/MonaspaceNeon-Regular.woff2']
    sources = [(path, (ROOT / path).read_bytes()) for path in source_paths]
    svg = compose(*(raw for _, raw in sources), receipts)
    with tempfile.TemporaryDirectory(prefix='journal-og-') as temporary:
        png = rasterize(svg, chromium_path(chromium), Path(temporary))
    manifest = {
        'schema': 'me-gad-ev.og.v1', 'requested_at': requested_at,
        'method': 'Authored layout with unchanged embedded masthead and real Art API glyph margins; not image-model output',
        'width': 1200, 'height': 630,
        'sources': [{'path': path, 'sha256': digest(raw)} for path, raw in sources],
        'requests': receipts,
        'assets': [{'path': 'journal-og.svg', 'sha256': digest(svg)},
                   {'path': 'journal-og.png', 'sha256': digest(png)}],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'journal-og.svg').write_bytes(svg)
    (output / 'journal-og.png').write_bytes(png)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('OG generated: 1200×630 PNG + self-contained SVG; '
          + ('two fresh Art API receipts' if refresh else 'offline cached receipts'))
    print('PNG SHA256: ' + digest(png))
    print('Unchanged masthead SHA256: ' + digest(sources[0][1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/assets/art')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--api-base', default=os.environ.get('ART_API_BASE'))
    parser.add_argument('--chromium')
    args = parser.parse_args()
    try:
        if args.refresh and not args.api_base:
            raise ValueError('Refresh requires ART_API_BASE or --api-base')
        build(args.output, args.api_base, args.refresh, args.chromium)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        parser.exit(2, 'journal-og: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
