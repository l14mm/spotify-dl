import base64
import json
import threading
import time
import requests
import urllib
import youtube_dl
from flask import Flask, request, redirect, g, render_template
from spotify import app_authorisation, user_authorisation, playlist_data, user_playlist_data, profile_data

app = Flask(__name__)

SPOTIFY_PLAYLISTS = None
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
        'outtmpl': 'Playlists/{0}/{1} - {2}.%(ext)s'.format(playlist_name, name, artist)
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
    global SPOTIFY_PLAYLISTS, SPOTIFY_ACCESS_TOKEN, YOUTUBE_KEY, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    with open('config.json') as f:
        data = json.load(f)
        SPOTIFY_PLAYLISTS = data['SPOTIFY_PLAYLISTS']
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

    profile = profile_data(authorization_header)
    Name = profile["display_name"]
    external_urls = profile["external_urls"]
    uri = profile["uri"]
    href = profile["href"]
    id = profile["id"]

    playlists = user_playlist_data(authorization_header, profile)

    threads = []

    for item in playlists["items"]:

        playlist = playlist_data(authorization_header, item['id'])
        playlist_name = item['name']

        # Only download wanted playlists
        if (playlist_name not in SPOTIFY_PLAYLISTS):
            continue

        print('Started retrieving playlist {0}'.format(playlist_name))

        for track in playlist['tracks']['items']:
            # TODO: don't download track if it has already been downloaded
            thread = threading.Thread(
                target=download_spotify_track, args=(track, playlist_name))
            thread.start()
            time.sleep(2)

        for thread in threads:
            thread.join()

    return 'Playlists retrieved'


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
