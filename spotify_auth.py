import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from dotenv import load_dotenv

load_dotenv()

auth_manager = SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="playlist-read-private playlist-read-collaborative",
    cache_path=".spotify_cache"
)

sp = spotipy.Spotify(auth_manager=auth_manager)
token = auth_manager.get_access_token(as_dict=False)
print("Spotify authenticated successfully! Token cached.")