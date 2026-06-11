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
    parser.add_argument('--sort', choices=['channel', 'date'], default=None)
    return parser


def get_config(path=Path('~/.config/youtube_feed.toml')):
    path = path.expanduser().resolve()
    with path.open('rb') as f:
        config = tomllib.load(f)
        assert 'feeds' in config and hasattr(config['feeds'], '__iter__')
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


def get_node_text(node):
    texts = []
    for node in node.childNodes:
        if node.nodeType == node.TEXT_NODE:
            texts.append(node.data)
    return ''.join(texts)


class Feed:
    def __init__(self, *, channel_id=None, playlist_id=None):
        if len({channel_id is None, playlist_id is None}) != 2:
            raise ValueError('channel_id or playlist_id argument is required, not both')

        if channel_id is not None:
            self.feed_url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
        else:
            self.feed_url = f'https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}'

    @classmethod
    def from_url(cls, url):
        if m := re.fullmatch(r'https?://(?:www.?)youtube.com/playlist\?list=(.+)', url):
            return cls(playlist_id=m[1])
        return cls(channel_id=cls.get_channel_id(url))

    @staticmethod
    def get_channel_id(channel_url):
        parser = CanonicalLinkParser()

        for line in request(channel_url):
            parser.feed(line)
            if parser.canonical:
                break

        if not parser.canonical:
            raise ValueError(f'No channel id found for channel {channel_url}')

        return parser.canonical.split('/')[-1]

    def get_file(self):
        return urllib.request.urlopen(self.feed_url)

    def __iter__(self):
        with self.get_file() as f:
            doc = xml_parse(f)

        for entry in doc.getElementsByTagName('entry'):
            title_node, = entry.getElementsByTagName('title')
            title = get_node_text(title_node)
            url_node, = entry.getElementsByTagName('link')
            url = url_node.attributes['href'].value
            published_node, = entry.getElementsByTagName('published')
            published = datetime.fromisoformat(get_node_text(published_node))

            yield published, title, url


def get_last_videos(feed, n=5):
    videos = sorted(feed, reverse=True)
    return videos[:n]


def get_all_videos(feed_urls, since):
    for feed_url in feed_urls:
        try:
            feed = Feed.from_url(feed_url)
            for video in get_last_videos(feed):
                if since is None or video[0] >= since:
                    yield feed_url, *video
        except Exception as e:
            print('#', feed_url)
            print(e)
            print('=' * 20)
            print()


def print_videos(videos):
    last_feed_url = None

    for feed_url, published, title, url in videos:
        if feed_url != last_feed_url:
            if last_feed_url is not None:
                print('=' * 20)
                print()
            print('#', feed_url)
            print()
            last_feed_url = feed_url

        print('##', title)
        print('- ', url)
        print('- ', f'{published:%d %B %Y}')
        print()


def main():
    config = get_config()
    args = get_parser().parse_args()

    loc = args.locale or config.get('locale')
    if loc:
        locale.setlocale(locale.LC_ALL, loc)

    since = args.since or config.get('since')
    if since is not None:
        since = datetime.fromisoformat(since).astimezone()

    sort = args.sort or config.get('sort', 'channel')

    videos = get_all_videos(config['feeds'], since)

    if sort == 'date':
        videos = sorted(videos, key=lambda v: v[1])

    print_videos(videos)

if __name__ == '__main__':
    main()
