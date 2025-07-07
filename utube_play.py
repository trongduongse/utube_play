#!/usr/bin/env python3


import os, re, json, requests, subprocess, sys, threading, time, socket
from tkinter import *
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from io import BytesIO


MPV_PATH, YTDLP_PATH = "mpv", "yt-dlp"
CACHE_DIR = os.path.join(os.path.expanduser('~'), 'youtube_cache')
AUTOSAVE_PATH = os.path.join(CACHE_DIR, 'autosave_playlist.m3u')
os.makedirs(CACHE_DIR, exist_ok=True)

# --- YouTube Search ---
def search_youtube(q):
    r = requests.get(f"https://www.youtube.com/results?search_query={q}", headers={'User-Agent': 'Mozilla/5.0'})
    pat = r'"videoRenderer":\{(.*?)\},"navigationEndpoint"'
    vids = []
    for b in re.findall(pat, r.text):
        i = re.search(r'"videoId":"(.*?)"', b)
        t = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', b) or re.search(r'"title":\{"simpleText":"(.*?)"', b)
        h = re.search(r'"thumbnails":\[\{"url":"(.*?)"', b)
        if i and t and h:
            vids.append({'videoId': i.group(1), 'title': t.group(1), 'thumbnail': h.group(1)})
    return vids

# --- Media Caching ---
def sanitize_filename(s):
    return re.sub(r'[\\/:*?"<>|]', '_', s)

def get_cached_media_path(vid, aud, title=None):
    ext = 'm4a' if aud else 'webm'
    return os.path.join(CACHE_DIR, f"{vid}_{sanitize_filename(title)[:80] if title else vid}.{ext}")

def download_media_if_needed(vid, link, aud, title=None, max_res=480, log_callback=None):
    p = get_cached_media_path(vid, aud, title)
    if not os.path.exists(p):
        args = [YTDLP_PATH, '-f', 'bestaudio[ext=m4a]/bestaudio/best', '-o', p, link] if aud else [YTDLP_PATH, '-f', f'bestvideo[ext=webm][height<={max_res}]+bestaudio[ext=webm]/bestvideo[height<={max_res}]+bestaudio/best[height<={max_res}]', '-o', p, link]
        try:
            proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0, encoding='utf-8', errors='replace')
            if log_callback: log_callback(proc.stdout)
            if proc.returncode != 0:
                if log_callback: log_callback("yt-dlp failed to download media!\n")
                messagebox.showerror("yt-dlp Error", "yt-dlp failed to download media!")
                return None
        except Exception as e:
            if log_callback: log_callback(f"yt-dlp Exception: {e}\n")
            messagebox.showerror("yt-dlp Error", f"yt-dlp exception: {e}")
            return None
    return p

# --- Playlist Save/Load ---
def save_playlist_to_file(pl, fp):
    with open(fp, 'w', encoding='utf-8') as f:
        for i in pl:
            f.write(f"# {i['title'].replace(chr(10),' ').replace(chr(13),' ')}\n{i['link']}\n")

def load_playlist_from_file(fp):
    pl, last = [], None
    if not os.path.exists(fp): return pl
    with open(fp, 'r', encoding='utf-8') as f:
        for l in [x.strip() for x in f if x.strip()]:
            if l.startswith('# '): last = l[2:]
            elif l.startswith('http'):
                pl.append({'link': l, 'title': last if last else l}); last = None
    return pl

# --- GUI ---
class YouTubeApp:
    def __init__(self, root, start_maximized=False):
        self.root = root
        self.root.title("YouTube Search & Playlist Player")
        self.playlist = []
        self.playlist_index = 0
        self.audio_only = BooleanVar(value=True)
        self.resolution = StringVar(value="480p")
        self.mpv_process = None
        self.search_results = []
        self.thumbnails = {}
        self.log_buffer = []
        self.setup_ui()
        # Activate the Main tab (index 1) on startup
        self.notebook.select(1)
        self.load_playlist(AUTOSAVE_PATH)
        self.root.update_idletasks()  # Ensure all widgets are laid out
        # Measure main content area (main_frame, left_frame, right_frame)
        # After adding Debug tab first, Main tab is at index 1
        main_frame = self.notebook.nametowidget(self.notebook.tabs()[1])
        left_frame = main_frame.grid_slaves(row=1, column=0)[0]
        right_frame = main_frame.grid_slaves(row=1, column=1)[0]
        left_frame.update_idletasks()
        right_frame.update_idletasks()
        # Get required width and height for both sections
        left_width = left_frame.winfo_reqwidth()
        right_width = right_frame.winfo_reqwidth()
        left_height = left_frame.winfo_reqheight()
        right_height = right_frame.winfo_reqheight()
        # Add a margin for borders and paddings
        margin_w = 48
        margin_h = 64
        total_width = left_width + right_width + margin_w
        total_height = max(left_height, right_height) + main_frame.grid_slaves(row=0, column=0)[0].winfo_reqheight() + margin_h
        # Set window size unless maximized
        if start_maximized:
            try:
                self.root.state('zoomed')  # Windows
            except Exception:
                self.root.attributes('-zoomed', True)  # Linux/others
        else:
            self.root.geometry(f'{total_width}x{total_height}')

    def setup_ui(self):
        # --- Main layout frames ---
        # Make sure the notebook fills the root window
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # --- Tabs ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # --- Debug tab (add first to ensure always visible) ---
        debug_frame = Frame(self.notebook)
        self.debug_text = Text(debug_frame, wrap='word', font=('Consolas', 10), state='disabled', height=30, width=120)
        self.debug_text.pack(fill=BOTH, expand=True)
        self.debug_text.tag_configure('stderr', foreground='red')
        self.notebook.add(debug_frame, text="Debug")

        # --- Main tab ---
        main_frame = Frame(self.notebook)
        self.notebook.add(main_frame, text="Main")

        # Make main_frame fully responsive
        main_frame.grid_rowconfigure(0, weight=0)  # Top bar
        main_frame.grid_rowconfigure(1, weight=1)  # Main content
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=2)

        # --- Top bar: Search ---
        topbar = Frame(main_frame, pady=8)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        for i in range(4):
            topbar.grid_columnconfigure(i, weight=0)
        topbar.grid_columnconfigure(1, weight=1)  # Make search entry expand
        self.search_var = StringVar()
        search_entry = Entry(topbar, textvariable=self.search_var, font=('Segoe UI', 12))
        search_entry.grid(row=0, column=0, padx=(8, 4), sticky="ew")
        search_entry.bind('<Return>', lambda e: self.search_and_display())
        Button(topbar, text="Search", font=('Segoe UI', 10), command=self.search_and_display).grid(row=0, column=1, padx=4)
        Checkbutton(topbar, text="Audio Only (default)", variable=self.audio_only, font=('Segoe UI', 10)).grid(row=0, column=2, padx=4)
        # Resolution dropdown (OptionMenu)
        res_frame = Frame(topbar)
        res_frame.grid(row=0, column=3, padx=4)
        Label(res_frame, text="Resolution:", font=('Segoe UI', 10)).pack(side=LEFT)
        OptionMenu(res_frame, self.resolution, "480p", "720p", "1080p").pack(side=LEFT)

        # --- Left: Search Results ---
        left_frame = Frame(main_frame, padx=8, pady=4)
        left_frame.grid(row=1, column=0, sticky="nsew")
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)
        # Search results (Canvas with thumbnails and titles)
        self.search_canvas = Canvas(left_frame, borderwidth=0)
        self.search_canvas.grid(row=0, column=0, sticky="nsew")
        self.search_scrollbar = Scrollbar(left_frame, orient="vertical", command=self.search_canvas.yview)
        self.search_scrollbar.grid(row=0, column=1, sticky="ns")
        self.search_canvas.configure(yscrollcommand=self.search_scrollbar.set)
        self.search_frame = Frame(self.search_canvas)
        self.search_canvas.create_window((0, 0), window=self.search_frame, anchor="nw")
        self.search_frame.bind("<Configure>", lambda e: self.search_canvas.configure(scrollregion=self.search_canvas.bbox("all")))
        self.search_result_widgets = []
        # Enable mouse wheel scrolling for search results (cross-platform)
        self.search_canvas.bind_all("<MouseWheel>", self._on_mousewheel_search, add='+')  # Windows and Mac (delta)
        self.search_canvas.bind_all("<Button-4>", self._on_mousewheel_search, add='+')    # Linux scroll up
        self.search_canvas.bind_all("<Button-5>", self._on_mousewheel_search, add='+')    # Linux scroll down

        # --- Right: Playlist and Controls ---
        right_frame = Frame(main_frame, padx=8, pady=4)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=0)  # Controls
        right_frame.grid_rowconfigure(1, weight=0)  # Label
        right_frame.grid_rowconfigure(2, weight=1)  # Playlist box
        right_frame.grid_rowconfigure(3, weight=0)  # Playback controls
        right_frame.grid_columnconfigure(0, weight=1)

        # Playlist controls (top of right frame)
        controls_frame = Frame(right_frame)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        Button(controls_frame, text="Save Playlist", font=('Segoe UI', 10), command=self.save_playlist_dialog).pack(side=LEFT, padx=2)
        Button(controls_frame, text="Load Playlist", font=('Segoe UI', 10), command=self.load_playlist_dialog).pack(side=LEFT, padx=2)
        Button(controls_frame, text="Remove Selected", font=('Segoe UI', 10), command=self.remove_selected_from_playlist).pack(side=LEFT, padx=2)

        # Playlist label
        Label(right_frame, text="Playlist:", font=('Segoe UI', 10)).grid(row=1, column=0, sticky="w", pady=(0, 2))

        # Playlist box
        self.playlist_box = Listbox(right_frame, font=('Segoe UI', 10), width=40, height=24)
        self.playlist_box.grid(row=2, column=0, sticky="nsew")
        self.playlist_box.bind('<Double-1>', self.play_from_playlist_box)
        # Enable mouse wheel scrolling for playlist (cross-platform)
        self.playlist_box.bind('<MouseWheel>', self._on_mousewheel_playlist)
        self.playlist_box.bind('<Button-4>', self._on_mousewheel_playlist)
        self.playlist_box.bind('<Button-5>', self._on_mousewheel_playlist)

        # Playback controls (bottom of right frame)
        playback_frame = Frame(right_frame, pady=8)
        playback_frame.grid(row=3, column=0, sticky="ew")
        self.pause_button = Button(playback_frame, text="Pause", font=('Segoe UI', 10), command=self.play_pause)
        self.pause_button.pack(side=LEFT, padx=4)
        self.is_paused = False
        Button(playback_frame, text="Stop", font=('Segoe UI', 10), command=self.stop).pack(side=LEFT, padx=4)
        Button(playback_frame, text="Next", font=('Segoe UI', 10), command=self.next_track).pack(side=LEFT, padx=4)
        self.status_label = Label(playback_frame, text="Idle", bg='gray', width=10)
        self.status_label.pack(side=LEFT, padx=12)

        # --- Add frames to main_frame grid (for resize) ---
        # Already done above, but ensure sticky is nsew for both frames
        left_frame.grid(row=1, column=0, sticky="nsew")
        right_frame.grid(row=1, column=1, sticky="nsew")
    def _on_mousewheel_search(self, event):
        # Cross-platform mouse wheel support
        if hasattr(event, 'delta'):
            if event.delta > 0:
                self.search_canvas.yview_scroll(-1, "units")
            elif event.delta < 0:
                self.search_canvas.yview_scroll(1, "units")
        elif hasattr(event, 'num'):
            if event.num == 4:
                self.search_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.search_canvas.yview_scroll(1, "units")

    def _on_mousewheel_playlist(self, event):
        if hasattr(event, 'delta'):
            if event.delta > 0:
                self.playlist_box.yview_scroll(-1, "units")
            elif event.delta < 0:
                self.playlist_box.yview_scroll(1, "units")
        elif hasattr(event, 'num'):
            if event.num == 4:
                self.playlist_box.yview_scroll(-1, "units")
            elif event.num == 5:
                self.playlist_box.yview_scroll(1, "units")

        # --- Add frames to main_frame grid ---
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=2)
        left_frame.grid(row=1, column=0, sticky="nsew")
        right_frame.grid(row=1, column=1, sticky="nsew")

        # ...existing code...

    def log(self, msg, tag=None):
        self.log_buffer.append(msg)
        self.debug_text.config(state='normal')
        if tag:
            self.debug_text.insert(END, msg, tag)
        else:
            self.debug_text.insert(END, msg)
        self.debug_text.see(END)
        self.debug_text.config(state='disabled')

    # No longer needed: _res_checkbox_logic

    def search_and_display(self):
        keyword = self.search_var.get().strip()
        if not keyword:
            return
        # Clear previous widgets
        for widget in self.search_result_widgets:
            widget.destroy()
        self.search_result_widgets.clear()
        self.search_results = search_youtube(keyword)
        self.thumbnails.clear()
        for idx, video in enumerate(self.search_results):
            row_frame = Frame(self.search_frame, height=100, width=880)
            row_frame.grid(row=idx, column=0, sticky="w", pady=2)
            thumb_label = Label(row_frame)
            thumb_label.pack(side=LEFT, padx=4)
            title_label = Label(row_frame, text=video['title'], font=('Segoe UI', 11), anchor='w', justify='left', wraplength=700)
            title_label.pack(side=LEFT, fill=X, expand=True, padx=8)
            row_frame.bind('<Double-1>', lambda e, i=idx: self.add_to_playlist_from_search(i))
            thumb_label.bind('<Double-1>', lambda e, i=idx: self.add_to_playlist_from_search(i))
            title_label.bind('<Double-1>', lambda e, i=idx: self.add_to_playlist_from_search(i))
            self.search_result_widgets.append(row_frame)
            threading.Thread(target=self.load_thumbnail_and_update, args=(idx, video['thumbnail'], thumb_label), daemon=True).start()

    def load_thumbnail_and_update(self, idx, url, label_widget):
        try:
            resp = requests.get(url, timeout=5)
            img = Image.open(BytesIO(resp.content)).resize((120, 90))
            photo = ImageTk.PhotoImage(img)
            self.thumbnails[idx] = photo
            # Update the label with the image (must be done in main thread)
            self.root.after(0, lambda: label_widget.config(image=photo))
            self.root.after(0, lambda: setattr(label_widget, 'image', photo))  # Keep reference
        except:
            self.thumbnails[idx] = None

    def update_listbox_item_image(self, idx, photo):
        # Listbox does not support images directly, so we use a workaround with a label overlay
        x = 20
        y = 100 + idx * 24  # 24 is approx item height
        label = Label(self.root, image=photo)
        label.image = photo  # Keep reference
        label.place(x=x, y=y)

    def load_thumbnail(self, idx, url):
        try:
            resp = requests.get(url, timeout=5)
            img = Image.open(BytesIO(resp.content)).resize((120, 90))
            self.thumbnails[idx] = ImageTk.PhotoImage(img)
        except:
            self.thumbnails[idx] = None

    def add_to_playlist_from_search(self, idx_or_event):
        # idx_or_event can be an int (from lambda) or an event (legacy)
        if isinstance(idx_or_event, int):
            idx = idx_or_event
        else:
            # fallback for event-based call (should not be used now)
            return
        video = self.search_results[idx]
        link = f"https://www.youtube.com/watch?v={video['videoId']}"
        # Prevent duplicates
        if any(item['link'] == link for item in self.playlist):
            self.playlist_index = [item['link'] for item in self.playlist].index(link)
        else:
            self.playlist.append({'link': link, 'title': video['title']})
            self.playlist_box.insert(END, video['title'])
            self.playlist_index = len(self.playlist) - 1
            self.auto_save_playlist()
        self.play_from_playlist()

    def play_from_playlist_box(self, event):
        idx = self.playlist_box.curselection()
        if not idx:
            return
        self.playlist_index = idx[0]
        self.play_from_playlist()

    def play_from_playlist(self):
        # Reset pause state and button
        self.is_paused = False
        self.pause_button.config(text="Pause")
        if not self.playlist:
            return
        if self.playlist_index >= len(self.playlist):
            self.playlist_index = 0
            return
        audio_only = self.audio_only.get()
        # Determine max resolution from dropdown
        res_map = {"480p": 480, "720p": 720, "1080p": 1080}
        max_res = res_map.get(self.resolution.get(), 480)
        # Prepare list of media paths or links for all playlist items
        mpv_playlist = []
        for item in self.playlist:
            video_link = item['link']
            video_id = re.search(r'v=([\w-]+)', video_link)
            video_id = video_id.group(1) if video_id else video_link
            title = item.get('title', None)
            media_path = get_cached_media_path(video_id, audio_only, title)
            if os.path.exists(media_path):
                mpv_playlist.append(media_path)
            else:
                mpv_playlist.append(video_link)
                # Start download in background for missing media
                threading.Thread(target=download_media_if_needed, args=(video_id, video_link, audio_only, title, max_res, self.log), daemon=True).start()
        # Kill previous mpv
        if self.mpv_process and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
        # Set IPC path for mpv (Windows: named pipe, Unix: unix socket)
        import sys
        if sys.platform == 'win32':
            self.mpv_ipc_path = r'\\.\pipe\mpv-pipe'
        else:
            self.mpv_ipc_path = f"/tmp/mpv-pipe-{os.getpid()}"
        # Reduce mpv's in-memory buffer for faster opening
        args = [
            MPV_PATH,
            f'--input-ipc-server={self.mpv_ipc_path}',
            '--cache=yes',
            '--cache-secs=1'
        ]
        # Set ytdl-format to match selected resolution for YouTube links
        ytdl_res_map = {480: '480', 720: '720', 1080: '1080'}
        ytdl_res = ytdl_res_map.get(max_res, '480')
        if audio_only:
            args.append('--no-video')
            args.append('--force-window=no')
            args.append(f'--ytdl-format=bestaudio[ext=m4a]/bestaudio/best')
        else:
            args.append(f'--ytdl-format=bestvideo[height<={ytdl_res}]+bestaudio/best[height<={ytdl_res}]')
        # Start mpv at the selected index, passing the full playlist
        args.extend(mpv_playlist[self.playlist_index:] + mpv_playlist[:self.playlist_index])
        try:
            self.mpv_process = subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
        except Exception as e:
            self.log(f"mpv Exception: {e}\n", tag='stderr')
            messagebox.showerror("mpv Error", f"mpv exception: {e}")
            return
        self.status_label.config(text='Playing', bg='lime')
        self.root.after(1000, self.poll_mpv)
        self.playlist_box.selection_clear(0, END)
        self.playlist_box.selection_set(self.playlist_index)
        self.playlist_box.activate(self.playlist_index)

    def poll_mpv(self):
        if self.mpv_process and self.mpv_process.poll() is None:
            self.status_label.config(text='Playing', bg='lime')
            self._poll_after_id = self.root.after(1000, self.poll_mpv)
        else:
            self.status_label.config(text='Idle', bg='gray')
            # Only auto-advance if not stopped by user
            if not getattr(self, '_stopped_by_user', False):
                self.playlist_index += 1
                if self.playlist_index < len(self.playlist):
                    self.play_from_playlist()
                else:
                    self.playlist_index = 0
            self._stopped_by_user = False

    def play_pause(self):
        # Toggle pause/resume for mpv using IPC (named pipe or unix socket)
        import json, time, sys, os
        if self.mpv_process and self.mpv_process.poll() is None:
            try:
                pause_state = not getattr(self, 'is_paused', False)
                if sys.platform == 'win32':
                    if not hasattr(self, 'mpv_ipc_path'):
                        self.mpv_ipc_path = r'\\.\pipe\mpv-pipe'
                    for _ in range(10):
                        try:
                            mpv_pipe = open(self.mpv_ipc_path, 'w+b', buffering=0)
                            break
                        except Exception:
                            time.sleep(0.1)
                    else:
                        return
                    cmd = {"command": ["set_property", "pause", pause_state]}
                    mpv_pipe.write((json.dumps(cmd) + '\n').encode('utf-8'))
                    mpv_pipe.flush()
                    mpv_pipe.close()
                else:
                    import socket
                    if not hasattr(self, 'mpv_ipc_path') or self.mpv_ipc_path.startswith('\\'):
                        self.mpv_ipc_path = f"/tmp/mpv-pipe-{os.getpid()}"
                    for _ in range(10):
                        try:
                            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                            client.connect(self.mpv_ipc_path)
                            break
                        except Exception:
                            time.sleep(0.1)
                    else:
                        return
                    cmd = {"command": ["set_property", "pause", pause_state]}
                    client.sendall((json.dumps(cmd) + '\n').encode('utf-8'))
                    # Read at least one response line to avoid broken pipe
                    try:
                        client.settimeout(0.5)
                        _ = client.recv(4096)
                    except Exception:
                        pass
                    client.close()
                self.is_paused = pause_state
                # Update button text
                if self.is_paused:
                    self.pause_button.config(text="Resume")
                else:
                    self.pause_button.config(text="Pause")
            except Exception:
                pass

    def stop(self):
        if self.mpv_process and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
            self.mpv_process.wait(timeout=2)
        self.status_label.config(text='Idle', bg='gray')
        # Prevent auto-advance in poll_mpv
        self._stopped_by_user = True
        poll_id = getattr(self, '_poll_after_id', None)
        if poll_id is not None:
            try:
                self.root.after_cancel(poll_id)
            except Exception:
                pass
            self._poll_after_id = None

    def next_track(self):
        if not self.playlist:
            return
        self.playlist_index += 1
        if self.playlist_index >= len(self.playlist):
            self.playlist_index = 0
        self.play_from_playlist()

    def remove_selected_from_playlist(self):
        idx = self.playlist_box.curselection()
        if not idx:
            messagebox.showerror("Error", "No playlist item selected!")
            return
        idx = idx[0]
        self.playlist_box.delete(idx)
        del self.playlist[idx]
        if self.playlist_index >= len(self.playlist):
            self.playlist_index = 0
        self.auto_save_playlist()

    def save_playlist_dialog(self):
        file_path = filedialog.asksaveasfilename(defaultextension='.m3u', filetypes=[('Playlist files', '*.m3u'), ('All files', '*.*')])
        if file_path:
            save_playlist_to_file(self.playlist, file_path)

    def load_playlist_dialog(self):
        file_path = filedialog.askopenfilename(filetypes=[('Playlist files', '*.m3u'), ('All files', '*.*')])
        if file_path:
            self.load_playlist(file_path)
            self.auto_save_playlist()

    def load_playlist(self, file_path):
        self.playlist = load_playlist_from_file(file_path)
        self.playlist_box.delete(0, END)
        for item in self.playlist:
            self.playlist_box.insert(END, item['title'])
        self.playlist_index = 0

    def auto_save_playlist(self):
        save_playlist_to_file(self.playlist, AUTOSAVE_PATH)

    def on_close(self):
        self.auto_save_playlist()
        if self.mpv_process and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
        self.root.destroy()

if __name__ == '__main__':
    root = Tk()
    # Set to True to always start maximized
    app = YouTubeApp(root, start_maximized=False)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
