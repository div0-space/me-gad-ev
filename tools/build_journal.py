#!/usr/bin/env python3
"""Publish bilingual trusted editorial sources offline (Python 3.11+).

Supply --public-source content/posts.json --site-source content/site-copy.json
--public-output docs. Members additionally require --private-source and
--private-output; private output must remain outside the checkout. All sources
and destinations are validated before writes. Date-only publication order is
stable across translations and is never changed by edits.
Asset URLs use content hashes from docs/assets, cached only for each publication.
"""
import argparse
from datetime import date
from functools import cache
from hashlib import sha256
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SCHEMA = 'me-gad-ev.journal.v2'
SITE_SCHEMA = 'me-gad-ev.site.v1'
SITE = 'https://megadev.div0.space'
TOKEN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
LANGUAGES = ('en', 'pl')
PAGE_PATHS = {
    'home': '/', 'episodes': '/challenge/',
    's01e01': '/challenge/s01e01/', 's01e02': '/challenge/s01e02/',
    's01e03': '/challenge/s01e03/', 'making-of': '/making-of/', 'gate': '/gate/',
    'privacy': '/privacy/',
}
GATE_IDS = {'agent-prompt', 'copy-prompt', 'copy-status', 'verdict', 'go',
            'retry', 'gate-actions', 'permission', 'public-teasers'}
UI = {
    'pl': {
        'episodes': 'Odcinki', 'ledger': 'Rejestr', 'making': 'Zbudowane z VC',
        'members': 'Dla uczestników', 'signin': 'Zaloguj się',
        'skip': 'Przejdź do treści', 'primary': 'Główna nawigacja', 'languages': 'Język',
        'rss': 'Publiczny RSS', 'author': 'The Journal · opowieści tworzone z agentami',
        'description': 'The Journal: opowieści o budowaniu i pracy z agentami.',
        'protected': 'Zapisy dla uczestników. Dostęp po sprawdzeniu uczestnictwa w kursie.',
        'public_eyebrow': 'Opowieści o pracy z agentami', 'member_eyebrow': 'Zapisy dla uczestników',
        'intro': 'Maciej Gad i agenci: od pomysłu do działającego rozwiązania.',
        'order': 'Od najnowszych publikacji. Aktualizacje nie zmieniają kolejności wpisów.',
        'stories': 'Historie', 'read': 'Czytaj historię', 'historical': 'Zapis archiwalny',
        'minutes': 'min czytania', 'updated': 'Aktualizacja', 'back': 'Wróć do archiwum',
        'newer': 'Nowszy wpis', 'older': 'Starszy wpis', 'article_nav': 'Nawigacja między wpisami',
        'ledger_title': 'Rejestr publikacji', 'outcomes': 'Zapisane wyniki kursu',
        'status_date': 'Stan zapisany 2026-10-30', 'episode': 'Odcinek', 'outcome': 'Zapisany wynik',
        'solved': 'rozwiązany w kursie', 'started': 'rozpoczęty · jeszcze nierozwiązany',
        'methodology': 'Metoda pracy i stan dowodów', 'two_paths': 'Dwie ścieżki czytania',
        'public_path': 'Publiczne historie można czytać bez logowania.',
        'member_path': 'Zapisy dla uczestników są dostępne po zalogowaniu.',
        'privacy': 'Prywatność',
        'independent': 'Niezależny dziennik uczestnika. Bez afiliacji z MEGA.dev / BRAVE Education.',
    },
    'en': {
        'episodes': 'Episodes', 'ledger': 'Ledger', 'making': 'Built with VC',
        'members': 'Members', 'signin': 'Sign in',
        'skip': 'Skip to content', 'primary': 'Primary navigation', 'languages': 'Language',
        'rss': 'Public RSS', 'author': 'The Journal · stories made with agents',
        'description': 'The Journal: stories about building and working with agents.',
        'protected': 'Member records. Access requires course enrollment verification.',
        'public_eyebrow': 'Stories about working with agents', 'member_eyebrow': 'Member records',
        'intro': 'Maciej Gad and agents: from an idea to working software.',
        'order': 'Newest publications first. Edits do not change the order of records.',
        'stories': 'Stories', 'read': 'Read story', 'historical': 'Historical record',
        'minutes': 'min read', 'updated': 'Updated', 'back': 'Return to archive',
        'newer': 'Newer story', 'older': 'Older story', 'article_nav': 'Article navigation',
        'ledger_title': 'Publication ledger', 'outcomes': 'Recorded course outcomes',
        'status_date': 'Status recorded 2026-10-30', 'episode': 'Episode', 'outcome': 'Recorded outcome',
        'solved': 'course solved', 'started': 'started · not solved yet',
        'methodology': 'Working method and evidence status', 'two_paths': 'Two reading paths',
        'public_path': 'Public stories can be read without signing in.',
        'member_path': 'Member records are available after signing in.',
        'privacy': 'Privacy',
        'independent': 'Independent participant journal. Not affiliated with MEGA.dev / BRAVE Education.',
    },
}


class _Body(HTMLParser):
    """Check the source boundary, not sanitize trusted editorial HTML."""
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        if tag in {'html', 'head', 'body', 'main', 'script', 'style', 'base', 'link', 'meta'}:
            raise ValueError('body_html must contain inner-main editorial content only')
        for key, value in attrs:
            if key == 'id':
                if value in self.ids or value in {'main', 'primary-nav'}:
                    raise ValueError('duplicate or reserved body id')
                self.ids.add(value)
            if key.startswith('on'):
                raise ValueError('inline behavior belongs in shared scripts')

    handle_startendtag = handle_starttag


def _translations(record, fields, *, gate=False):
    translations = record.get('translations')
    if not isinstance(translations, dict) or set(translations) != set(LANGUAGES):
        raise ValueError('complete pl and en translations are required')
    for text in translations.values():
        if not isinstance(text, dict) or set(text) != set(fields):
            raise ValueError('invalid translation fields')
        if any(not isinstance(text[key], str) or not text[key].strip() for key in fields):
            raise ValueError('translation fields must be nonempty text')
        body = _Body()
        body.feed(text['body_html'])
        body.close()
        if gate and not GATE_IDS <= body.ids:
            raise ValueError('gate body is missing required interaction IDs')
    return translations


def load_posts(path, audience):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or set(data) != {'schema', 'posts'}
            or data.get('schema') != SCHEMA or not isinstance(data.get('posts'), list)):
        raise ValueError('expected journal v2 posts array')
    ids, slugs = set(), set()
    fields = {'id', 'slug', 'audience', 'published', 'updated', 'sequence', 'episode', 'author', 'translations'}
    for post in data['posts']:
        if not isinstance(post, dict) or set(post) != fields or post.get('audience') != audience:
            raise ValueError('invalid post fields or source audience mismatch')
        for key, seen in [('id', ids), ('slug', slugs)]:
            value = post.get(key)
            if not isinstance(value, str) or not TOKEN.fullmatch(value) or value in seen:
                raise ValueError(f'invalid or duplicate {key}')
            if key == 'id' and value in {'main', 'histories', 'matrix', 'primary-nav'}:
                raise ValueError('reserved archive id')
            seen.add(value)
        for key in ('published', 'updated'):
            value = post.get(key)
            if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('expected ISO date')
            date.fromisoformat(value)
        if post['updated'] < post['published']:
            raise ValueError('update precedes publication')
        if type(post.get('sequence')) is not int or post['sequence'] < 0:
            raise ValueError('sequence must be a nonnegative integer')
        if not isinstance(post['author'], str) or not post['author'].strip():
            raise ValueError('missing author')
        if post['episode'] is not None and not isinstance(post['episode'], str):
            raise ValueError('invalid episode')
        _translations(post, ('title', 'excerpt', 'body_html'))
    return sorted(data['posts'], key=lambda p: (p['published'], p['sequence'], p['id']), reverse=True)


def load_site(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or set(data) != {'schema', 'pages'}
            or data.get('schema') != SITE_SCHEMA or not isinstance(data.get('pages'), dict)
            or set(data['pages']) != set(PAGE_PATHS)):
        raise ValueError('expected site v1 with all required fixed pages')
    for page_id, page in data['pages'].items():
        if not isinstance(page, dict) or set(page) != {'translations'}:
            raise ValueError('invalid site page fields')
        _translations(page, ('title', 'description', 'body_html'), gate=page_id == 'gate')
    return data['pages']


def local_path(path, language):
    """Localize an unlocalized publisher path; assets and gate APIs are separate."""
    if language == 'en':
        return path
    if path.startswith('/members/'):
        return '/members/pl/' + path.removeprefix('/members/')
    return '/pl' + path


def route(post, language='en'):
    return local_path(('/members/journal/' if post['audience'] == 'member' else '/journal/') + post['slug'] + '/', language)


def metadata(post, language='en'):
    ui = UI[language]
    words = len(unescape(re.sub('<[^>]+>', ' ', post['translations'][language]['body_html'])).split())
    episode = escape(post['episode'] or ui['historical'])
    return (f'<div class="post-meta"><time datetime="{post["published"]}">{post["published"]}</time> · '
            f'{escape(post["author"])} · {max(1, (words + 219) // 220)} {ui["minutes"]} · {episode}'
            f' · {ui["updated"]} <time datetime="{post["updated"]}">{post["updated"]}</time></div>')


@cache
def asset_url(name):
    """Version canonical source assets lazily; importing the publisher reads nothing."""
    source = Path(__file__).resolve().parents[1] / 'docs' / 'assets' / name
    return f'/assets/{name}?v={sha256(source.read_bytes()).hexdigest()[:16]}'


def shell(title, content, member=False, *, path='/journal/', description=None, language='en', article_page=False):
    """path is an unlocalized logical route; localize once for links and metadata."""
    ui = UI[language]
    here = local_path(path, language)
    nav = [('The Journal', '/journal/'), (ui['episodes'], '/challenge/'),
           (ui['ledger'], '/journal/#matrix'), (ui['making'], '/making-of/'),
           (ui['members'], '/members/journal/'), (ui['signin'], '/gate/')]
    links = ''
    for text, url in nav:
        current = '#' not in url and (path == url or (url != '/gate/' and path.startswith(url)))
        links += f'<a href="{local_path(url, language)}"' + (' aria-current="page"' if current else '') + f'>{text}</a> '
    languages = ''.join(
        f'<a href="{local_path(path, lang)}" lang="{lang}" hreflang="{lang}" '
        f'aria-label="{"Polski" if lang == "pl" else "English"}"'
        + (' aria-current="page"' if lang == language else '') + f'>{lang.upper()}</a>'
        for lang in LANGUAGES)
    page_title = title if title == 'The Journal' or title.endswith(' — The Journal') else f'{title} — The Journal'
    if member:
        # No member titles, excerpts or permalinks in share metadata.
        page_title = ui['members'] + ' — The Journal'
        head_metadata = f'<meta name="robots" content="noindex, nofollow"><meta name="description" content="{ui["protected"]}">'
    else:
        summary = escape(description or ui['description'], quote=True)
        canonical = escape(SITE + here, quote=True)
        head_metadata = (f'<link rel="canonical" href="{canonical}"><meta name="description" content="{summary}">'
                         f'<meta property="og:type" content="{"article" if article_page else "website"}">'
                         f'<meta property="og:site_name" content="The Journal"><meta property="og:title" content="{escape(page_title, quote=True)}">'
                         f'<meta property="og:description" content="{summary}"><meta property="og:url" content="{canonical}">'
                         f'<meta property="og:locale" content="{"pl_PL" if language == "pl" else "en_GB"}">'
                         f'<meta property="og:image" content="{SITE}{asset_url("art/journal-og.png")}">'
                         f'<meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200">'
                         f'<meta property="og:image:height" content="630"><meta property="og:image:alt" content="The Journal — me·gad·ev. made by × The VC Agents.">'
                         f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{escape(page_title, quote=True)}">'
                         f'<meta name="twitter:description" content="{summary}"><meta name="twitter:image" content="{SITE}{asset_url("art/journal-og.png")}">'
                         f'<meta name="twitter:image:alt" content="The Journal — me·gad·ev. made by × The VC Agents.">')
        head_metadata += ''.join(f'<link rel="alternate" hreflang="{lang}" href="{SITE}{local_path(path, lang)}">' for lang in LANGUAGES)
    gate_assets = ''
    if path == '/gate/':
        gate_assets = f'<meta name="robots" content="noindex"><link rel="stylesheet" href="{asset_url("gate.css")}"><script src="{asset_url("gate.js")}" defer></script>'
        privacy = ('Przed logowaniem przeczytaj informację o administratorze, tokenach i cookies.'
                   if language == 'pl' else
                   'Before signing in, read how the controller handles tokens and cookies.')
        content = (f'<p class="note">{privacy} <a href="{local_path("/privacy/", language)}">'
                   f'{ui["privacy"]}</a>. {ui["independent"]}</p>' + content)
    return f'''<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(page_title)}</title>{head_metadata}
<link rel="stylesheet" href="{asset_url('frontier.css')}"><link rel="stylesheet" href="{asset_url('journal.css')}">
<script src="{asset_url('journal.js')}" defer></script>{gate_assets}
<link rel="alternate" type="application/rss+xml" title="The Journal ({language.upper()})" href="{local_path('/journal/feed.xml', language)}"></head>
<body class="journal-site{' member-site' if member else ''}"><a class="skip-link" href="#main">{ui['skip']}</a>
<header class="site-header"><div class="brand-lockup"><a class="brand" href="{local_path('/', language)}" aria-label="me·gad·ev">me·gad·ev</a><span class="brand-caption">made by × The <a href="https://vetcoders.io">VC</a> <a href="https://vibecrafted.io">Agents</a></span></div>
<nav class="language-switch" aria-label="{ui['languages']}">{languages}</nav>
<button class="menu-toggle" aria-controls="primary-nav" aria-expanded="false" type="button">Menu</button>
<nav class="site-nav" id="primary-nav" aria-label="{ui['primary']}">{links}</nav></header>
<div class="page-shell"><main id="main">{content}</main>
<footer class="site-footer"><p>{ui['author']}</p><p><a href="{local_path('/making-of/', language)}">{ui['making']} / Vibecrafted</a> · <a href="{local_path('/journal/feed.xml', language)}">{ui['rss']}</a></p>
<p>{ui['independent']} · <a href="{local_path('/privacy/', language)}">{ui['privacy']}</a> · <a href="/NOTICE.txt">NOTICE</a></p>
<p>𝚅𝚒𝚋𝚎𝚌𝚛𝚊𝚏𝚝𝚎𝚍. with AI Agents by Vetcoders (c)2024-2026 LibraxisAI</p></footer></div></body></html>
'''


def visual(post):
    if post['id'] not in {'s01e01', 's01e02', 's01e03'}:
        return ''
    return f'<img class="post-visual" src="/assets/art/{post["id"]}.svg" alt="" loading="lazy">'


def archive(posts, member, language='en'):
    ui = UI[language]
    title = ui['members'] + ' — The Journal' if member else 'The Journal'
    root = '/members/journal/' if member else '/journal/'
    content = (f'<header class="page-heading"><p class="eyebrow">{ui["member_eyebrow"] if member else ui["public_eyebrow"]}</p>'
               f'<h1>{title}</h1><p class="standfirst">{ui["intro"]}</p><p class="note">{ui["order"]}</p></header>'
               f'<section id="histories" aria-label="{ui["stories"]}"><div class="post-list">')
    for post in posts:
        text = post['translations'][language]
        content += (f'<article class="post-preview" id="{post["id"]}" data-published="{post["published"]}" data-sequence="{post["sequence"]}" data-audience="{post["audience"]}">'
                    + visual(post) + metadata(post, language) + f'<h2 class="post-title"><a href="{route(post, language)}">{escape(text["title"])}</a></h2>'
                    + f'<p class="post-excerpt">{escape(text["excerpt"])}</p><a class="read-link" href="{route(post, language)}">{ui["read"]} →</a></article>')
    content += '</div></section>'
    if not member:
        content += (f'<section id="matrix"><h2 class="section-heading">{ui["ledger_title"]}</h2>'
                    f'<div class="table-wrap" role="region" aria-label="{ui["outcomes"]}" tabindex="0"><table>'
                    f'<caption>{ui["status_date"]}</caption><thead><tr><th scope="col">{ui["episode"]}</th>'
                    f'<th scope="col">{ui["outcome"]}</th></tr></thead><tbody>')
        for episode in ('s01e01', 's01e02', 's01e03', 's01e04', 's01e05'):
            record = next((post for post in posts if post['id'] == episode), None)
            if record:
                label = f'<a href="{route(record, language)}">{episode.upper()}</a>'
            elif episode in PAGE_PATHS:
                label = f'<a href="{local_path(PAGE_PATHS[episode], language)}">{episode.upper()}</a>'
            else:
                label = episode.upper()
            content += f'<tr><th scope="row">{label}</th><td>{ui["started"] if episode == "s01e05" else ui["solved"]}</td></tr>'
        content += (f'</tbody></table></div><p class="note"><a href="{local_path("/making-of/", language)}#methodology">{ui["methodology"]}</a></p></section>'
                    f'<section><h2>{ui["two_paths"]}</h2><p>{ui["public_path"]} '
                    f'<a href="{local_path("/members/journal/", language)}">{ui["member_path"]}</a></p></section>')
    return shell(title, content, member, path=root, language=language)


def article(posts, index, language='en'):
    post = posts[index]
    text, ui = post['translations'][language], UI[language]
    member = post['audience'] == 'member'
    root = '/members/journal/' if member else '/journal/'
    links = f'<a href="{local_path(root, language)}">← {ui["back"]}</a>'
    if index > 0:
        newer = posts[index - 1]
        links += f' <a rel="prev" href="{route(newer, language)}">{ui["newer"]}: {escape(newer["translations"][language]["title"])}</a>'
    if index + 1 < len(posts):
        older = posts[index + 1]
        links += f' <a rel="next" href="{route(older, language)}">{ui["older"]}: {escape(older["translations"][language]["title"])}</a>'
    content = (f'<article class="article-layout"><header><p class="eyebrow">{ui["members"] if member else "The Journal"}</p>'
               f'<h1 class="article-title">{escape(text["title"])}</h1>{metadata(post, language)}</header>{visual(post)}'
               f'<div class="article-body">{text["body_html"]}</div><nav class="article-nav" aria-label="{ui["article_nav"]}">{links}</nav></article>')
    return shell(text['title'], content, member, path=root + post['slug'] + '/',
                 description=None if member else text['excerpt'], language=language, article_page=True)


def feed(posts, language='en'):
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, text in [('title', 'The Journal'), ('link', SITE + local_path('/journal/', language)),
                      ('description', UI[language]['description']), ('language', language)]:
        ET.SubElement(channel, key).text = text
    for post in posts:
        text = post['translations'][language]
        item = ET.SubElement(channel, 'item')
        for key, value in [('title', text['title']), ('link', SITE + route(post, language)),
                           ('guid', SITE + route(post, language)), ('description', text['excerpt'])]:
            ET.SubElement(item, key).text = value
        # No fabricated time-of-day for date-only source records.
        ET.SubElement(item, '{http://purl.org/dc/elements/1.1/}date').text = post['published']
    return ET.tostring(rss, encoding='unicode', xml_declaration=True)


def agent_index(posts, pages, language):
    if language == 'pl':
        intro = 'Maciej Gad · me·gad·ev. The Journal: opowieści o budowaniu i pracy z agentami.'
        reading, access = 'Czytanie', 'Dostęp do kursu'
        instructions = ('Publiczne strony nie wymagają logowania. Zapisy uczestników są przechowywane poza publicznym katalogiem.\n'
                        'Logowanie: otwórz stronę bramy w tej samej przeglądarce. GET /gate/handshake zwraca dane połączenia.\n'
                        'Użytkownik loguje się i zatwierdza świeże połączenie OAuth w https://hq.mega.dev. Używaj wyłącznie zwróconego adresu /gate/login na tym samym origin.\n'
                        'Backend sprawdza uczestnictwo przez oficjalny MCP, próbuje unieważnić świeże tokeny, usuwa je i ustawia własne ciasteczko HttpOnly.\n'
                        'Nie kopiuj istniejących danych logowania, tokenów ani kodów do rozmowy. GET /gate/check zwraca 200 dla ważnego ciasteczka, w innym przypadku 401.\n'
                        'Błędy nie przyznają dostępu. Statyczna kopia nie zawiera usługi bramy ani prywatnych zapisów.\n')
    else:
        intro = 'Maciej Gad · me·gad·ev. The Journal: stories about building and working with agents.'
        reading, access = 'Read the work', 'Course access'
        instructions = ('Public pages need no login. Member records are held outside the public directory.\n'
                        'Sign in through the gate page in the same browser. GET /gate/handshake returns connection details.\n'
                        'The person signs in and approves a fresh OAuth connection at https://hq.mega.dev. Use only the returned same-origin /gate/login URL.\n'
                        'The backend verifies enrollment through the official MCP, attempts to revoke the fresh tokens, discards them and sets its own HttpOnly cookie.\n'
                        'Never copy existing credentials, tokens or codes into chat. GET /gate/check returns 200 for a valid cookie, otherwise 401.\n'
                        'Errors never grant access. A static copy includes neither the gate service nor private records.\n')
    lines = ['# The Journal', '', intro, '', '## ' + reading, '']
    for page_id, path in PAGE_PATHS.items():
        lines.append(f'- {local_path(path, language)} — {pages[page_id]["translations"][language]["title"]}')
    lines.append(f'- {local_path("/journal/", language)} — The Journal')
    lines.append(f'- {local_path("/journal/feed.xml", language)} — RSS')
    for post in posts:
        lines.append(f'- {route(post, language)} — {post["translations"][language]["title"]}')
    return '\n'.join(lines) + '\n\n## ' + access + '\n\n' + instructions


def build(public_source, public_output, private_source=None, private_output=None, *, site_source):
    asset_url.cache_clear()
    if bool(private_source) != bool(private_output):
        raise ValueError('both private flags are required together')
    public_root = Path(public_output).resolve()
    private_root = Path(private_output).resolve() if private_output else None
    if private_root:
        repo = Path(__file__).resolve().parents[1]
        if public_root == private_root or public_root in private_root.parents or private_root in public_root.parents:
            raise ValueError('output roots overlap')
        if private_root == repo or repo in private_root.parents:
            raise ValueError('private output must remain outside checkout')
        source = Path(private_source).resolve()
        if source == public_root or public_root in source.parents:
            raise ValueError('private source is inside public output')
    public = load_posts(public_source, 'public')
    private = load_posts(private_source, 'member') if private_source else []
    pages = load_site(site_source)
    outputs = []
    for language in LANGUAGES:
        for page_id, path in PAGE_PATHS.items():
            text = pages[page_id]['translations'][language]
            output = public_root / local_path(path, language).lstrip('/') / 'index.html'
            outputs.append((output, public_root, shell(text['title'], text['body_html'], path=path,
                            description=text['description'], language=language)))
        for posts, root, member in [(public, public_root, False), (private, private_root, True)]:
            if root is None:
                continue
            base = root / local_path('/members/journal/' if member else '/journal/', language).lstrip('/')
            outputs.append((base / 'index.html', root, archive(posts, member, language)))
            for index, post in enumerate(posts):
                outputs.append((base / post['slug'] / 'index.html', root, article(posts, index, language)))
            if not member:
                outputs.append((base / 'feed.xml', root, feed(posts, language)))
        outputs.append((public_root / local_path('/llms.txt', language).lstrip('/'), public_root,
                        agent_index(public, pages, language)))
    # Validate the entire bilingual plan before mkdir/write.
    sources = {Path(source).resolve() for source in (public_source, site_source, private_source) if source}
    destinations = set()
    for path, root, _ in outputs:
        destination = path.resolve()
        if root not in destination.parents:
            raise ValueError('output destination escapes its root')
        if destination in sources or destination in destinations:
            raise ValueError('output destination aliases another output or source')
        destinations.add(destination)
        if root == private_root and (public_root == destination or public_root in destination.parents):
            raise ValueError('private destination reaches public output')
        if (path.exists() or path.is_symlink()) and not path.is_file():
            raise ValueError('output destination is not a file')
        if any((parent.exists() or parent.is_symlink()) and not parent.is_dir() for parent in path.parents):
            raise ValueError('output parent is not a directory')
    for path, _, text in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return len(public), len(private)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-source', required=True)
    parser.add_argument('--site-source', required=True)
    parser.add_argument('--public-output', required=True)
    parser.add_argument('--private-source')
    parser.add_argument('--private-output')
    args = parser.parse_args()
    try:
        public, private = build(args.public_source, args.public_output, args.private_source,
                                args.private_output, site_source=args.site_source)
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, f'journal: {error}\n')
    print(f'Published {public} public and {private} member records in PL and EN')


if __name__ == '__main__':
    main()
