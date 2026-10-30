#!/usr/bin/env python3
"""Journal art: validate offline by default; --refresh explicitly calls Art API.

ART_API_KEY or ART_API_KEY_FILE supplies build-only authentication. Public text
is the only API input. Manifest receipts pin raw responses and composed SVGs;
these illustrations are authored compositions using API glyph material, not
image-model output. No Forge, upstream generation, or browser API dependency.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

NAMES = ('masthead', 's01e01', 's01e02', 's01e03', 'vc-process', 'divider')
LABELS = ('The Journal', 'First contact', 'Signal and noise', 'Across the threshold', 'Built with VC', 'Continue reading')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['schema'] != 'me-gad-ev.art.v1':
        raise ValueError('Unsupported art manifest schema')
    assets = manifest['assets']
    if {a['path'] for a in assets} != {n + '.svg' for n in NAMES}:
        raise ValueError('Expected exactly six Journal illustrations')
    endpoints = set()
    for asset in assets:
        path = (folder / asset['path']).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Asset escapes output directory')
        raw = path.read_bytes()
        if digest(raw) != asset['sha256']:
            raise ValueError('Artwork checksum mismatch: ' + asset['path'])
        root = ET.fromstring(raw)
        if root.tag != '{http://www.w3.org/2000/svg}svg' or not root.get('viewBox'):
            raise ValueError('Invalid SVG root')
        for node in root.iter():
            if node.tag.rsplit('}', 1)[-1] in ('script', 'foreignObject', 'image'):
                raise ValueError('Non-static SVG content')
            for key, value in node.attrib.items():
                if key.endswith('href') and not value.startswith('#'):
                    raise ValueError('External SVG resource')
        for receipt in asset['requests']:
            endpoints.add(receipt['endpoint'])
            response = receipt['response']
            raw_response = response.encode('utf-8')
            if digest(raw_response) != receipt['response_sha256']:
                raise ValueError('API response checksum mismatch')
            if json.loads(response).get('status') != 'ok':
                raise ValueError('Unsuccessful API receipt')
    if len(endpoints) < 2:
        raise ValueError('At least two Art API families required')
    print('ART OK: six cached SVGs and pinned API receipts; offline, no network')


def request_art(base, key, endpoint, parameters):
    request = Request(base.rstrip('/') + endpoint,
                      data=json.dumps(parameters).encode(),
                      headers={'Content-Type': 'application/json', 'x-api-key': key})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
    except HTTPError as exc:
        raise ValueError(f'Art API {endpoint}: HTTP {exc.code}; refresh stopped') from None
    except (URLError, TimeoutError):
        raise ValueError(f'Art API {endpoint}: connection failed; refresh stopped') from None
    body = json.loads(raw)
    if body.get('status') != 'ok':
        raise ValueError(f'Art API {endpoint}: unsuccessful response')
    return body, {'endpoint': endpoint, 'parameters': parameters,
                  'response_sha256': digest(raw), 'response': raw.decode('utf-8')}


def text(x, y, value, size=20, fill='#f2f2ee', extra=''):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" {extra}>{escape(value)}</text>'


def compose(index, glyphs):
    ivory, red, muted = '#f2f2ee', '#ff3b30', '#55554e'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 640" role="img" aria-labelledby="title desc"><title id="title">{LABELS[index]}</title><desc id="desc">Authored editorial composition using Art API stylize, decorate and emotionize glyphs.</desc><rect width="960" height="640" fill="#101010"/><g font-family="monospace">']
    # Registration marks and fine rules give every plate a print vocabulary.
    for x in range(40, 961, 80):
        parts.append(f'<path d="M{x} 0V640" stroke="{muted}" opacity=".13"/>')
    for y in (40, 600):
        parts.append(f'<path d="M40 {y}H920" stroke="{ivory}" opacity=".35"/>')
    parts += [text(42, 28, f'MG / FIELD NOTES     {index + 1:02d}', 13), text(720, 625, 'ART STUDIES / 26', 12)]
    if index == 0:
        for r in range(240, 30, -28):
            parts.append(f'<circle cx="590" cy="320" r="{r}" fill="none" stroke="{red if r % 3 else ivory}" stroke-width="{2 if r % 3 else 1}"/>')
        parts += ['<path d="M90 470L340 120 590 470Z" fill="#f2f2ee"/><path d="M180 470L340 245 500 470Z" fill="#101010"/>', text(70, 555, glyphs[0], 34), text(690, 315, '01—∞', 46, ivory, 'transform="rotate(90 690 315)"')]
    elif index == 1:
        for row in range(7):
            for col in range(9):
                x, y = 100 + col * 90, 110 + row * 66
                parts.append(f'<circle cx="{x}" cy="{y}" r="{5 + (row * col) % 17}" fill="{red if col == row else ivory}" opacity="{.3 + row / 12}"/>')
        parts += ['<path d="M100 110L640 506" stroke="#ff3b30" stroke-width="4"/>', text(65, 565, glyphs[0], 34)]
    elif index == 2:
        for i in range(36):
            y = 95 + i * 12
            amplitude = 25 + (i % 9) * 14
            parts.append(f'<path d="M70 {y}Q260 {y-amplitude} 440 {y}T890 {y}" fill="none" stroke="{red if i % 5 == 0 else ivory}" opacity=".65"/>')
        parts += ['<rect x="330" y="220" width="300" height="170" fill="#101010" stroke="#ff3b30"/>', text(370, 315, 'SIGNAL', 52), text(65, 565, glyphs[0], 30)]
    elif index == 3:
        for i in range(11):
            inset = i * 22
            parts.append(f'<path d="M{120+inset} 530V{85+inset}H{840-inset}V530" fill="none" stroke="{red if i % 3 == 0 else ivory}" stroke-width="2"/>')
        parts += ['<circle cx="480" cy="375" r="54" fill="#ff3b30"/>', text(65, 565, glyphs[0], 28)]
    elif index == 4:
        for i, label in enumerate(('INTENT', 'MAKE', 'VERIFY')):
            x = 75 + i * 300
            parts += [f'<rect x="{x}" y="200" width="210" height="220" fill="{red if i == 2 else ivory}"/>', text(x+22, 260, f'0{i+1}', 45, '#101010'), text(x+22, 370, label, 24, '#101010')]
            if i < 2:
                parts.append(f'<path d="M{x+215} 310h80m-16-12 16 12-16 12" fill="none" stroke="#ff3b30" stroke-width="3"/>')
        parts += [text(65, 545, glyphs[0], 30)]
    else:
        for i in range(22):
            x = 65 + i * 39
            parts.append(f'<path d="M{x} {210 + (i%4)*20}v{220-(i%4)*40}" stroke="{red if i%3==0 else ivory}" stroke-width="{4+i%6}"/>')
        parts += [text(65, 145, glyphs[0], 30), text(65, 535, 'THE STORY CONTINUES →', 37)]
    # Preserve real returned material as distinct marginal bands, never headings.
    for line_no, line in enumerate(glyphs[1].splitlines()[:3]):
        parts.append(text(60, 65 + line_no * 17, line, 13, '#a6a6af'))
    parts.append(text(915, 565, glyphs[2], 14, '#a6a6af', 'text-anchor="end"'))
    parts.append('</g></svg>\n')
    return ''.join(parts).encode('utf-8')


def refresh(folder, base):
    key = os.environ.get('ART_API_KEY', '')
    if not key and os.environ.get('ART_API_KEY_FILE'):
        key = Path(os.environ['ART_API_KEY_FILE']).read_text().strip()
    if not key:
        raise ValueError('Refresh requires ART_API_KEY or ART_API_KEY_FILE')
    assets = []
    # Complete every request before replacing a previously usable cache.
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        for i, (name, label) in enumerate(zip(NAMES, LABELS, strict=True)):
            style, a = request_art(base, key, '/api/art/stylize', {'text': label, 'styles': ['smallCaps']})
            frame, b = request_art(base, key, '/api/art/transform', {'text': label, 'mode': 'decorate', 'style': 'box'})
            mood, c = request_art(base, key, '/api/art/emotionize', {'text': label, 'mode': 'full', 'emotion': 'curiosity'})
            glyphs = (style['variants']['smallCaps']['preview'], frame['result'], next(v['preview'] for v in mood['variants'] if v['key'] == 'minimal'))
            raw = compose(i, glyphs)
            (stage / (name + '.svg')).write_bytes(raw)
            assets.append({'path': name + '.svg', 'sha256': digest(raw), 'requests': [a, b, c]})
        manifest = {'schema': 'me-gad-ev.art.v1', 'generated_at': datetime.now(timezone.utc).isoformat(), 'method': 'Authored SVG compositions using returned API glyph material', 'assets': assets}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        validate(stage)
        folder.mkdir(parents=True, exist_ok=True)
        for path in stage.iterdir():
            (folder / path.name).write_bytes(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/assets/art')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--api-base', default=os.environ.get('ART_API_BASE'))
    args = parser.parse_args()
    try:
        if args.refresh:
            if not args.api_base:
                raise ValueError('Refresh requires ART_API_BASE or --api-base')
            refresh(args.output, args.api_base)
        else:
            validate(args.output)
    except (OSError, ValueError, KeyError, StopIteration, ET.ParseError) as exc:
        print('ART ERROR: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
