import customtkinter as ctk
import threading
import subprocess
import sys
import os
import json
import re
import shutil
from tkinter import filedialog

# ── Auto-install deps ─────────────────────────────────────────────────────────
def _pip(*pkgs):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", *pkgs,
                        "--quiet", "--break-system-packages"], check=True)
    except subprocess.CalledProcessError:
        # Fallback for pip versions that don't support --break-system-packages
        subprocess.run([sys.executable, "-m", "pip", "install", *pkgs,
                        "--quiet"], check=True)

try:
    import customtkinter  # noqa
except ImportError:
    _pip("customtkinter")
    import customtkinter as ctk

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":      "#0D0D12",
    "surface": "#13131A",
    "card":    "#18181F",
    "border":  "#252535",
    "accent":  "#7C6EF8",
    "spotify": "#1DB954",
    "yt":      "#E53935",
    "text":    "#EAEAF5",
    "muted":   "#5A5A78",
    "success": "#22C55E",
    "error":   "#EF4444",
    "warn":    "#F59E0B",
    "chip_on": "#7C6EF820",
    "chip_border_on": "#7C6EF8",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    if "spotify.com" in url:
        return "spotify"
    if "youtube.com" in url or "youtu.be" in url or "music.youtube" in url:
        return "ytmusic"
    return "unknown"

def tool_ok(name: str) -> bool:
    """Cross-platform check if an executable exists (replaces `which`)"""
    return shutil.which(name) is not None

def ensure_tools(log):
    need = [t for t in ("spotdl", "yt-dlp") if not tool_ok(t)]
    if need:
        log(f"Installing {', '.join(need)} …", "warn")
        _pip(*need)
        log("Tools ready.", "success")

def shorten(p: str, n: int = 48) -> str:
    return ("…" + p[-(n-1):]) if len(p) > n else p

def _fmt_dur(ms: int) -> str:
    s = ms // 1000
    return f"{s//60}:{s%60:02d}" if s else ""

def fetch_tracklist(url: str, platform: str) -> list[dict]:
    """
    Returns list of {title, artist, duration, url} dicts.
    For playlists/albums: all tracks. For single: one entry.
    """
    tracks = []
    if platform == "spotify":
        tmp = os.path.join(os.getenv("TEMP", "/tmp"), "_spotdl_meta.spotdl")
        subprocess.run(
            ["spotdl", "save", url, "--save-file", tmp, "--log-level", "ERROR"],
            capture_output=True, text=True
        )
        if os.path.exists(tmp):
            with open(tmp) as f:
                data = json.load(f)
            for s in data.get("songs", []):
                tracks.append({
                    "title":    s.get("name", "Unknown"),
                    "artist":   ", ".join(s.get("artists", [])) or "Unknown",
                    "duration": _fmt_dur(s.get("duration", 0)),
                    "url":      s.get("url", url),
                })
            os.remove(tmp)
        else:
            tracks.append({"title": "Track", "artist": "", "duration": "", "url": url})

    else:  # ytmusic / yt-dlp
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print",
             "%(title)s\t%(uploader)s\t%(duration_string)s\t%(webpage_url)s",
             "--no-warnings", url],
            capture_output=True, text=True
        )
        for line in r.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                tracks.append({
                    "title":    parts[0],
                    "artist":   parts[1],
                    "duration": parts[2],
                    "url":      parts[3],
                })
            elif len(parts) == 1 and parts[0]:
                tracks.append({"title": parts[0], "artist": "", "duration": "", "url": url})
        if not tracks:
            tracks.append({"title": "Video", "artist": "", "duration": "", "url": url})

    return tracks


# ── App ───────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Music Downloader")
        self.geometry("740x860")
        self.minsize(680, 700)
        self.configure(fg_color=C["bg"])

        self._plat_var   = ctk.StringVar(value="auto")
        self._fmt_var    = ctk.StringVar(value="mp3")
        self._out_dir    = ctk.StringVar(value=os.path.expanduser("~/Music"))
        self._busy       = False
        self._tracks: list[dict]         = []
        self._track_vars: list[ctk.BooleanVar] = []
        self._track_rows: list[ctk.CTkFrame]   = []

        self._build()

    # ─── Layout ──────────────────────────────────────────────────────────────

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=64)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="♫  Music Downloader",
                     font=ctk.CTkFont("Helvetica", 20, "bold"),
                     text_color=C["text"]).place(relx=.5, rely=.5, anchor="center")

        self._body = ctk.CTkScrollableFrame(self, fg_color=C["bg"],
                                             scrollbar_button_color=C["border"])
        self._body.pack(fill="both", expand=True, padx=20, pady=16)

        self._build_link()
        self._build_platform()
        self._build_format()
        self._build_songs()
        self._build_outdir()
        self._build_action()
        self._build_log()

    def _section(self, label: str) -> ctk.CTkFrame:
        wrap = ctk.CTkFrame(self._body, fg_color="transparent")
        wrap.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(wrap, text=label.upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(0, 5))
        card = ctk.CTkFrame(wrap, fg_color=C["card"], corner_radius=14,
                             border_color=C["border"], border_width=1)
        card.pack(fill="x")
        return card

    def _build_link(self):
        card = self._section("Link")
        inn = ctk.CTkFrame(card, fg_color="transparent")
        inn.pack(fill="x", padx=16, pady=14)

        row = ctk.CTkFrame(inn, fg_color="transparent")
        row.pack(fill="x")

        self._url = ctk.CTkEntry(
            row, placeholder_text="Paste a Spotify or YouTube Music link …",
            height=44, corner_radius=10,
            fg_color=C["surface"], border_color=C["border"], border_width=1,
            font=ctk.CTkFont(size=13), text_color=C["text"])
        self._url.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._url.bind("<KeyRelease>", self._on_url_key)

        self._fetch_btn = ctk.CTkButton(
            row, text="Fetch", width=76, height=44, corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["accent"], hover_color="#6257D0",
            command=self._fetch_tracks)
        self._fetch_btn.pack(side="left")

        self._detect_lbl = ctk.CTkLabel(inn, text="",
                                         font=ctk.CTkFont(size=11),
                                         text_color=C["muted"])
        self._detect_lbl.pack(anchor="w", pady=(6, 0))

    def _build_platform(self):
        card = self._section("Platform")
        inn = ctk.CTkFrame(card, fg_color="transparent")
        inn.pack(fill="x", padx=16, pady=14)

        self._plat_btns: dict[str, ctk.CTkButton] = {}
        opts = [("auto", "Auto-detect", C["accent"]),
                ("spotify", "Spotify", C["spotify"]),
                ("ytmusic", "YouTube Music", C["yt"])]
        for val, lbl, col in opts:
            b = ctk.CTkButton(
                inn, text=lbl, width=156, height=38, corner_radius=10,
                font=ctk.CTkFont(size=13),
                fg_color=col if val == "auto" else C["surface"],
                hover_color=col, border_width=1, border_color=C["border"],
                command=lambda v=val: self._pick_plat(v))
            b.pack(side="left", padx=(0, 8))
            self._plat_btns[val] = b

    def _build_format(self):
        card = self._section("Format")
        inn = ctk.CTkFrame(card, fg_color="transparent")
        inn.pack(fill="x", padx=16, pady=14)

        FMTS = [
            ("mp3",  "MP3",  "Most compatible · lossy"),
            ("flac", "FLAC", "Lossless · large files"),
            ("m4a",  "M4A",  "Apple format · lossy"),
            ("ogg",  "OGG",  "Open format · lossy"),
            ("opus", "OPUS", "High quality · small"),
            ("wav",  "WAV",  "Uncompressed · huge"),
        ]
        self._fmt_cards: dict[str, ctk.CTkFrame] = {}
        self._fmt_labels: dict[str, ctk.CTkLabel] = {}

        row1 = ctk.CTkFrame(inn, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        row2 = ctk.CTkFrame(inn, fg_color="transparent")
        row2.pack(fill="x")

        for i, (val, short, desc) in enumerate(FMTS):
            parent = row1 if i < 3 else row2
            fc = ctk.CTkFrame(parent, fg_color=C["surface"],
                               corner_radius=10, border_width=1,
                               border_color=C["accent"] if val == "mp3" else C["border"],
                               cursor="hand2")
            fc.pack(side="left", padx=(0, 8), ipadx=6, ipady=6)
            
            lbl = ctk.CTkLabel(fc, text=short,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=C["accent"] if val == "mp3" else C["text"])
            lbl.pack(padx=12, pady=(6, 0))
            
            ctk.CTkLabel(fc, text=desc,
                         font=ctk.CTkFont(size=9),
                         text_color=C["muted"]).pack(padx=12, pady=(2, 8))
            fc.bind("<Button-1>", lambda e, v=val: self._pick_fmt(v))
            for w in fc.winfo_children():
                w.bind("<Button-1>", lambda e, v=val: self._pick_fmt(v))
            
            self._fmt_cards[val] = fc
            self._fmt_labels[val] = lbl

    def _build_songs(self):
        self._songs_wrap = ctk.CTkFrame(self._body, fg_color="transparent")
        self._songs_wrap.pack(fill="x", pady=(0, 14))

    def _render_songs(self):
        for w in self._songs_wrap.winfo_children():
            w.destroy()

        if not self._tracks:
            return

        ctk.CTkLabel(self._songs_wrap, text="SONGS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(0, 5))

        card = ctk.CTkFrame(self._songs_wrap, fg_color=C["card"],
                             corner_radius=14, border_color=C["border"],
                             border_width=1)
        card.pack(fill="x")

        tb = ctk.CTkFrame(card, fg_color="transparent")
        tb.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(tb, text=f"{len(self._tracks)} track(s) found",
                     font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(side="left")
        ctk.CTkButton(tb, text="All", width=48, height=26, corner_radius=6,
                      font=ctk.CTkFont(size=11),
                      fg_color=C["surface"], hover_color=C["border"],
                      border_width=1, border_color=C["border"],
                      command=lambda: self._select_all(True)).pack(side="right", padx=(4, 0))
        ctk.CTkButton(tb, text="None", width=48, height=26, corner_radius=6,
                      font=ctk.CTkFont(size=11),
                      fg_color=C["surface"], hover_color=C["border"],
                      border_width=1, border_color=C["border"],
                      command=lambda: self._select_all(False)).pack(side="right")

        ctk.CTkFrame(card, height=1, fg_color=C["border"]).pack(fill="x", padx=14)

        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                         height=min(260, len(self._tracks) * 46 + 10),
                                         scrollbar_button_color=C["border"])
        scroll.pack(fill="x", padx=4, pady=4)

        self._track_vars = []
        self._track_rows = []
        for i, t in enumerate(self._tracks):
            var = ctk.BooleanVar(value=True)
            self._track_vars.append(var)

            row = ctk.CTkFrame(scroll, fg_color="transparent", corner_radius=8)
            row.pack(fill="x", pady=1)
            self._track_rows.append(row)

            cb = ctk.CTkCheckBox(row, text="", variable=var,
                                  width=20, checkbox_width=18, checkbox_height=18,
                                  fg_color=C["accent"], hover_color="#6257D0",
                                  border_color=C["border"],
                                  command=lambda r=row, v=var: self._highlight(r, v))
            cb.pack(side="left", padx=(8, 4))

            num = ctk.CTkLabel(row, text=f"{i+1:02d}",
                                font=ctk.CTkFont("Courier New", 11),
                                text_color=C["muted"], width=28)
            num.pack(side="left")

            title_lbl = ctk.CTkLabel(row, text=t["title"],
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      text_color=C["text"], anchor="w")
            title_lbl.pack(side="left", fill="x", expand=True, padx=(4, 0))

            if t.get("artist"):
                ctk.CTkLabel(row, text=t["artist"],
                              font=ctk.CTkFont(size=11), text_color=C["muted"],
                              anchor="e").pack(side="left", padx=(0, 8))

            if t.get("duration"):
                ctk.CTkLabel(row, text=t["duration"],
                              font=ctk.CTkFont("Courier New", 11),
                              text_color=C["muted"], width=40).pack(side="right", padx=(0, 8))

            self._highlight(row, var)

    def _build_outdir(self):
        card = self._section("Save to")
        inn = ctk.CTkFrame(card, fg_color="transparent")
        inn.pack(fill="x", padx=16, pady=12)

        self._dir_lbl = ctk.CTkLabel(inn, text=shorten(self._out_dir.get()),
                                      font=ctk.CTkFont(size=12),
                                      text_color=C["muted"], anchor="w")
        self._dir_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(inn, text="Browse", width=84, height=32,
                      corner_radius=8, font=ctk.CTkFont(size=12),
                      fg_color=C["surface"], hover_color=C["border"],
                      border_width=1, border_color=C["border"],
                      command=self._browse).pack(side="right")

    def _build_action(self):
        self._dl_btn = ctk.CTkButton(
            self._body, text="Download", height=52,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=C["accent"], hover_color="#6257D0",
            corner_radius=14, command=self._start)
        self._dl_btn.pack(fill="x", pady=(0, 10))

        self._prog = ctk.CTkProgressBar(
            self._body, height=5, corner_radius=4,
            fg_color=C["border"], progress_color=C["accent"])
        self._prog.set(0)
        self._prog.pack(fill="x", pady=(0, 14))

    def _build_log(self):
        self._log = ctk.CTkTextbox(
            self._body, height=150, fg_color=C["card"],
            border_color=C["border"], border_width=1, corner_radius=12,
            font=ctk.CTkFont("Courier New", 12), text_color=C["muted"], wrap="word")
        self._log.pack(fill="x")
        self._log.configure(state="disabled")

    # ─── Event handlers ───────────────────────────────────────────────────────

    def _on_url_key(self, _=None):
        url = self._url.get().strip()
        if not url:
            self._detect_lbl.configure(text="")
            return
        p = detect_platform(url)
        msgs = {"spotify": "🟢 Spotify", "ytmusic": "🔴 YouTube Music",
                "unknown": "⚠️  Unknown — pick platform manually"}
        self._detect_lbl.configure(text=msgs.get(p, ""))

    def _pick_plat(self, val: str):
        self._plat_var.set(val)
        pc = {"auto": C["accent"], "spotify": C["spotify"], "ytmusic": C["yt"]}
        for k, b in self._plat_btns.items():
            b.configure(fg_color=pc[k] if k == val else C["surface"])

    def _pick_fmt(self, val: str):
        self._fmt_var.set(val)
        for k, fc in self._fmt_cards.items():
            on = k == val
            fc.configure(border_color=C["accent"] if on else C["border"])
            if k in self._fmt_labels:
                self._fmt_labels[k].configure(text_color=C["accent"] if on else C["text"])

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self._out_dir.get())
        if d:
            self._out_dir.set(d)
            self._dir_lbl.configure(text=shorten(d))

    def _select_all(self, state: bool):
        for var, row in zip(self._track_vars, self._track_rows):
            var.set(state)
            self._highlight(row, var)

    def _highlight(self, row: ctk.CTkFrame, var: ctk.BooleanVar):
        row.configure(fg_color=C["surface"] if var.get() else "transparent")

    # ─── Fetch tracks ─────────────────────────────────────────────────────────

    def _fetch_tracks(self):
        url = self._url.get().strip()
        if not url:
            self._log_msg("Paste a link first.", "error"); return
        plat = self._plat_var.get()
        if plat == "auto":
            plat = detect_platform(url)
        if plat == "unknown":
            self._log_msg("Unknown platform — pick Spotify or YouTube Music.", "error"); return

        self._fetch_btn.configure(state="disabled", text="Fetching…")
        self._log_msg(f"Fetching tracklist from {plat} …", "info")
        threading.Thread(target=self._fetch_thread, args=(url, plat), daemon=True).start()

    def _fetch_thread(self, url, plat):
        try:
            ensure_tools(self._log_msg)
            tracks = fetch_tracklist(url, plat)
            self._tracks = tracks
            self.after(0, self._render_songs)
            self._log_msg(f"Found {len(tracks)} track(s). Uncheck any you don't want.", "success")
        except Exception as e:
            self._log_msg(f"Fetch error: {e}", "error")
        finally:
            self.after(0, lambda: self._fetch_btn.configure(state="normal", text="Fetch"))

    # ─── Download ─────────────────────────────────────────────────────────────

    def _start(self):
        if self._busy: return
        url = self._url.get().strip()
        if not url:
            self._log_msg("Paste a link first.", "error"); return

        plat = self._plat_var.get()
        if plat == "auto":
            plat = detect_platform(url)
        if plat == "unknown":
            self._log_msg("Unknown platform.", "error"); return

        if self._tracks and self._track_vars:
            selected = [t for t, v in zip(self._tracks, self._track_vars) if v.get()]
            if not selected:
                self._log_msg("Select at least one song.", "error"); return
        else:
            selected = []

        self._busy = True
        self._dl_btn.configure(state="disabled", text="Downloading …")
        self._clear_log()
        
        # Fix: Configure to indeterminate FIRST, then start
        self._prog.configure(mode="indeterminate")
        self._prog.start()

        threading.Thread(
            target=self._dl_thread,
            args=(url, plat, self._fmt_var.get(), self._out_dir.get(), selected),
            daemon=True).start()

    def _dl_thread(self, url, plat, fmt, out, selected):
        try:
            self._log_msg("Checking tools …", "info")
            ensure_tools(self._log_msg)
            os.makedirs(out, exist_ok=True)

            if selected:
                total = len(selected)
                for i, t in enumerate(selected, 1):
                    self._log_msg(f"[{i}/{total}] {t['title']}", "info")
                    if plat == "spotify":
                        self._run_spotdl(t["url"], fmt, out)
                    else:
                        self._run_ytdlp(t["url"], fmt, out)
            else:
                if plat == "spotify":
                    self._run_spotdl(url, fmt, out)
                else:
                    self._run_ytdlp(url, fmt, out)

            self._log_msg(f"✓ All done! Saved to: {out}", "success")
        except Exception as e:
            self._log_msg(f"Error: {e}", "error")
        finally:
            self.after(0, self._dl_done)

    def _run_spotdl(self, url, fmt, out):
        self._stream(["spotdl", url, "--output", out, "--format", fmt,
                      "--log-level", "WARNING"])

    def _run_ytdlp(self, url, fmt, out):
        tpl = os.path.join(out, "%(title)s.%(ext)s")
        self._stream(["yt-dlp", "-x",
                      "--audio-format", fmt, "--audio-quality", "0",
                      "--no-playlist",
                      "-o", tpl, url])

    def _stream(self, cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in p.stdout:
            line = line.rstrip()
            if line:
                self._log_msg(line, "info")
        p.wait()
        if p.returncode not in (0, 1):
            raise RuntimeError(f"Exited {p.returncode}")

    def _dl_done(self):
        self._prog.stop()
        self._prog.configure(mode="determinate")
        self._prog.set(1)
        self._dl_btn.configure(state="normal", text="Download")
        self._busy = False

    # ─── Log ─────────────────────────────────────────────────────────────────

    _LCOL = {"info": "#5A5A78", "success": "#22C55E",
              "error": "#EF4444", "warn": "#F59E0B"}

    def _log_msg(self, msg: str, lvl: str = "info"):
        def _do():
            self._log.configure(state="normal")
            tag = f"t{id(msg)}"
            self._log.tag_config(tag, foreground=self._LCOL.get(lvl, C["muted"]))
            self._log.insert("end", msg + "\n", tag)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


if __name__ == "__main__":
    App().mainloop()