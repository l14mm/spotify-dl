import base64
import json
import threading
import time
import eyed3
import requests
import urllib
import youtube_dl
from os import listdir, mkdir
from os.path import isfile, isdir, join
from flask import Flask, request, redirect, g, render_template
from flask_socketio import SocketIO, emit
from spotify import app_authorisation, user_authorisation, playlist_data, user_playlist_data, profile_data

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

SPOTIFY_PLAYLISTS = None
YOUTUBE_KEYS = []
SPOTIFY_CLIENT_ID = None
SPOTIFY_CLIENT_SECRET = None
SPOTIFY_ACCESS_TOKEN = None

YOUTUBE_KEY_INDEX = 0

thread = None
playlists_status = {}

@socketio.on('connect', namespace='/test')
def test_connect():
    emit('my response', {'data': 'Connected', 'count': 0})

@socketio.on('disconnect', namespace='/test')
def test_disconnect():
    print('Client disconnected')

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
    global YOUTUBE_KEY_INDEX

    track_name = sanitise_file_name(track['track']['name'])
    artist = track['track']['artists'][0]['name']
    file_path = 'Playlists/{0}/{1}.mp3'.format(playlist_name, track_name)

    print('downloading {0}'.format(track_name))

    # Skip if track already exists
    # if path.isfile(file_path):
    #     return

    r = None
    while (r == None or r.status_code != 200) and YOUTUBE_KEY_INDEX < len(YOUTUBE_KEYS):
        youtube_params = {
        'part': 'snippet',
        'type': 'video',
        'maxResults': 1,
        'key': YOUTUBE_KEYS[YOUTUBE_KEY_INDEX],
        'q': '{0} {1}'.format(track_name, artist)
        }

        r = requests.get(
        'https://www.googleapis.com/youtube/v3/search', params=youtube_params)

        # Try next key
        YOUTUBE_KEY_INDEX += 1

    if r != None and r.status_code == 200:
        video_id = r.json()['items'][0]['id']['videoId']
        url = 'https://www.youtube.com/watch?v={0}'.format(video_id)

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

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Get album art
        image_url = track['track']['album']['images'][0]['url']
        image = urllib.request.urlopen(image_url).read()

        # Add id3 tags
        audiofile = eyed3.load(file_path)
        audiofile.tag.artist = artist
        audiofile.tag.title = track_name
        audiofile.tag.images.set(3, image , "image/jpeg" ,u"Description")
        
        audiofile.tag.save()

        # Move from missing to downloaded tracks list
        playlists_status[playlist_name]['missing'].remove(track_name)
        playlists_status[playlist_name]['downloaded'].append(track_name)
    else:
        print('tried all keys')
        print('youtube response error')
        print(r.json()['error']['message'])


def load_config():
    global SPOTIFY_PLAYLISTS, SPOTIFY_ACCESS_TOKEN, YOUTUBE_KEYS, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    with open('config.json') as f:
        data = json.load(f)
        SPOTIFY_PLAYLISTS = data['SPOTIFY_PLAYLISTS']
        SPOTIFY_ACCESS_TOKEN = data['SPOTIFY_ACCESS_TOKEN']
        YOUTUBE_KEYS = data['YOUTUBE_KEYS']
        SPOTIFY_CLIENT_ID = data['SPOTIFY_CLIENT_ID']
        SPOTIFY_CLIENT_SECRET = data['SPOTIFY_CLIENT_SECRET']

def update_page():
    while True:
        time.sleep(5)
        socketio.emit('message', {'playlists_status': json.dumps(playlists_status)}, namespace='/test')

@app.route('/')
def index():
    load_config()
    auth_url = app_authorisation(SPOTIFY_CLIENT_ID)
    return redirect(auth_url)

# Make sure file name doesn't contain any illegal characters
def sanitise_file_name(name):
    return name.replace('/','-').strip()

@app.route('/callback/q')
def callback():
    global thread, playlists_status
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

    if thread is None:
        thread = threading.Thread(target=update_page)
        thread.start()

    for item in playlists["items"]:

        playlist = playlist_data(authorization_header, item['id'])
        playlist_name = item['name']

        # Only download wanted playlists
        if (playlist_name not in SPOTIFY_PLAYLISTS):
            continue

        playlist_path = 'Playlists/{0}/'.format(playlist_name)

        # Create playlist folder if it doens't exist
        if not isdir(playlist_path):
            mkdir(playlist_path)

        # Get current and playlist track names
        current_track_names = sorted([f.replace('.mp3','') for f in listdir(playlist_path) if isfile(join(playlist_path, f))], key=str.lower)
        playlist_track_names = sorted([sanitise_file_name(f['track']['name']) for f in playlist['tracks']['items']], key=str.lower)

        # Return playlist tracks which aren't downloaded
        missing_tracks = list(set(current_track_names) ^ set(playlist_track_names))
        print('Missing these {0} tracks from {1}'.format(len(missing_tracks), playlist_name))
        print(missing_tracks)

        playlists_status[playlist_name] = {'missing': missing_tracks, 'downloaded': current_track_names}

        for track in playlist['tracks']['items']:
            if sanitise_file_name(track['track']['name']) in missing_tracks:
                thread = threading.Thread(
                    target=download_spotify_track, args=(track, playlist_name))
                thread.start()

    for thread in threads:
        thread.join()

    return render_template('index.html', playlists=playlists_status)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080)
