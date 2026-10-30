"""Behavior regressions for bilingual publication and audience isolation."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from build_journal import archive, build, load_posts, PAGE_PATHS


def post(name, published='2026-10-28', sequence=1, audience='public'):
    return dict(id=name, slug=name, published=published, updated=published,
                sequence=sequence, audience=audience, author='Editor', episode=None,
                translations={language: dict(title=f'{name} {language}',
                    excerpt=f'Introduction {language}.', body_html=f'<p>Editorial record {language}.</p>')
                    for language in ('pl', 'en')})


def site_copy():
    pages = {page_id: dict(translations={language: dict(title=f'{page_id} {language}',
                description=f'Description {language}.', body_html=f'<h1>{page_id} {language}</h1>')
                for language in ('pl', 'en')}) for page_id in PAGE_PATHS}
    gate = ('<pre><code id="agent-prompt" tabindex="0">Prompt</code></pre>'
            '<button id="copy-prompt">Copy</button><p id="copy-status"></p>'
            '<div id="gate-actions"><button id="go" disabled>Sign in</button>'
            '<button id="retry" hidden>Retry</button></div>'
            '<p id="verdict"></p><p id="permission"></p><a id="public-teasers" href="/challenge/">Public</a>')
    for text in pages['gate']['translations'].values():
        text['body_html'] += gate
    return dict(schema='me-gad-ev.site.v1', pages=pages)


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.head_links, self.language = [], [], None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        elif tag == 'a':
            self.links.append(attrs)
        elif tag == 'link':
            self.head_links.append(attrs)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'public.json'
        self.private = self.root / 'private.json'
        self.site = self.root / 'site.json'
        self.out = self.root / 'public'
        self.members = self.root / 'private'
        self.site.write_text(json.dumps(site_copy()))

    def save(self, path, posts):
        path.write_text(json.dumps(dict(schema='me-gad-ev.journal.v2', posts=posts)))

    def publish(self, private=False):
        return build(self.source, self.out, self.private if private else None,
                     self.members if private else None, site_source=self.site)

    def assert_no_outputs(self):
        self.assertFalse(self.out.exists())
        self.assertFalse(self.members.exists())

    def test_publication_order_ignores_edits_and_breaks_ties(self):
        old = post('old')
        old['updated'] = '2026-10-30'
        posts = [old, post('a', '2026-10-29', 2), post('b', '2026-10-29', 2), post('first', '2026-10-29', 1)]
        self.save(self.source, posts)
        self.assertEqual([p['id'] for p in load_posts(self.source, 'public')], ['b', 'a', 'first', 'old'])
        self.publish()
        for prefix, language in [('', 'en'), ('pl/', 'pl')]:
            archive = (self.out / prefix / 'journal/index.html').read_text()
            self.assertLess(archive.index('id="b"'), archive.index('id="old"'))
            self.assertNotIn(f'Editorial record {language}.', archive)
            middle = (self.out / prefix / 'journal/a/index.html').read_text()
            self.assertIn(f'href="/{prefix}journal/b/"', middle)
            self.assertIn(f'href="/{prefix}journal/first/"', middle)
            feed = ET.parse(self.out / prefix / 'journal/feed.xml')
            self.assertEqual([item.text for item in feed.findall('./channel/item/title')],
                             [f'{name} {language}' for name in ('b', 'a', 'first', 'old')])

    def test_private_failure_writes_nothing_public(self):
        self.save(self.source, [post('safe')])
        self.save(self.private, [post('secret', audience='public')])
        with self.assertRaises(ValueError):
            self.publish(private=True)
        self.assert_no_outputs()

    def test_wrong_public_audience_and_invalid_records(self):
        original = post('safe')
        invalid = [dict(audience='member'), dict(slug='../escape'), dict(id='bad/id'),
                   dict(published='2026-02-30'), dict(updated='20261029'), dict(sequence=True),
                   dict(title='Obsolete top-level translation')]
        for changes in invalid:
            with self.subTest(changes=changes):
                value = copy.deepcopy(original)
                value.update(changes)
                self.save(self.source, [value])
                with self.assertRaises(ValueError):
                    self.publish()
                self.assert_no_outputs()
        for key in ('id', 'slug'):
            value = post('other')
            value[key] = original[key]
            self.save(self.source, [original, value])
            with self.assertRaises(ValueError):
                self.publish()
            self.assert_no_outputs()

    def test_complete_translations_are_required_before_any_write(self):
        for audience in ('public', 'member'):
            for broken in ('missing-language', 'empty-body', 'missing-field', 'extra-language'):
                with self.subTest(audience=audience, broken=broken):
                    self.save(self.source, [post('safe')])
                    value = post('translated', audience=audience)
                    if broken == 'missing-language':
                        del value['translations']['en']
                    elif broken == 'empty-body':
                        value['translations']['en']['body_html'] = ' '
                    elif broken == 'missing-field':
                        del value['translations']['en']['excerpt']
                    else:
                        value['translations']['fr'] = value['translations']['en']
                    self.save(self.source if audience == 'public' else self.private, [value])
                    with self.assertRaises(ValueError):
                        self.publish(private=audience == 'member')
                    self.assert_no_outputs()

    def test_incomplete_static_pages_and_wrappers_fail_before_writes(self):
        self.save(self.source, [post('safe')])
        for broken in ('missing-page', 'missing-language', 'main-wrapper', 'script', 'gate-ids'):
            with self.subTest(broken=broken):
                source = site_copy()
                if broken == 'missing-page':
                    del source['pages']['s01e03']
                elif broken == 'missing-language':
                    del source['pages']['home']['translations']['en']
                elif broken == 'gate-ids':
                    source['pages']['gate']['translations']['en']['body_html'] = '<p>Incomplete gate</p>'
                else:
                    source['pages']['home']['translations']['en']['body_html'] = (
                        '<main><p>Wrapped</p></main>' if broken == 'main-wrapper' else '<script>grant()</script>')
                self.site.write_text(json.dumps(source))
                with self.assertRaises(ValueError):
                    self.publish()
                self.assert_no_outputs()

    def test_obsolete_source_schema_has_no_fallback(self):
        self.source.write_text(json.dumps(dict(schema='me-gad-ev.journal.v1', posts=[])))
        with self.assertRaises(ValueError):
            self.publish()
        self.assert_no_outputs()

    def test_roots_and_symlinks_cannot_publish_members(self):
        self.save(self.source, [post('safe')])
        self.save(self.private, [post('secret', audience='member')])
        repo = Path(__file__).resolve().parents[1]
        for target in (self.out, self.out / 'nested', self.root, repo / '.private-test-output'):
            with self.assertRaises(ValueError):
                build(self.source, self.out, self.private, target, site_source=self.site)
        self.members.mkdir()
        self.out.mkdir()
        (self.members / 'members').symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.publish(private=True)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_late_localized_destination_escape_writes_no_pages(self):
        self.save(self.source, [post('safe')])
        self.out.mkdir()
        escape = self.root / 'escape'
        escape.mkdir()
        (self.out / 'pl').symlink_to(escape, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(list(escape.iterdir()), [])
        self.assertEqual([path.name for path in self.out.iterdir()], ['pl'])

    def test_output_aliases_and_blocked_parents_fail_before_writes(self):
        self.save(self.source, [post('safe')])
        self.out.mkdir()
        (self.out / 'pl').symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual([path.name for path in self.out.iterdir()], ['pl'])
        (self.out / 'pl').unlink()
        (self.out / 'pl').write_text('not a directory')
        with self.assertRaises((ValueError, OSError)):
            self.publish()
        self.assertEqual([path.name for path in self.out.iterdir()], ['pl'])
        (self.out / 'pl').unlink()
        (self.out / 'pl').symlink_to(self.out / 'missing', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual([path.name for path in self.out.iterdir()], ['pl'])

    def test_private_source_inside_public_root_is_rejected(self):
        self.save(self.source, [post('safe')])
        self.out.mkdir()
        private = self.out / 'private.json'
        self.save(private, [post('secret', audience='member')])
        with self.assertRaises(ValueError):
            build(self.source, self.out, private, self.members, site_source=self.site)
        self.assertEqual([path.name for path in self.out.iterdir()], ['private.json'])
        self.assertFalse(self.members.exists())

    def test_member_body_feed_agent_index_and_share_metadata_isolation(self):
        self.save(self.source, [post('safe')])
        secret = post('secret', audience='member')
        for language, text in secret['translations'].items():
            text.update(title=f'PRIVATE-TITLE-{language}', excerpt=f'PRIVATE-EXCERPT-{language}',
                        body_html=f'<p>PRIVATE-BODY-{language}</p>')
        self.save(self.private, [secret])
        self.assertEqual(self.publish(private=True), (1, 1))
        for path in self.out.rglob('*'):
            if path.is_file():
                self.assertNotIn('PRIVATE-', path.read_text())
                self.assertNotIn('/secret/', path.read_text())
        for prefix, language in [('members/', 'en'), ('members/pl/', 'pl')]:
            html = (self.members / prefix / 'journal/secret/index.html').read_text()
            self.assertIn(f'PRIVATE-BODY-{language}', html)
            head = html.split('</head>')[0]
            self.assertNotIn('PRIVATE-', head)
            self.assertNotIn('/secret/', head)
            self.assertNotIn('property="og:', head)
            self.assertNotIn('name="twitter:', head)
            self.assertNotIn('journal-og.png', head)
            self.assertNotIn('rel="canonical"', head)
            self.assertIn('noindex, nofollow', head)
        self.assertFalse((self.out / 'members').exists())
        self.assertFalse((self.out / 'pl/members').exists())
        self.assertFalse((self.members / 'pl/members').exists())
        self.assertFalse((self.members / 'members/en').exists())


    def test_new_episode_ledger_links_use_public_post_slugs(self):
        handover, current = post('s01e04'), post('s01e05')
        handover['slug'], current['slug'] = 'handover-story', 'current-story'
        for language, prefix in [('en', ''), ('pl', '/pl')]:
            html = archive([current, handover], False, language)
            ledger = html.split('<section id="matrix">')[1].split('</table>')[0]
            self.assertIn(f'href="{prefix}/journal/handover-story/"', ledger)
            self.assertIn(f'href="{prefix}/journal/current-story/"', ledger)
            self.assertNotIn('/challenge/s01e04/', ledger)
            self.assertNotIn('/challenge/s01e05/', ledger)

    def test_language_switches_preserve_routes_and_localized_feeds(self):
        self.save(self.source, [post('safe')])
        self.save(self.private, [post('secret', audience='member')])
        self.publish(private=True)
        pairs = [(self.out, '/pl' + path, path) for path in PAGE_PATHS.values()]
        pairs += [(self.out, '/pl/journal/', '/journal/'),
                  (self.out, '/pl/journal/safe/', '/journal/safe/'),
                  (self.members, '/members/pl/journal/', '/members/journal/'),
                  (self.members, '/members/pl/journal/secret/', '/members/journal/secret/')]
        for root, pl, en in pairs:
            for language, here, other in [('pl', pl, en), ('en', en, pl)]:
                with self.subTest(route=here):
                    html = (root / here.lstrip('/') / 'index.html').read_text()
                    page = Links(html)
                    self.assertEqual(page.language, language)
                    switch = [attrs for attrs in page.links if 'hreflang' in attrs]
                    self.assertEqual({attrs['href'] for attrs in switch}, {here, other})
                    for attrs in switch:
                        self.assertEqual(attrs.get('aria-current'), 'page' if attrs['href'] == here else None)
                        self.assertEqual(attrs['hreflang'], attrs['lang'])
                    prefix = '/pl' if language == 'pl' else ''
                    self.assertIn(prefix + '/', [attrs.get('href') for attrs in page.links])
                    self.assertIn(prefix + '/journal/', [attrs.get('href') for attrs in page.links])
                    rss_links = [attrs['href'] for attrs in page.head_links
                                 if attrs.get('type') == 'application/rss+xml']
                    self.assertEqual(rss_links, [prefix + '/journal/feed.xml'])
                    if root == self.out:
                        canonical = [attrs['href'] for attrs in page.head_links
                                     if attrs.get('rel') == 'canonical']
                        self.assertEqual(canonical, ['https://megadev.div0.space' + here])
                        alternates = {attrs['hreflang']: attrs['href'] for attrs in page.head_links
                                      if 'hreflang' in attrs}
                        self.assertEqual(alternates, {
                            'en': 'https://megadev.div0.space' + en,
                            'pl': 'https://megadev.div0.space' + pl})
        self.assertFalse((self.out / 'en').exists())
        for prefix, language in [('', 'en'), ('pl/', 'pl')]:
            rss = ET.parse(self.out / prefix / 'journal/feed.xml')
            self.assertEqual(rss.findtext('./channel/language'), language)
            self.assertEqual(rss.findtext('./channel/item/link'), f'https://megadev.div0.space/{prefix}journal/safe/')
            self.assertIn(f'/{prefix}journal/safe/', (self.out / prefix / 'llms.txt').read_text())


if __name__ == '__main__':
    unittest.main()
