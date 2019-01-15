import json
import requests
import base64
import urllib
from flask import request

SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE_URL = 'https://api.spotify.com'
API_VERSION = 'v1'
SPOTIFY_API_URL = '{}/{}'.format(SPOTIFY_API_BASE_URL, API_VERSION)

CLIENT_SIDE_URL = 'http://192.168.1.250'
PORT = 8080
REDIRECT_URI = '{}:{}/callback/q'.format(CLIENT_SIDE_URL, PORT)
SCOPE = 'playlist-modify-public playlist-modify-private'
STATE = ''
SHOW_DIALOG_bool = True
SHOW_DIALOG_str = str(SHOW_DIALOG_bool).lower()


def playlist_data(header, playlist):
    playlist_api_endpoint = '{0}/playlists/{1}'.format(
        SPOTIFY_API_URL, playlist)
    playlists_response = requests.get(playlist_api_endpoint, headers=header)
    playlist_data = json.loads(playlists_response.text)
    return playlist_data


def app_authorisation(SPOTIFY_CLIENT_ID):
    auth_query_parameters = {
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
        'client_id': SPOTIFY_CLIENT_ID
    }
    url_args = '&'.join(['{}={}'.format(key, urllib.parse.quote(val))
                         for key, val in auth_query_parameters.items()])
    auth_url = '{}/?{}'.format(SPOTIFY_AUTH_URL, url_args)
    return auth_url


def user_authorisation(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET):
    auth_token = request.args['code']
    code_payload = {
        'grant_type': 'authorization_code',
        'code': str(auth_token),
        'redirect_uri': REDIRECT_URI
    }
    auth_str = '{0}:{1}'.format(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    b64_auth_str = base64.urlsafe_b64encode(auth_str.encode()).decode()
    headers = {'Authorization': 'Basic {0}'.format(b64_auth_str)}
    post_request = requests.post(
        SPOTIFY_TOKEN_URL, data=code_payload, headers=headers)

    response_data = json.loads(post_request.text)
    access_token = response_data['access_token']
    refresh_token = response_data['refresh_token']
    token_type = response_data['token_type']
    expires_in = response_data['expires_in']

    authorization_header = {'Authorization': 'Bearer {}'.format(access_token)}
    return authorization_header
