import base64
import json
import threading
import time
import eyed3
import requests
import urllib
import youtube_dl
from os import listdir, makedirs, listdir, remove
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

update_thread = None
main_thread = None
playlists_status = {}
playlist_names = {'available':[],'monitored':[]}
playlists = {}

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
        youtube_search_params = {
        'part': 'snippet',
        'type': 'video',
        'maxResults': 1,
        'key': YOUTUBE_KEYS[YOUTUBE_KEY_INDEX],
        'q': '{0} {1}'.format(track_name, artist)
        }

        r = requests.get(
        'https://www.googleapis.com/youtube/v3/search', params=youtube_search_params)

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

        attempts = 0

        while attempts < 4:
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                # Check if file downloaded and converted successfully
                if isfile(file_path):
                    break
            except Exception as e:
                print("Youtube download error: {0}".format(e))

        # Check if file downloaded and converted successfully
        if isfile(file_path):
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
            print("Track did not download/convert successfully")
    else:
        print('tried all keys')
        print('youtube response error')
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

def update_page():
    while True:
        time.sleep(1)
        socketio.emit('message', {'playlists_status': json.dumps(playlists_status), "playlist_names": json.dumps(playlist_names)}, namespace='/test')

@app.route('/')
def index():
    load_config()
    auth_url = app_authorisation(SPOTIFY_CLIENT_ID)
    return redirect(auth_url)

# Make sure file name doesn't contain any illegal characters
def sanitise_file_name(name):
    return name.replace('/','-').strip('.')

@app.route('/callback/q')
def callback():
    global update_thread, main_thread

    authorization_header = user_authorisation(
        SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)

    if update_thread is None:
        update_thread = threading.Thread(target=update_page)
        update_thread.start()
    if main_thread is None:
        main_thread = threading.Thread(target=load_playlists, args=(authorization_header,))
        main_thread.start()
    # threading.Thread(target=monitor_playlists).start()

    return render_template('index.html', playlists=playlists_status, playlist_names=playlist_names)

def load_playlists(authorization_header):
    global thread, playlists_status, playlist_names, playlists

    with app.test_request_context():

        profile = profile_data(authorization_header)
        playlists = user_playlist_data(authorization_header, profile)

        for item in playlists["items"]:

            playlist = playlist_data(authorization_header, item['id'])
            playlist_name = item['name']

            playlist_names['available'].append(playlist_name)
            playlists[playlist_name] = playlist

@socketio.on('monitor_playlist', namespace='/test')
def monitor_playlist(msg):
    playlist_name = msg['data']
    
    playlist = playlists[playlist_name]
    if playlist_name in playlist_names['available']:
        playlist_names['available'].remove(playlist_name)
        playlist_names['monitored'].append(playlist_name)

    threads = []

    playlist_path = 'Playlists/{0}/'.format(playlist_name)

    # Create playlist folder if it doens't exist
    if not isdir(playlist_path):
        makedirs(playlist_path)
    else:
        # Cleanup unwanted files
        current_tracks = listdir(playlist_path)
        for track in current_tracks:
            if track.endswith(".webm") or track.endswith(".m4a"):
                remove(join(playlist_path, track))

    # Get current and playlist track names
    current_track_names = sorted([f.replace('.mp3','') for f in listdir(playlist_path) if isfile(join(playlist_path, f))], key=str.lower)
    playlist_track_names = sorted([sanitise_file_name(f['track']['name']) for f in playlist['tracks']['items']], key=str.lower)

    # Return playlist tracks which aren't downloaded
    missing_tracks = list(set(playlist_track_names).difference(current_track_names))
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
        
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080)
