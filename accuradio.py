#!/usr/bin/env python2
import sys
import os.path
import argparse
import json
import shutil
import urllib

from urllib2 import build_opener, HTTPCookieProcessor, Request, HTTPHandler
from urllib import urlencode
from cookielib import CookieJar
from tempfile import mkstemp
from contextlib import closing
from subprocess import Popen, PIPE

from lxml import html

URL = 'http://www.accuradio.com'
cj = CookieJar()
handler = HTTPHandler(debuglevel=0)
opener = build_opener(handler, HTTPCookieProcessor(cj))
opener.addheaders = [
        ('User-agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36'),
        ('Accept', '*/*'),
        ('Accept-Encoding','deflate')
]

def fetch_channels(genre):
    resp = opener.open('{}/search/{}/'.format(URL,  urllib.quote(genre)))
    content = resp.read()
    root = html.fromstring(content)
    return {r.attrib['title'].replace('Listen to ',''): r.attrib['data-id']
        for r in root.xpath('//a[@data-id and @title]')}


def fetch_channel_meta(channel, cid):
    token = None
    for c in cj:
        if c.name == 'csrftoken':
            token = c.value

    assert token

    data = {
        'name': channel,
        'o': cid,
        'getando': '1',
        'getts': '1',
        'csrfmiddlewaretoken': token
    }

    req = Request('{}/c/m/json/channel/'.format(URL), urlencode(data))
    req.add_header('X-CSRFToken', token)
    # req.add_header('X-Requested-With', 'XMLHttpRequest')
    resp = opener.open(req)
    return json.load(resp)


def fetch_playlist(cid, ando, schedule):
    url = '{}/playlist/json/{}/?ando={}&intro=true&spotschedule={}&fa=null'.format(
        URL, cid, ando, schedule)
    resp = opener.open(url)
    return json.load(resp)


def set_tags(fname, info):
    opts = []

    ai = info['album']
    if 'title' in ai:
        opts.extend(('-A', ai['title']))

    if 'year' in ai:
        opts.extend(('-y', ai['year']))

    ai = info['artist']
    if 'artistdisplay' in ai:
        opts.extend(('-R', ai['artistdisplay']))

    opts.extend(('-a', info['track_artist']))
    opts.extend(('-s', info['title']))
    opts = [r.encode('utf-8') for r in opts]

    Popen(['mp4tags'] + opts + [fname]).poll()


def fetch(channel, cid):
    meta = fetch_channel_meta(channel, cid)
    ando = meta['ando']
    schedule = meta['spotschedule']
    playlist = fetch_playlist(cid, ando, schedule)

    for song in playlist:
        if 'primary' not in song:
            continue

        fname = os.path.basename(song['fn']) + '.m4a'
        if os.path.exists(fname):
            continue

        if fname.startswith('index'):
            print song

        if fname.startswith('protocol'):
            print song

        url = song['primary'] + song['fn'] + '.m4a'
        try:
            resp = opener.open(url)
        except:
            continue

        print url

        fd, tmpfname = mkstemp()
        with closing(os.fdopen(fd, 'w')) as tmpfile:
            shutil.copyfileobj(resp, tmpfile)

        shutil.move(tmpfname, fname)
        set_tags(fname, song)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='fetch music from accuradio.com')
    parser.add_argument('genre', help='something like jazz or adultalternative')
    parser.add_argument('channel', help='Groove Jazz or Latin Jazz', nargs='?', default=None)
    args = parser.parse_args()

    channels = fetch_channels(args.genre)
    if args.channel and args.channel in channels:
        fetch(args.channel, channels[args.channel])
    else:
        print '\n'.join(sorted(channels))


