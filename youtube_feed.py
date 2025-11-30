#!/usr/bin/env python

import argparse
import locale
import re
import tomllib
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.dom.minidom import parse as xml_parse


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--locale', default=None)
    parser.add_argument('--since', default=None)
    return parser


def get_config(path=Path('~/.config/youtube_feed.toml')):
    path = path.expanduser().resolve()
    with path.open('rb') as f:
        config = tomllib.load(f)
        assert 'channels' in config and hasattr(config['channels'], '__iter__')
        return config


def request(url):
    with urllib.request.urlopen(url) as resp:
        for line in resp:
            yield line.decode()


class CanonicalLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        if tag == 'link':
            attrs = dict(attrs)
            if 'rel' in attrs and attrs['rel'] == 'canonical':
                self.canonical = attrs['href']


def get_channel_id(channel):
    parser = CanonicalLinkParser()

    for line in request(channel):
        parser.feed(line)
        if parser.canonical:
            break

    if not parser.canonical:
        raise ValueError(f'No channel id found for channel {channel}')

    return parser.canonical.split('/')[-1]


def get_feed(channel_id):
    return urllib.request.urlopen(f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}')


def get_node_text(node):
    texts = []
    for node in node.childNodes:
        if node.nodeType == node.TEXT_NODE:
            texts.append(node.data)
    return ''.join(texts)


def get_videos(channel_id):
    with get_feed(channel_id) as f:
        doc = xml_parse(f)
    for entry in doc.getElementsByTagName('entry'):
        title_node, = entry.getElementsByTagName('title')
        title = get_node_text(title_node)
        url_node, = entry.getElementsByTagName('link')
        url = url_node.attributes['href'].value
        published_node, = entry.getElementsByTagName('published')
        published = datetime.fromisoformat(get_node_text(published_node))

        yield published, title, url


def get_last_videos(channel_id, n=5):
    videos = sorted(get_videos(channel_id), reverse=True)
    return videos[:n]


def main():
    config = get_config()
    args = get_parser().parse_args()

    loc = args.locale or config.get('locale')
    if loc:
        locale.setlocale(locale.LC_ALL, loc)

    since = args.since or config.get('since')
    if since is not None:
        since = datetime.fromisoformat(since).astimezone()

    for channel in config['channels']:
        print('#', channel)
        print()
        channel_id = get_channel_id(channel)

        for published, title, url in get_last_videos(channel_id):
            if since is None or published >= since:
                print('##', title)
                print('- ', url)
                print('- ', f'{published:%d %B %Y}')
                print()

        print('=' * 20)
        print()


if __name__ == '__main__':
    main()
