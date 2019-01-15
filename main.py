import base64
import json
import threading
import time
import requests
import urllib
import youtube_dl
from flask import Flask, request, redirect, g, render_template
from spotify import app_authorisation, user_authorisation, playlist_data

app = Flask(__name__)

SPOTIFY_PLAYLIST = None
YOUTUBE_KEY = None
SPOTIFY_CLIENT_ID = None
SPOTIFY_CLIENT_SECRET = None
SPOTIFY_ACCESS_TOKEN = None


class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def yt_dl_hook(d):
    if d['status'] == 'finished':
        print('Done downloading, now converting...')


def download_spotify_track(track, playlist_name):
    name = track['track']['name']
    artist = track['track']['artists'][0]['name']

    params = {
        'part': 'snippet',
        'type': 'video',
        'maxResults': 1,
        'key': YOUTUBE_KEY,
        'q': '{0} {1}'.format(name, artist)
    }

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': MyLogger(),
        'progress_hooks': [yt_dl_hook],
        'outtmpl': '{0}/{1} - {2}.%(ext)s'.format(playlist_name, name, artist),
    }

    r = requests.get(
        'https://www.googleapis.com/youtube/v3/search', params=params)

    if r.status_code == 200:
        video_id = r.json()['items'][0]['id']['videoId']
        url = 'https://www.youtube.com/watch?v={0}'.format(video_id)

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    else:
        print('youtube response error')
        print(r.json()['error']['message'])


def load_config():
    global SPOTIFY_PLAYLIST, SPOTIFY_ACCESS_TOKEN, YOUTUBE_KEY, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    with open('config.json') as f:
        data = json.load(f)
        SPOTIFY_PLAYLIST = data['SPOTIFY_PLAYLIST']
        SPOTIFY_ACCESS_TOKEN = data['SPOTIFY_ACCESS_TOKEN']
        YOUTUBE_KEY = data['YOUTUBE_KEY']
        SPOTIFY_CLIENT_ID = data['SPOTIFY_CLIENT_ID']
        SPOTIFY_CLIENT_SECRET = data['SPOTIFY_CLIENT_SECRET']


@app.route('/')
def index():
    load_config()
    auth_url = app_authorisation(SPOTIFY_CLIENT_ID)
    return redirect(auth_url)


@app.route('/callback/q')
def callback():
    authorization_header = user_authorisation(
        SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)

    playlist1 = playlist_data(authorization_header, SPOTIFY_PLAYLIST)
    playlist_name = playlist1['name']

    threads = []

    print('Started retrieving playlist {0}'.format(playlist_name))

    for track in playlist1['tracks']['items'][:2]:
        thread = threading.Thread(
            target=download_spotify_track, args=(track, playlist_name))
        thread.start()
        time.sleep(1)

    for thread in threads:
        thread.join()

    return '{0} retrieved'.format(playlist_name)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
