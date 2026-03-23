# Echo 
A self hosted Discord music bot built with Python

## Features
- Play audio from YouTube, YouTube Music, and Spotify
- Queue management with shuffle and remove
- Pause, resume, and skip controls
- Automatic audio normalization

## Requirements
- Python 3.10+
- Node.js 20+
- Git
- FFmpeg
- PyNaCl

## Installation

### 1. Install Git
Download and install from https://git-scm.com if you don't already have it. Verify with `git --version`

### 2. Clone the repository
```bash
git clone https://github.com/domranieri/echo-bot.git
cd echo
```

### 3. Install Python dependencies
```bash
python -m pip install "discord.py[voice]" yt-dlp spotipy python-dotenv
```

### 4. Install Node.js
Download and install from https://nodejs.org (LTS version recommended). This is required by yt-dlp to solve YouTube's JavaScript challenges.

After installing, find the path to your Node.js executable:
- **Windows:** Run `where node` in your terminal (e.g. `C:\Program Files\nodejs\node.exe`)

Open `bot.py` and update the Node.js path in both `YTDL_OPTIONS` and `YTDL_PLAYLIST_OPTIONS`:
```python
"extractor_args": {"youtube": {"js_runtimes": ["nodejs:/your/path/to/node"]}},
```

### 5. Install FFmpeg
Download from https://ffmpeg.org and add it to your system PATH

### 6. Set up Discord bot
- Go to https://discord.com/developers/applications
- Create a new application and navigate to the **Bot** tab
- Enable **Message Content Intent** under Privileged Gateway Intents
- Copy your bot token
- Under **OAuth2 → URL Generator**, select `bot` scope and the following permissions:
  - Send Messages
  - Read Message History
  - Embed Links
  - Connect
  - Speak
- Use the generated URL to invite the bot to your server

### 7. Set up custom emojis
Echo uses custom emojis to indicate whether a track is from YouTube or Spotify

- Go to https://discord.com/developers/applications and open your bot application
- Click the **Emojis** tab and upload the YouTube and Spotify icons provided or use your own
- Name them `youtube` and `spotify` respectively
- Copy the ID of each emoji (shown in the dashboard)

Open `bot.py` and update the emoji lines with your IDs:
```python
EMOJI_SPOTIFY = "<:spotify:your_spotify_emoji_id_here>"
EMOJI_YOUTUBE = "<:youtube:your_youtube_emoji_id_here>"
```

### 8. Set up Spotify API credentials
- Go to https://developer.spotify.com/dashboard
- Create a new app
- Add `http://127.0.0.1:8888/callback` as a redirect URI
- Select **Web API** under APIs used
- Copy your Client ID and Client Secret

### 9. Configure your environment
Open `.env` and fill in your credentials:
```
DISCORD_TOKEN=your_discord_token_here
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
```

### 10. Authenticate with Spotify
Run this once to log in and cache your Spotify credentials:
```bash
python spotify_auth.py
```
A browser window will open asking you to log in to Spotify and approve the app. After approving, a `.spotify_cache` file will be saved locally and you won't need to do this again.

### 11. Run the bot
```bash
python bot.py
```

## Commands

| Command | Aliases | Description |
|---|---|---|
| `!play <query>` | `!p` | Play a YouTube/Spotify URL, or search term |
| `!skip` | `!s` | Skip the current track |
| `!pause` | | Pause playback |
| `!resume` | `!r` | Resume playback |
| `!stop` | | Stop playback and clear the queue |
| `!queue` | `!q` | Show the current queue |
| `!nowplaying` | `!np` | Show what's currently playing |
| `!shuffle` | | Shuffle the queue |
| `!remove <number>` | `!rm` | Remove a track from the queue by position |
| `!volume <0-100>` | `!vol` | Set the playback volume |
| `!leave` | `!disconnect`, `!dc` | Disconnect the bot from voice |
| `!help` | `!h` | Show all available commands |

## Notes
- Spotify links are resolved to YouTube searches for audio playback, as Spotify does not provide direct audio streaming via its API
- The bot will automatically disconnect after 5 minutes of being left alone in a voice channel
- Audio normalization is applied automatically to keep volume levels consistent across tracks

## Maintenance
Keep yt-dlp updated regularly to maintain YouTube compatibility:
```bash
python -m pip install -U yt-dlp
```
If Spotify authentication stops working, delete `.spotify_cache` and run `spotify_auth.py` again.

## Built With
- [discord.py](https://github.com/Rapptz/discord.py)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [spotipy](https://github.com/spotipy-dev/spotipy)
- [FFmpeg](https://ffmpeg.org)
