#!/usr/bin/env python2
import sys
import os.path
import argparse
import json
import shutil
from Queue import Queue
from threading import Thread

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

queue = Queue()
# how many thread for downloading songs
THREAD_AMOUNT = 20


def fetch_channels(genre):
    resp = opener.open('{}/finder/2013/channels/{}/?s=2013'.format(URL, genre))
    content = resp.read()
    root = html.fromstring(content)
    return {r.attrib['data-name']: r.attrib['data-id']
        for r in root.xpath('//a[@data-id and @data-name]')}


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

        # add song to queue, let threads to download
        queue.put(song)


def download_song(song):
    fname = os.path.basename(song['fn']) + '.m4a'
    if os.path.exists(fname):
        return

    if fname.startswith('index'):
        print song

    if fname.startswith('protocol'):
        print song

    url = song['primary'] + song['fn'] + '.m4a'
    try:
        resp = opener.open(url)
    except:
        return

    print url

    fd, tmpfname = mkstemp()
    with closing(os.fdopen(fd, 'w')) as tmpfile:
        shutil.copyfileobj(resp, tmpfile)

    shutil.move(tmpfname, fname)
    set_tags(fname, song)


class DownloadThread(Thread):

    def __init__(self, queue):
        Thread.__init__(self)
        self.queue = queue

    def run(self):
        while True:
            # get the song from queue
            song = self.queue.get()

            download_song(song)

            # mark the song as downloaded
            self.queue.task_done()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='fetch music from accuradio.com')
    parser.add_argument('genre', help='something like jazz or adultalternative')
    parser.add_argument('channel', help='Groove Jazz or Latin Jazz', nargs='?', default=None)
    args = parser.parse_args()

    channels = fetch_channels(args.genre)
    if args.channel and args.channel in channels:
        # create THREAD_AMOUNT of threads to download songs
        for i in range(THREAD_AMOUNT):
            thread = DownloadThread(queue)
            thread.setDaemon(True)
            thread.start()

        fetch(args.channel, channels[args.channel])
    else:
        print '\n'.join(sorted(channels))

    # wait for all songs to download
    queue.join()
