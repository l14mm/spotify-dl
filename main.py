import base64
import json
import os.path
import threading
import time
import eyed3
import requests
import urllib
import youtube_dl
from flask import Flask, request, redirect, g, render_template
from spotify import app_authorisation, user_authorisation, playlist_data, user_playlist_data, profile_data

app = Flask(__name__)

SPOTIFY_PLAYLISTS = None
YOUTUBE_KEYS = []
SPOTIFY_CLIENT_ID = None
SPOTIFY_CLIENT_SECRET = None
SPOTIFY_ACCESS_TOKEN = None


class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        print('youtube logger warning: ' + msg)

    def error(self, msg):
        print('youtube logger error: ' + msg)


def yt_dl_hook(d):
    if d['status'] == 'finished':
        print('Finished downloading {0}'.format(d['filename']))


def download_spotify_track(track, playlist_name):
    track_name = sanitise_file_name(track['track']['name'])
    artist = track['track']['artists'][0]['name']
    file_path = 'Playlists/{0}/{1}.mp3'.format(playlist_name, track_name)

    # Skip if track already exists
    if os.path.isfile(file_path):
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': MyLogger(),
        'progress_hooks': [yt_dl_hook],
        'outtmpl': 'Playlists/{0}/{1}.%(ext)s'.format(playlist_name, track_name)
    }

    youtube_key_index = 0
    r = None

    while (r == None or r.status_code != 200) and youtube_key_index < len(YOUTUBE_KEYS):
        youtube_search_params = {
            'part': 'snippet',
            'type': 'video',
            'maxResults': 1,
            'key': YOUTUBE_KEYS[youtube_key_index],
            'q': '{0} {1}'.format(track_name, artist)
        }

        r = requests.get(
            'https://www.googleapis.com/youtube/v3/search', params=youtube_search_params)

        # Try next key
        youtube_key_index += 1

    if r != None and r.status_code == 200:
        video_id = r.json()['items'][0]['id']['videoId']
        url = 'https://www.youtube.com/watch?v={0}'.format(video_id)

        attempts = 0
        while attempts < 4:
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                break
            except Exception as e:
                print("Youtube download error {0}, track {1}".format(e, track_name))

        # Wait for conversion to finish
        while not os.path.isfile(file_path):
            time.sleep(1)

        # Get album art
        album = track['track']['album']
        image_url = album['images'][0]['url']
        image = urllib.request.urlopen(image_url).read()

        try:
            audiofile = eyed3.load(file_path)
            audiofile.tag.title = track_name
            audiofile.tag.artist = artist
            audiofile.tag.album = album['name']
            audiofile.tag.album_artist = album['artists'][0]['name']
            audiofile.tag.track_num = track['track']['track_number']
            audiofile.tag.images.set(3, image , "image/jpeg" ,u"Description")
            audiofile.tag.lyrics.set(u"""Test Lyrics""")
            audiofile.tag.save()
        except Exception as e:
            print('error on eyed3 on track {0}, error: {1}'.format(track_name, e))

    else:
        print('youtube response error')
        print(r.json()['error']['message'])
        print(r)


def load_config():
    global SPOTIFY_PLAYLISTS, SPOTIFY_ACCESS_TOKEN, YOUTUBE_KEYS, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    with open('config.json') as f:
        data = json.load(f)
        SPOTIFY_PLAYLISTS = data['SPOTIFY_PLAYLISTS']
        SPOTIFY_ACCESS_TOKEN = data['SPOTIFY_ACCESS_TOKEN']
        YOUTUBE_KEYS = data['YOUTUBE_KEYS']
        SPOTIFY_CLIENT_ID = data['SPOTIFY_CLIENT_ID']
        SPOTIFY_CLIENT_SECRET = data['SPOTIFY_CLIENT_SECRET']


@app.route('/')
def index():
    load_config()
    auth_url = app_authorisation(SPOTIFY_CLIENT_ID)
    return redirect(auth_url)

# Make sure file name doesn't contain any illegal characters
def sanitise_file_name(name):
    return name.replace('/', '-').replace('"', '').strip('.').strip('`').strip("'")

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
        sanitised_playlist_name = sanitise_file_name(item['name'])

        # Only download wanted playlists
        if (playlist_name not in SPOTIFY_PLAYLISTS):
            continue

        print('Started retrieving playlist {0}'.format(playlist_name))

        for track in playlist['tracks']['items']:
            thread = threading.Thread(
                target=download_spotify_track, args=(track, sanitised_playlist_name))
            threads.append(thread)
            thread.start()

    num_threads_left = len(threads)

    for thread in threads:
        thread.join()
        num_threads_left -= 1
        print('{0} songs left'.format(num_threads_left))

    print('Playlists retrieved')

    print('Playlists retrieved')

    return 'Playlists retrieved'


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
