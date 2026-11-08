"""Offline fixtures for publication links and citation metadata, not hardware."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

SPEC = importlib.util.spec_from_file_location('check_documentation',
    Path(__file__).resolve().parents[1]/'scripts/check_documentation.py')
docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs)


def png():
    def chunk(name, payload):
        return struct.pack('>I', len(payload)) + name + payload + struct.pack('>I', zlib.crc32(name+payload) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\0\0\0\0\xff')) + chunk(b'IEND', b''))


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'assets').mkdir()
        (self.root/'assets/banner.png').write_bytes(png())
        (self.root/'assets/mark.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        for name in docs.DOCUMENTS:
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            prefix = '../../' if name.startswith('docs/') else ''
            target.write_text('# Main\n\n![Banner]('+prefix+'assets/banner.png)\n'+
                              '[Heading]('+prefix+'README.md#main)\n'+
                              '<img src="'+prefix+'assets/mark.svg">\n'+
                              '[External](https://example.invalid/never-fetched)\n')
        (self.root/'CITATION.cff').write_text('cff-version: 1.2.0\nmessage: "Cite this work."\n'+
            'title: "Software fixture"\nauthors:\n  - family-names: Example\n    given-names: Test\n'+
            'repository-code: https://example.invalid/repository\n')

    def test_all_languages_links_assets_and_simple_citation_pass_offline(self):
        result = docs.check(self.root)
        self.assertEqual((result['documents'], result['assets'], result['citation_authors']), (4, 2, 1))
        self.assertEqual(result['external_links_skipped'], 4)

    def test_missing_and_outside_repository_targets_fail(self):
        for destination in ('missing.md', '../outside.md'):
            with self.subTest(destination=destination):
                (self.root/'README.md').write_text('[Broken]('+destination+')\n')
                with self.assertRaisesRegex(docs.DocumentationError, 'target'):
                    docs.check(self.root)

    def test_unicode_duplicate_anchors_and_missing_anchor(self):
        target = self.root/'README.md'
        original = target.read_text()
        target.write_text(original+'\n# Własny wynik\n# Własny wynik\n[Valid](#własny-wynik-1)\n')
        docs.check(self.root)
        target.write_text(original+'\n[Broken](#unknown-heading)\n')
        with self.assertRaisesRegex(docs.DocumentationError, 'heading anchor'):
            docs.check(self.root)

    def test_reference_and_parenthesized_destinations(self):
        (self.root/'assets/file (draft).md').write_text('# Draft\n')
        links = docs.destinations('[Note](assets/file%20(draft).md#draft)\n[Guide][ref]\n[ref]: README.md#main\n')
        self.assertEqual(set(links), {'assets/file%20(draft).md#draft', 'README.md#main'})
        self.assertEqual(docs.destinations('[Guide]\n[Guide]: README.md#main\n'), ['README.md#main'])
        with self.assertRaisesRegex(docs.DocumentationError, 'undefined'):
            docs.destinations('[Guide][missing]\n')

    def test_corrupt_image_bytes_and_malformed_svg_fail(self):
        broken = bytearray(png())
        broken[-1] ^= 1
        (self.root/'assets/banner.png').write_bytes(broken)
        with self.assertRaisesRegex(docs.DocumentationError, 'PNG'):
            docs.check(self.root)
        (self.root/'assets/banner.png').write_bytes(png())
        (self.root/'assets/mark.svg').write_text('<svg>')
        with self.assertRaisesRegex(docs.DocumentationError, 'SVG'):
            docs.check(self.root)

    def test_missing_required_citation_and_duplicate_fields_fail(self):
        path = self.root/'CITATION.cff'
        path.write_text('cff-version: 1.2.0\n')
        with self.assertRaisesRegex(docs.DocumentationError, 'missing required'):
            docs.check_citation(path)
        path.write_text('cff-version: 1.2.0\ncff-version: 1.2.0\n')
        with self.assertRaisesRegex(docs.DocumentationError, 'duplicate'):
            docs.check_citation(path)

    def test_fenced_example_links_are_not_checked(self):
        for fence in ('```', '~~~'):
            with self.subTest(fence=fence):
                self.assertEqual(docs.destinations(fence+'markdown\n[Example](missing.md)\n'+fence+'\n'), [])


if __name__ == '__main__':
    unittest.main()
