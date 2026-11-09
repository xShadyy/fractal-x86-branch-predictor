#!/usr/bin/env python3
"""Offline checks for publication documents, local assets, and simple CFF metadata.

The CFF check accepts the repository's scalar fields plus an authors mapping
list. It checks this supported YAML structure and required CFF 1.2 fields;
it is not a replacement for the complete external Citation File Format schema.
"""
from __future__ import annotations

import argparse
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zlib

def publication_documents(root):
    """Include every translated README as languages are added."""
    return ('README.md', *(path.relative_to(root).as_posix()
                          for path in sorted((root/'docs/i18n').glob('README.*.md'))))


class DocumentationError(ValueError):
    pass


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.anchors.add(attrs['id'])
        if tag == 'a' and attrs.get('name'):
            self.anchors.add(attrs['name'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.links.append(attrs[key])


def prose(text):
    """Remove fenced code so sample links are not treated as rendered links."""
    return re.sub(r'^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$', '', text,
                  flags=re.MULTILINE | re.DOTALL)


def destinations(text):
    text = prose(text)
    parser = HTMLLinks()
    parser.feed(text)
    result = list(parser.links)
    references = {}
    for match in re.finditer(r'^\s{0,3}\[([^\]\n]+)\]:\s*(?:<([^>]+)>|(\S+))', text, re.MULTILINE):
        references[' '.join(match[1].lower().split())] = match[2] or match[3]
    # Include definitions so shortcut-style references are checked as well.
    result.extend(references.values())
    # Parse balanced parentheses in inline Markdown destinations.
    for start in re.finditer(r'!?\[[^\]\n]*\]\(', text):
        i, depth, escaped = start.end(), 1, False
        end = i
        for end in range(i, len(text)):
            char = text[end]
            if char == '\n':
                break
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if not depth:
                    raw = text[i:end].strip()
                    if raw.startswith('<') and '>' in raw:
                        result.append(raw[1:raw.index('>')])
                    elif raw:
                        result.append(re.split(r'\s+[\"\']', raw, maxsplit=1)[0])
                    break
    for match in re.finditer(r'!?\[([^\]\n]+)\]\[([^\]\n]*)\]', text):
        key = ' '.join((match[2] or match[1]).lower().split())
        if key not in references:
            raise DocumentationError(f'undefined Markdown link reference: {key}')
        if references[key] not in result:
            result.append(references[key])
    return result


def anchors(text):
    text = prose(text)
    parser = HTMLLinks()
    parser.feed(text)
    result, seen = set(parser.anchors), {}
    headings = re.findall(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$', text, re.MULTILINE)
    headings += re.findall(r'^([^\n]+)\n(?:={3,}|-{3,})\s*$', text, re.MULTILINE)
    for heading in headings:
        heading = re.sub(r'<[^>]*>', '', unescape(heading)).strip().lower()
        heading = re.sub(r'!?\[([^\]]+)\]\([^)]*\)', r'\1', heading)
        slug = re.sub(r'[^\w\-\s]', '', heading, flags=re.UNICODE).replace(' ', '-')
        duplicate = seen.get(slug, 0)
        seen[slug] = duplicate + 1
        result.add(slug if not duplicate else f'{slug}-{duplicate}')
    return result


def check_asset(path):
    if path.suffix.lower() == '.svg':
        try:
            root = ET.fromstring(path.read_bytes())
        except ET.ParseError as error:
            raise DocumentationError(f'invalid SVG XML: {path.name}: {error}') from error
        if root.tag.split('}')[-1] != 'svg':
            raise DocumentationError(f'asset does not have an SVG root: {path.name}')
    elif path.suffix.lower() == '.png':
        data = path.read_bytes()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise DocumentationError(f'invalid PNG signature: {path.name}')
        offset, chunks = 8, []
        while offset < len(data):
            if offset + 12 > len(data):
                raise DocumentationError(f'truncated PNG chunk: {path.name}')
            length = struct.unpack_from('>I', data, offset)[0]
            kind = data[offset+4:offset+8]
            end = offset + 12 + length
            if end > len(data) or (zlib.crc32(data[offset+4:end-4]) & 0xffffffff) != struct.unpack_from('>I', data, end-4)[0]:
                raise DocumentationError(f'invalid PNG chunk or CRC: {path.name}')
            chunks.append(kind)
            if kind == b'IHDR':
                if length != 13 or not all(struct.unpack_from('>II', data, offset+8)):
                    raise DocumentationError(f'invalid PNG dimensions: {path.name}')
            offset = end
        if not chunks or chunks[0] != b'IHDR' or chunks[-1] != b'IEND' or b'IDAT' not in chunks:
            raise DocumentationError(f'incomplete PNG: {path.name}')


def scalar(raw):
    raw = raw.strip()
    if not raw:
        raise DocumentationError('empty CFF scalar')
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise DocumentationError(f'invalid quoted CFF scalar: {raw}') from error
        if not isinstance(value, str) or not value:
            raise DocumentationError('CFF scalar must be a nonempty string')
        return value
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'") or re.search(r"(?<!')'(?!')", raw[1:-1]):
            raise DocumentationError('invalid single-quoted CFF scalar')
        return raw[1:-1].replace("''", "'")
    raw = raw.split(' #', 1)[0].rstrip()
    if not raw or raw[0] in '[{&*!>|' or raw in ('null', '~') or re.search(r':\s', raw):
        raise DocumentationError(f'unsupported or invalid CFF scalar: {raw}')
    return raw


def check_citation(path):
    fields, authors, current = {}, [], None
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '\t' in line:
            raise DocumentationError(f'CFF line {number}: tabs are not supported')
        top = re.fullmatch(r'([a-z][a-z0-9-]*):\s*(.*)', line)
        author = re.fullmatch(r'  - ([a-z][a-z0-9-]*):\s*(.+)', line)
        detail = re.fullmatch(r'    ([a-z][a-z0-9-]*):\s*(.+)', line)
        if top:
            key, value = top.groups()
            if key in fields:
                raise DocumentationError(f'duplicate CFF field: {key}')
            if key == 'authors':
                if value:
                    raise DocumentationError('CFF authors must be a mapping list')
                fields[key] = authors
            else:
                fields[key] = scalar(value)
            current = None
        elif author or detail:
            if 'authors' not in fields or list(fields)[-1] != 'authors':
                raise DocumentationError(f'CFF line {number}: misplaced author mapping')
            match = author or detail
            if author:
                current = {}
                authors.append(current)
            if current is None or match[1] in current:
                raise DocumentationError(f'CFF line {number}: invalid or duplicate author field')
            current[match[1]] = scalar(match[2])
        else:
            raise DocumentationError(f'CFF line {number}: unsupported YAML structure')
    missing = {'cff-version', 'message', 'title', 'authors'} - fields.keys()
    if missing:
        raise DocumentationError(f'missing required CFF fields: {sorted(missing)}')
    if fields['cff-version'] != '1.2.0' or not authors:
        raise DocumentationError('CFF 1.2.0 and at least one author are required')
    for author in authors:
        if not author.get('name') and not author.get('family-names'):
            raise DocumentationError('each CFF author needs name or family-names')
    for key in ('repository-code', 'url'):
        if key in fields and not fields[key].startswith('https://'):
            raise DocumentationError(f'CFF {key} must be an HTTPS URL')
    return len(authors)


def check(root):
    root = root.resolve()
    checked, assets, external = 0, set(), 0
    documents = publication_documents(root)
    for name in documents:
        document = root / name
        if not document.is_file():
            raise DocumentationError(f'missing publication document: {name}')
        for destination in destinations(document.read_text(encoding='utf-8')):
            parsed = urlsplit(unescape(destination))
            if parsed.scheme or parsed.netloc:
                external += 1
                continue
            local = unquote(parsed.path).replace('\\', '/')
            target = (document if not local else
                      root / local.lstrip('/') if local.startswith('/') else document.parent / local).resolve()
            if not target.is_relative_to(root) or not target.exists():
                raise DocumentationError(f'{name}: missing or outside-repository target: {destination}')
            if parsed.fragment and target.suffix.lower() == '.md':
                fragment = unquote(parsed.fragment)
                if fragment.startswith('user-content-'):
                    fragment = fragment[len('user-content-'):]
                if fragment not in anchors(target.read_text(encoding='utf-8')):
                    raise DocumentationError(f'{name}: missing heading anchor: {destination}')
            if target.suffix.lower() in ('.png', '.svg') and target not in assets:
                check_asset(target)
                assets.add(target)
            checked += 1
    authors = check_citation(root/'CITATION.cff')
    if not any(path.suffix.lower() == '.png' for path in assets):
        raise DocumentationError('publication documents must link a local PNG image')
    return dict(documents=len(documents), document_paths=list(documents),
                local_links=checked, assets=len(assets),
                external_links_skipped=external, citation_authors=authors,
                scope='offline local links, headings, PNG/SVG structure and required CFF fields')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = check(args.root)
    except (DocumentationError, OSError, ValueError) as error:
        print(f'Documentation check failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
