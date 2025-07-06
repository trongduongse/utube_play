# YouTube Player

Fun project to play youtube with minimal memory footprint, and powerc consumption.
Let you listen to Youtube music without hesitation on laptop battery.

Note: it works but lots of bug here and there.

## Features
- Search YouTube and display results with thumbnails
- Add videos to a playlist
- Play audio or video using `mpv` (with resolution selection)
- Save/load playlists in `.m3u` format
- Caches downloaded media for offline playback
- Debug tab for logs

## Requirements
- Python 3.7+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (must be in your PATH)
- [mpv](https://mpv.io/) (must be in your PATH)

### Python packages
Install required Python packages with:

```bash
pip install requests pillow
```

On Ubuntu, you may use:

```bash
sudo apt-get install python3-tk python3-pil python3-pil.imagetk
```

Tested with:
- mpv 0.40
- yt-dlp 2025.6.30

(You can install the latest versions with Homebrew: `brew install mpv` and `brew install yt-dlp`)

## Usage
1. Ensure `yt-dlp` and `mpv` are installed and available in your system PATH.
2. Run the application:

   ```bash
   python youtube_search.py
   ```
3. Use the GUI to search, build playlists, and play media.

## Notes
- Media is cached in `~/youtube_cache`.
- Playlists are autosaved to `~/youtube_cache/autosave_playlist.m3u`.
- On first run, the cache directory is created automatically.

## License
MIT License
