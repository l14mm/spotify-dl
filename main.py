import json
import threading
import time
import requests
import youtube_dl


playlist = None
spotify_access_token = None
youtube_key = None


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


ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'logger': MyLogger(),
    'progress_hooks': [yt_dl_hook],
}


def getTrack(track):
    name = track['track']['name']
    artist = track['track']['artists'][0]['name']

    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": 1,
        "key": youtube_key,
        "q": name + " " + artist
    }

    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search", params=params)

    if r.status_code == 200:
        video_id = r.json()['items'][0]['id']['videoId']
        url = 'https://www.youtube.com/watch?v=' + video_id
        print('Got youtube url for: ' + name)

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    else:
        print('youtube response error')
        print(r.json()['error']['message'])


def load_config():
    global playlist, spotify_access_token, youtube_key
    with open('config.json') as f:
        data = json.load(f)
        playlist = data['playlist']
        spotify_access_token = data['spotify_access_token']
        youtube_key = data['youtube_key']


def main():

    load_config()

    r = requests.get('https://api.spotify.com/v1/playlists/' + playlist,
                     headers={'Authorization': 'Bearer ' + spotify_access_token})

    if r.status_code == 200:
        threads = []
        for track in r.json()['tracks']['items']:
            thread = threading.Thread(target=getTrack, args=(track,))
            thread.start()
            time.sleep(1)

        for thread in threads:
            thread.join()

        print("Finished downloading playlist")
    else:
        print('spotify response error')
        print(r.json()['error']['message'])


if __name__ == "__main__":
    main()
