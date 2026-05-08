import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Optional

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

try:
    import serial  # pyserial
except Exception:
    serial = None

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter  # pillow
except Exception:
    Image = ImageTk = ImageDraw = ImageFont = ImageFilter = None

try:
    import pygame
except Exception:
    pygame = None

try:
    from mutagen.mp3 import MP3
except Exception:
    MP3 = None

# --- CONFIG ---
# You can override the port via env var: RFID_SERIAL_PORT
# - Windows examples: COM3
# - macOS examples: /dev/tty.usbmodemXXXX or /dev/tty.usbserial-XXXX
# - Linux examples: /dev/ttyACM0 or /dev/ttyUSB0
SERIAL_PORT = os.getenv("RFID_SERIAL_PORT") or "AUTO"
BAUDRATE = 115200

songs = {
    "B9 71 F9 03": {"folder": "songs/folder1", "title": "Playlist One", "artist": "Artist A", "cover": "covers/cover1.jpg"},
    "55 A5 F9 03": {"folder": "songs/Sad", "title": "Sad Vibes", "artist": "Artist B", "cover": "covers/cover2.jpg"},
    "69 12 F6 03": {"folder": "songs/Happy", "title": "Happy Beats", "artist": "Artist C", "cover": "covers/cover3.jpg"},
    "8E 57 6C 05": {"folder": "songs/Classical", "title": "Classical Zone", "artist": "Artist D", "cover": "covers/cover4.jpg"},
    "E5 3F 6A 05": {"folder": "songs/deshi", "title": "Deshi Mix", "artist": "Artist E", "cover": "covers/cover5.jpg"}
}

# --- UI CONFIG ---
UI_BG_IMAGE = "ui_background.png"
SIDE_BOX_IMAGE = "side_box.png"  # your generated image

BASE_W, BASE_H = 720, 900
APP_W, APP_H = BASE_W, BASE_H  # design reference; actual runtime size can scale

TEXT = "#F3F7FF"
MUTED = "#B6C4D9"
ACCENT = "#4FA3FF"
GOOD = "#31D7A3"
BAD = "#FF5A6A"

PANEL_TINT = (8, 16, 28, 150)
PANEL_BORDER = (255, 255, 255, 40)

WIDGET_BG = "#111B2D"  # fallback solid bg

UI_BG_STYLE = (os.getenv("RFID_BG_STYLE") or "raw").strip().lower()

# Canvas cannot use RGBA tuples; use hex
CANVAS_SOFT_BORDER = "#7F8AA0"   # subtle border (soft grey-blue)
CANVAS_SOFT_BORDER_2 = "#5C667A"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STARTUP_LOG = os.path.join(BASE_DIR, "rfid_startup.log")


def startup_log(*parts):
    msg = " ".join(str(p) for p in parts)
    try:
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
    except Exception:
        pass
    if os.getenv("RFID_DEBUG") == "1":
        print("[RFID]", msg, flush=True)


def _missing_deps_banner_and_exit():
    missing = []
    if Image is None:
        missing.append("pillow (PIL)")
    if pygame is None:
        missing.append("pygame")

    if not missing:
        return

    # Pillow is required for the full image UI. If it's missing, only allow running
    # in compat UI mode (no images) by setting RFID_COMPAT_UI=1.
    if Image is None:
        compat_env = os.getenv("RFID_COMPAT_UI", "").strip().lower()
        compat_allowed = compat_env in ("1", "true", "yes", "on")
        msg = (
            "Missing Python packages: pillow (PIL)"
            + (", pygame" if pygame is None else "")
            + "\n\n"
            + "Recommended (venv):\n"
            + "  cd \"Human Computer Interaction/HCI Dummy/gg\"\n"
            + "  python3 -m venv .venv\n"
            + "  .venv/bin/python -m pip install -r requirements.txt\n\n"
            + "Then run:\n"
            + "  .venv/bin/python rfid_simple.py\n"
        )
        print(msg, file=sys.stderr)
        if not compat_allowed:
            print("Tip: set RFID_COMPAT_UI=1 to run without images.", file=sys.stderr)
            raise SystemExit(1)
        return

    # Pygame is only needed for audio playback. Allow the UI to run without it.
    if pygame is None:
        print("Warning: pygame not installed; audio playback will be disabled.", file=sys.stderr)
        return


def pick_serial_port(configured: str) -> Optional[str]:
    if not configured:
        return None

    configured = str(configured).strip()
    if configured and configured.upper() != "AUTO":
        return configured

    if os.name == "nt":
        return "COM3"

    try:
        if serial is None:
            return None

        from serial.tools import list_ports  # type: ignore

        ports = [p.device for p in list_ports.comports()]
        if not ports:
            return None

        def score(p: str) -> int:
            p = p.lower()
            if "usbmodem" in p:
                return 0
            if "usbserial" in p:
                return 1
            if "ttyacm" in p:
                return 2
            if "ttyusb" in p:
                return 3
            return 9

        ports.sort(key=score)
        return ports[0]
    except Exception:
        return None


def fmt_time(seconds: float) -> str:
    try:
        seconds = max(0, float(seconds))
    except Exception:
        seconds = 0
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


# Add rounded-rect support to Tk canvas using polygons (smooth)
def _create_round_rect(self, x1, y1, x2, y2, radius=12, **kwargs):
    r = max(1, int(radius))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1
    ]
    return self.create_polygon(points, smooth=True, splinesteps=16, **kwargs)

tk.Canvas.create_round_rect = _create_round_rect


def _hex_to_rgb(color: str):
    c = (color or "").strip()
    if c.startswith("#"):
        c = c[1:]
    if len(c) == 3:
        c = "".join([ch * 2 for ch in c])
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except Exception:
        return 0, 0, 0


def _flatten_rgba(img, bg_hex: str):
    if img is None:
        return None
    if getattr(img, "mode", None) != "RGBA":
        try:
            img = img.convert("RGBA")
        except Exception:
            return img
    r, g, b = _hex_to_rgb(bg_hex)
    base = Image.new("RGBA", img.size, (r, g, b, 255))
    return Image.alpha_composite(base, img).convert("RGB")


class CanvasSlider:
    """
    Professional slider drawn on canvas.
    - No ttk blocks.
    - Smooth knob.
    - Supports dragging + click.
    """

    def __init__(
        self,
        canvas: tk.Canvas,
        x: int, y: int,
        width: int, height: int,
        min_val: float, max_val: float, value: float,
        on_change=None,
        track_color="#223552",
        fill_color="#4FA3FF",
        knob_color="#F3F7FF",
        border_hex=CANVAS_SOFT_BORDER,
        show_knob=True,
        active_glow=True,
    ):
        self.c = canvas
        self.x, self.y = x, y
        self.w, self.h = width, height
        self.min = float(min_val)
        self.max = float(max_val) if max_val != min_val else float(min_val) + 1.0
        self.val = float(value)
        self.on_change = on_change

        self.track_color = track_color
        self.fill_color = fill_color
        self.knob_color = knob_color
        self.border_hex = border_hex
        self.show_knob = show_knob
        self.active_glow = active_glow

        self.dragging = False

        self._build()

        # Bind
        for tag in (self.tag_track, self.tag_fill, self.tag_knob, self.tag_hit):
            self.c.tag_bind(tag, "<Button-1>", self._click)
            self.c.tag_bind(tag, "<B1-Motion>", self._drag)
            self.c.tag_bind(tag, "<ButtonRelease-1>", self._release)

    def set_range(self, min_val: float, max_val: float):
        self.min = float(min_val)
        self.max = float(max_val) if max_val != min_val else float(min_val) + 1.0
        self.set_value(self.val, invoke=False)

    def set_value(self, v: float, invoke: bool = True):
        v = float(v)
        if v < self.min:
            v = self.min
        if v > self.max:
            v = self.max
        self.val = v
        self._redraw()
        if invoke and self.on_change:
            self.on_change(self.val)

    def get_value(self) -> float:
        return self.val

    def _ratio(self) -> float:
        return (self.val - self.min) / (self.max - self.min)

    def _px_from_value(self) -> float:
        pad = 10
        x1 = self.x + pad
        x2 = self.x + self.w - pad
        return x1 + self._ratio() * (x2 - x1)

    def _value_from_px(self, px: float) -> float:
        pad = 10
        x1 = self.x + pad
        x2 = self.x + self.w - pad
        px = max(x1, min(x2, px))
        r = (px - x1) / (x2 - x1) if x2 != x1 else 0.0
        return self.min + r * (self.max - self.min)

    def _build(self):
        r = self.h // 2

        # hit area (invisible)
        self.tag_hit = f"hit_{id(self)}"
        self.c.create_rectangle(
            self.x, self.y - 10, self.x + self.w, self.y + self.h + 10,
            fill="", outline="", tags=self.tag_hit
        )

        # track
        self.tag_track = f"track_{id(self)}"
        self.track_id = self.c.create_round_rect(
            self.x, self.y, self.x + self.w, self.y + self.h,
            radius=r,
            fill=self.track_color,
            outline=self.border_hex,  # FIX: hex only
            width=1,
            tags=self.tag_track
        )

        # fill
        self.tag_fill = f"fill_{id(self)}"
        self.fill_id = self.c.create_round_rect(
            self.x, self.y, self.x + r * 2, self.y + self.h,
            radius=r,
            fill=self.fill_color,
            outline="",
            width=0,
            tags=self.tag_fill
        )

        # knob
        self.tag_knob = f"knob_{id(self)}"
        if self.show_knob:
            k = self.h + 10
            self.knob_glow = None
            if self.active_glow:
                self.knob_glow = self.c.create_oval(
                    self.x, self.y, self.x + k, self.y + k,
                    fill="",
                    outline="",
                    tags=self.tag_knob
                )
            self.knob_id = self.c.create_oval(
                self.x, self.y, self.x + k, self.y + k,
                fill=self.knob_color,
                outline=CANVAS_SOFT_BORDER_2,  # FIX: hex only
                width=1,
                tags=self.tag_knob
            )
        else:
            self.knob_id = None
            self.knob_glow = None

        self._redraw()

    def _redraw(self):
        r = self.h // 2
        px = self._px_from_value()

        left = self.x
        top = self.y
        bottom = self.y + self.h
        right = max(left + r * 2, px)  # minimum pill width
        self.c.coords(self.fill_id, left, top, right, bottom)

        if self.knob_id:
            k = self.h + 10
            cx = px
            cy = self.y + self.h / 2
            x1 = cx - k / 2
            y1 = cy - k / 2
            x2 = cx + k / 2
            y2 = cy + k / 2

            if self.knob_glow:
                if self.dragging:
                    self.c.coords(self.knob_glow, x1 - 6, y1 - 6, x2 + 6, y2 + 6)
                    self.c.itemconfigure(self.knob_glow, outline="#2C6BFF", width=2)
                else:
                    self.c.coords(self.knob_glow, x1 - 6, y1 - 6, x2 + 6, y2 + 6)
                    self.c.itemconfigure(self.knob_glow, outline="", width=0)

            self.c.coords(self.knob_id, x1, y1, x2, y2)

    def _click(self, e):
        self.dragging = True
        self.set_value(self._value_from_px(e.x), invoke=True)

    def _drag(self, e):
        if not self.dragging:
            return
        self.set_value(self._value_from_px(e.x), invoke=True)

    def _release(self, e):
        self.dragging = False
        self._redraw()


class MusicPlayerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # Fixed size: 720x900 at scale 1.0. Override with RFID_UI_SCALE env var (e.g. 0.8, 1.2).
        self.ui_scale = 1.0
        try:
            env_scale = os.getenv("RFID_UI_SCALE")
            if env_scale:
                self.ui_scale = max(0.5, min(2.0, float(env_scale)))
        except Exception:
            pass

        self.app_w = int(round(BASE_W * self.ui_scale))
        self.app_h = int(round(BASE_H * self.ui_scale))

        def s(v: float) -> int:
            return int(round(float(v) * self.ui_scale))

        self._s = s

        self.is_playing = False
        self.current_uid = None
        self.current_folder = None
        self.current_song_path = None
        self.song_history = []
        self.volume_level = 0.7
        self.song_length = 0.0

        self.tap_count = 0
        self.last_tap_time = 0.0
        self.tap_reset_seconds = 10.0

        self.last_uid_seen = None
        self.last_uid_time = 0.0
        self.serial_min_interval = 0.25

        self.title_full = "Scan a Card"
        self._marquee_index = 0
        self._marquee_window_chars = 26

        self.wave_ids = []
        self.wave_vals = []
        self.wave_targets = []
        self.wave_count = 64
        self.wave_last_update = 0.0

        self.audio_available = False
        self._audio_init_started = False
        self._audio_init_error = None
        self._audio_backend = "none"  # "pygame" | "afplay" | "none"
        self._afplay_proc = None
        self._afplay_file = None
        self._afplay_started_at = 0.0
        self._afplay_offset = 0.0
        self._afplay_paused_at = None
        self._pygame_start_offset = 0.0
        self.compat_ui = False
        self._pending_folder_after_audio = None
        self._closing = False
        compat_env = os.getenv("RFID_COMPAT_UI")
        if compat_env is not None:
            v = compat_env.strip().lower()
            if v in ("1", "true", "yes", "on"):
                self.compat_ui = True
            elif v in ("0", "false", "no", "off"):
                self.compat_ui = False
            else:
                # Any other value means "auto"
                self.compat_ui = False

        try:
            # Tk 8.5 on macOS is unreliable with PhotoImage-heavy layouts. Always
            # use the canvas UI there, even if RFID_COMPAT_UI=0 is set somewhere.
            if sys.platform == "darwin" and float(getattr(tk, "TkVersion", 0.0)) < 8.6:
                self.compat_ui = True
        except Exception:
            pass

        startup_log(
            "starting",
            "python=", sys.executable,
            "cwd=", os.getcwd(),
            "tk=", getattr(tk, "TkVersion", "?"),
            "compat_ui=", self.compat_ui,
        )

        self.title("RFID Music Player")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.configure(bg=WIDGET_BG)
        # Set geometry before resizable. On macOS, resizable(False, False) can lock
        # the OS-assigned default size if geometry() has not been applied yet.
        self._set_window_geometry()
        self.minsize(self.app_w, self.app_h)
        self.maxsize(self.app_w, self.app_h)
        self.resizable(False, False)

        self._boot_label = tk.Label(
            self,
            text="Loading RFID Music Player...",
            bg=WIDGET_BG,
            fg=TEXT,
            font=("Helvetica", 18, "bold"),
        )
        self._boot_label.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.update_idletasks()

        try:
            self.create_widgets()
        except Exception as exc:
            print(f"Full UI failed, using compat UI: {type(exc).__name__}: {exc}", file=sys.stderr)
            self.compat_ui = True
            self._clear_widgets_for_fallback()
            self._create_widgets_compat()

        try:
            if getattr(self, "_boot_label", None) is not None:
                self._boot_label.destroy()
                self._boot_label = None
        except Exception:
            pass

        self.update_idletasks()
        self.deiconify()
        self.update()
        self._bring_to_front()
        self.after(350, self._ensure_visible)

        self._debug_canvas_state("after create_widgets")
        self._debug("tk", "TkVersion=", getattr(tk, "TkVersion", "?"), "compat_ui=", self.compat_ui)
        try:
            startup_log("ui_ready", "canvas_items=", len(self.bg_canvas.find_all()))
        except Exception as exc:
            startup_log("ui_ready_check_failed", type(exc).__name__, exc)

        self.update_progress()
        self.check_music_end()
        self.update_waveform_genuine()
        self.start_marquee()

        # Let Tk paint the first frame before audio/serial work begins.
        if "--smoke" not in sys.argv:
            self.after(100, self._start_audio_init)
            self.after(350, lambda: threading.Thread(target=self.read_serial, daemon=True).start())

    def _set_window_geometry(self):
        try:
            self.update_idletasks()
            x = max(0, (self.winfo_screenwidth() - self.app_w) // 2)
            y = max(0, (self.winfo_screenheight() - self.app_h) // 2)
            self.geometry(f"{self.app_w}x{self.app_h}+{x}+{y}")
        except Exception:
            self.geometry(f"{self.app_w}x{self.app_h}+80+40")

    def _bring_to_front(self):
        try:
            self.state("normal")
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(700, lambda: self.attributes("-topmost", False))
        except Exception as exc:
            self._debug("front failed:", exc)

    def _ensure_visible(self):
        try:
            self.update_idletasks()
            self.update()
            mapped = bool(self.winfo_ismapped())
            viewable = bool(self.winfo_viewable())
        except Exception:
            mapped = True
            viewable = True

        if mapped and viewable:
            return

        try:
            self._set_window_geometry()
            self.deiconify()
            self._bring_to_front()
            self.update_idletasks()
            self.update()
        except Exception as exc:
            self._debug("ensure_visible failed:", exc)

        try:
            startup_log("ui_visibility", "mapped=", self.winfo_ismapped(), "viewable=", self.winfo_viewable())
        except Exception:
            pass

    def _clear_widgets_for_fallback(self):
        for child in list(self.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

    def _on_close(self):
        self._closing = True
        try:
            self._audio_stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _ui_after(self, delay_ms, callback):
        if self._closing:
            return
        try:
            self.after(delay_ms, callback)
        except RuntimeError:
            pass
        except tk.TclError:
            pass

    def _debug(self, *parts):
        if os.getenv("RFID_DEBUG") == "1":
            print("[RFID]", *parts, flush=True)

    def _debug_canvas_state(self, label: str):
        if os.getenv("RFID_DEBUG") != "1":
            return
        try:
            items = list(self.bg_canvas.find_all())
            self._debug(label, "canvas_items=", len(items))
            if items:
                sample = items[:5]
                self._debug(label, "sample_types=", [self.bg_canvas.type(i) for i in sample])
        except Exception as e:
            self._debug(label, "canvas_debug_failed", repr(e))

    def _start_audio_init(self):
        if self._audio_init_started:
            return
        self._audio_init_started = True

        if pygame is None:
            if sys.platform == "darwin" and shutil.which("afplay"):
                self._audio_backend = "afplay"
                self.audio_available = True
                self._audio_init_error = None
                self._debug("audio: afplay ready")
                try:
                    self.bg_canvas.itemconfigure(self.status_text_id, text="Ready. Scan an RFID card to begin.")
                except Exception:
                    pass
                return

            self._audio_backend = "none"
            self.audio_available = False
            self._audio_init_error = "no audio backend (install pygame or use macOS afplay)"
            self._debug("audio: no backend")
            return

        self._audio_backend = "pygame"

        self.bg_canvas.itemconfigure(self.status_text_id, text="Initializing audio…")

        def worker():
            ok = False
            err = None
            try:
                pygame.mixer.init()
                ok = True
            except Exception as e:
                err = str(e)

            def done():
                self.audio_available = ok
                self._audio_init_error = err
                if ok:
                    try:
                        pygame.mixer.music.set_volume(self.volume_level)
                    except Exception:
                        pass
                    self._debug("audio: ready")
                    self.bg_canvas.itemconfigure(self.status_text_id, text="Ready. Scan an RFID card to begin.")
                    pending = self._pending_folder_after_audio
                    self._pending_folder_after_audio = None
                    if pending and self.current_folder:
                        self.play_random_song_from_folder(pending)
                else:
                    if sys.platform == "darwin" and shutil.which("afplay"):
                        self._audio_backend = "afplay"
                        self.audio_available = True
                        self._audio_init_error = None
                        self._debug("audio: pygame failed, using afplay", err)
                        self.bg_canvas.itemconfigure(self.status_text_id, text="Ready. Scan an RFID card to begin.")
                        pending = self._pending_folder_after_audio
                        self._pending_folder_after_audio = None
                        if pending and self.current_folder:
                            self.play_random_song_from_folder(pending)
                    else:
                        self._audio_backend = "none"
                        self._debug("audio: failed", err)
                        self.bg_canvas.itemconfigure(
                            self.status_text_id,
                            text="Audio unavailable (pygame mixer init failed).",
                        )

            try:
                self._ui_after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _audio_stop(self):
        if self._audio_backend == "pygame" and self.audio_available and pygame is not None:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            return

        if self._audio_backend == "afplay":
            proc = self._afplay_proc
            self._afplay_proc = None
            self._afplay_paused_at = None
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            return

    def _audio_play_file(self, path: str, start_at: float = 0.0):
        if not self.audio_available:
            return

        if self._audio_backend == "pygame" and pygame is not None:
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self.volume_level)
                pygame.mixer.music.play(start=start_at)
                self._pygame_start_offset = start_at
            except Exception as e:
                self._debug("audio play error:", e)
                self.audio_available = False
            return

        if self._audio_backend == "afplay":
            self._audio_stop()
            self._afplay_file = path
            self._afplay_offset = max(0.0, float(start_at or 0.0))
            self._afplay_started_at = time.time()
            self._afplay_paused_at = None

            vol = max(0.0, min(1.0, float(self.volume_level)))
            cmd = ["afplay", "-v", f"{vol:.3f}"]
            if self._afplay_offset > 0.0:
                cmd += ["-s", f"{self._afplay_offset:.3f}"]
            cmd.append(path)
            try:
                self._afplay_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                self._debug("afplay spawn failed:", e)
                self.audio_available = False
                self._audio_backend = "none"
            return

    def _audio_pause(self):
        if not self.audio_available:
            return
        if self._audio_backend == "pygame" and pygame is not None:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
            return
        if self._audio_backend == "afplay":
            proc = self._afplay_proc
            if proc and proc.poll() is None and self._afplay_paused_at is None:
                try:
                    proc.send_signal(signal.SIGSTOP)
                    self._afplay_paused_at = time.time()
                except Exception:
                    pass

    def _audio_unpause(self):
        if not self.audio_available:
            return
        if self._audio_backend == "pygame" and pygame is not None:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
            return
        if self._audio_backend == "afplay":
            proc = self._afplay_proc
            if proc and proc.poll() is None and self._afplay_paused_at is not None:
                try:
                    proc.send_signal(signal.SIGCONT)
                    pause_dur = max(0.0, time.time() - float(self._afplay_paused_at))
                    self._afplay_started_at += pause_dur
                    self._afplay_paused_at = None
                except Exception:
                    pass

    def _audio_set_volume(self, v: float):
        try:
            self.volume_level = float(v)
        except Exception:
            self.volume_level = 0.7

        if not self.audio_available:
            return

        if self._audio_backend == "pygame" and pygame is not None:
            try:
                pygame.mixer.music.set_volume(self.volume_level)
            except Exception:
                pass
            return

        if self._audio_backend == "afplay":
            # afplay volume is set at process start; restart from current position.
            pos = self._audio_get_pos_seconds()
            if self._afplay_file and pos >= 0:
                self._audio_play_file(self._afplay_file, start_at=pos)

    def _audio_set_pos_seconds(self, seconds: float):
        if not self.audio_available:
            return
        seconds = max(0.0, float(seconds or 0.0))
        if self._audio_backend == "pygame" and pygame is not None:
            try:
                if self.current_song_path:
                    pygame.mixer.music.load(self.current_song_path)
                    pygame.mixer.music.set_volume(self.volume_level)
                    pygame.mixer.music.play(start=seconds)
                    self._pygame_start_offset = seconds
            except Exception:
                pass
            return
        if self._audio_backend == "afplay":
            if self._afplay_file:
                self._audio_play_file(self._afplay_file, start_at=seconds)

    def _audio_get_pos_seconds(self) -> float:
        if not self.audio_available:
            return 0.0
        if self._audio_backend == "pygame" and pygame is not None:
            try:
                pos_ms = pygame.mixer.music.get_pos()
                if pos_ms == -1:
                    return 0.0
                return max(0.0, self._pygame_start_offset + pos_ms / 1000.0)
            except Exception:
                return 0.0
        if self._audio_backend == "afplay":
            proc = self._afplay_proc
            if not proc or proc.poll() is not None:
                return 0.0
            now = time.time()
            if self._afplay_paused_at is not None:
                now = float(self._afplay_paused_at)
            return max(0.0, float(self._afplay_offset) + (now - float(self._afplay_started_at)))
        return 0.0

    def _audio_is_busy(self) -> bool:
        if not self.audio_available:
            return False
        if self._audio_backend == "pygame" and pygame is not None:
            try:
                return bool(pygame.mixer.music.get_busy())
            except Exception:
                return False
        if self._audio_backend == "afplay":
            proc = self._afplay_proc
            return bool(proc and proc.poll() is None)
        return False

    def _abs_path(self, rel):
        if not rel:
            return None
        if os.path.isabs(str(rel)):
            return str(rel)
        return os.path.join(BASE_DIR, str(rel))

    def load_image_safe(self, filename, size):
        path = self._abs_path(filename)
        try:
            img = Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        except Exception:
            img = Image.new("RGBA", size, (15, 20, 35, 255))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([18, 18, size[0]-18, size[1]-18], radius=26, fill=(30, 50, 85, 255))
            d.text((30, 30), f"Missing: {filename}", fill=(255, 255, 255, 180))
        return img

    def make_glass_panel_rgba(self, bg_img_rgba, box, radius=22, blur=12, tint=PANEL_TINT):
        x1, y1, x2, y2 = box
        crop = bg_img_rgba.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(blur))
        crop = Image.alpha_composite(crop, Image.new("RGBA", crop.size, tint))

        mask = Image.new("L", crop.size, 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, crop.size[0]-1, crop.size[1]-1], radius=radius, fill=255)
        crop.putalpha(mask)

        border = Image.new("RGBA", crop.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(border)
        bd.rounded_rectangle([1, 1, crop.size[0]-2, crop.size[1]-2], radius=radius, outline=PANEL_BORDER, width=2)
        crop = Image.alpha_composite(crop, border)

        return crop

    def make_glass_panel(self, bg_img_rgba, box, radius=22, blur=12, tint=PANEL_TINT):
        crop = self.make_glass_panel_rgba(bg_img_rgba, box, radius=radius, blur=blur, tint=tint)
        if self.compat_ui:
            crop = _flatten_rgba(crop, WIDGET_BG)
        return ImageTk.PhotoImage(crop, master=self)

    def make_plain_panel(self, box, radius=22, fill=(8, 16, 28, 50), border=PANEL_BORDER):
        x1, y1, x2, y2 = box
        w = max(1, int(x2 - x1))
        h = max(1, int(y2 - y1))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill)
        d.rounded_rectangle([1, 1, w - 2, h - 2], radius=radius, outline=border, width=2)
        if self.compat_ui:
            img = _flatten_rgba(img, WIDGET_BG)
        return ImageTk.PhotoImage(img, master=self)

    def create_round_button_images(self, fill_color, hover_color, text, size):
        def make(bg):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse((3, 3, size-3, size-3), fill=bg, outline=(255, 255, 255, 35), width=1)

            icon_color = (243, 247, 255, 255)
            icon = text

            # Draw icons with shapes so they render correctly on macOS without special symbol fonts.
            def draw_icon(icon_text: str):
                cx = size / 2.0
                cy = size / 2.0
                pad = max(12, int(size * 0.28))
                x1 = pad
                y1 = pad
                x2 = size - pad
                y2 = size - pad

                if icon_text in ("▶️", "PLAY"):
                    pts = [(x1, y1), (x1, y2), (x2, cy)]
                    d.polygon(pts, fill=icon_color)
                    return True

                if icon_text in ("⏸", "PAUSE"):
                    bar_w = max(4, int(size * 0.10))
                    gap = max(4, int(size * 0.08))
                    total = bar_w * 2 + gap
                    left = int(cx - total / 2)
                    top = y1
                    bottom = y2
                    d.rounded_rectangle([left, top, left + bar_w, bottom], radius=bar_w // 2, fill=icon_color)
                    d.rounded_rectangle([left + bar_w + gap, top, left + bar_w + gap + bar_w, bottom], radius=bar_w // 2, fill=icon_color)
                    return True

                if icon_text in ("⏮", "PREV"):
                    bar_w = max(3, int(size * 0.06))
                    d.rounded_rectangle([x1, y1, x1 + bar_w, y2], radius=bar_w // 2, fill=icon_color)
                    pts = [(x2, y1), (x2, y2), (x1 + bar_w, cy)]
                    d.polygon(pts, fill=icon_color)
                    return True

                if icon_text in ("⏭", "NEXT"):
                    bar_w = max(3, int(size * 0.06))
                    d.rounded_rectangle([x2 - bar_w, y1, x2, y2], radius=bar_w // 2, fill=icon_color)
                    pts = [(x1, y1), (x1, y2), (x2 - bar_w, cy)]
                    d.polygon(pts, fill=icon_color)
                    return True

                return False

            drew = draw_icon(icon)
            if not drew:
                try:
                    font = ImageFont.truetype("Arial.ttf", max(10, size // 3))
                except Exception:
                    font = ImageFont.load_default()
                bbox = d.textbbox((0, 0), text, font=font)
                tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
                d.text(((size - tw)/2, (size - th)/2 - size*0.03), text, font=font, fill=icon_color)
            if self.compat_ui:
                img2 = _flatten_rgba(img, WIDGET_BG)
                return ImageTk.PhotoImage(img2, master=self)
            return ImageTk.PhotoImage(img, master=self)
        return make(fill_color), make(hover_color)

    def create_rounded_image(self, image_path, size, radius=34):
        path = self._abs_path(image_path) if image_path else None
        try:
            if path and os.path.exists(path):
                base = Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
            else:
                raise FileNotFoundError
        except Exception:
            base = Image.new("RGBA", size, (25, 35, 60, 255))

        mask = Image.new("L", size, 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=255)
        base.putalpha(mask)

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle([1, 1, size[0]-2, size[1]-2], radius=radius, outline=(255, 255, 255, 40), width=2)
        base = Image.alpha_composite(base, overlay)

        if self.compat_ui:
            base2 = _flatten_rgba(base, WIDGET_BG)
            return ImageTk.PhotoImage(base2, master=self)
        return ImageTk.PhotoImage(base, master=self)

    def create_widgets(self):
        if self.compat_ui:
            return self._create_widgets_compat()

        s = self._s

        self.bg_canvas = tk.Canvas(self, width=self.app_w, height=self.app_h, highlightthickness=0, bd=0, bg=WIDGET_BG)
        self.bg_canvas.pack(fill="both", expand=True)

        try:
            self.bg_canvas.update_idletasks()
        except Exception:
            pass

        self.bg_rgba = self.load_image_safe(UI_BG_IMAGE, (self.app_w, self.app_h))

        # Compose the base background as a single RGB image in compat mode to avoid alpha issues on macOS system Tk.
        overlay_alpha = 0 if UI_BG_STYLE == "raw" else 55
        overlay = Image.new("RGBA", (self.app_w, self.app_h), (0, 0, 0, overlay_alpha))
        base_bg = Image.alpha_composite(self.bg_rgba, overlay)

        self.header_box   = (s(28),  s(22),  self.app_w - s(28),  s(110))
        self.main_box     = (s(28),  s(130), self.app_w - s(28),  s(495))
        self.progress_box = (s(28),  s(515), self.app_w - s(28),  s(655))
        self.control_box  = (s(28),  s(675), self.app_w - s(28),  s(870))

        hb, mb, pb, cb = self.header_box, self.main_box, self.progress_box, self.control_box

        if self.compat_ui:
            for box, radius in ((hb, 22), (mb, 26), (pb, 22), (cb, 26)):
                x1, y1, x2, y2 = box
                panel = self.make_glass_panel_rgba(base_bg, box, radius=radius, blur=14)
                base_bg.alpha_composite(panel, dest=(x1, y1))

            self.bg_img = ImageTk.PhotoImage(base_bg.convert("RGB"), master=self)
            self.bg_canvas.create_image(self.app_w // 2, self.app_h // 2, image=self.bg_img)
            self.overlay_img = None
            self.header_panel = None
            self.main_panel = None
            self.prog_panel = None
            self.ctrl_panel = None
        else:
            self.bg_img = ImageTk.PhotoImage(base_bg, master=self)
            self.bg_canvas.create_image(self.app_w // 2, self.app_h // 2, image=self.bg_img)

            if UI_BG_STYLE == "glass":
                overlay2 = Image.new("RGBA", (self.app_w, self.app_h), (0, 0, 0, 55))
                self.overlay_img = ImageTk.PhotoImage(overlay2, master=self)
                self.bg_canvas.create_image(self.app_w // 2, self.app_h // 2, image=self.overlay_img)

                self.header_panel = self.make_glass_panel(self.bg_rgba, hb, radius=22, blur=14)
                self.main_panel   = self.make_glass_panel(self.bg_rgba, mb, radius=26, blur=14)
                self.prog_panel   = self.make_glass_panel(self.bg_rgba, pb, radius=22, blur=14)
                self.ctrl_panel   = self.make_glass_panel(self.bg_rgba, cb, radius=26, blur=14)
            else:
                self.overlay_img = None
                self.header_panel = self.make_plain_panel(hb, radius=22)
                self.main_panel   = self.make_plain_panel(mb, radius=26)
                self.prog_panel   = self.make_plain_panel(pb, radius=22)
                self.ctrl_panel   = self.make_plain_panel(cb, radius=26)

            self.bg_canvas.create_image((hb[0]+hb[2])//2, (hb[1]+hb[3])//2, image=self.header_panel)
            self.bg_canvas.create_image((mb[0]+mb[2])//2, (mb[1]+mb[3])//2, image=self.main_panel)
            self.bg_canvas.create_image((pb[0]+pb[2])//2, (pb[1]+pb[3])//2, image=self.prog_panel)
            self.bg_canvas.create_image((cb[0]+cb[2])//2, (cb[1]+cb[3])//2, image=self.ctrl_panel)

        # Header
        self.bg_canvas.create_text(hb[0]+s(26), hb[1]+s(30), text="RFID Music Player", fill=TEXT,
                                   font=("Segoe UI", max(12, s(18)), "bold"), anchor="w")
        self.bg_canvas.create_text(hb[0]+s(26), hb[1]+s(62),
                                   text="Tap & Listen",
                                   fill=MUTED, font=("Segoe UI", max(9, s(10))), anchor="w")
        self.serial_text_id = self.bg_canvas.create_text(hb[2]-s(26), hb[1]+s(34),
                                                         text="SERIAL: CONNECTING", fill=ACCENT,
                                                         font=("Segoe UI", max(9, s(10)), "bold"), anchor="e")

        # Left image box
        art_x = mb[0] + s(26)
        art_y = mb[1] + s(28)
        cover_w = s(280)
        cover_h = s(280)
        self.cover_canvas = tk.Canvas(self, width=cover_w, height=cover_h, highlightthickness=0, bd=0, bg=WIDGET_BG)
        self.bg_canvas.create_window(art_x, art_y, anchor="nw", window=self.cover_canvas)

        # Cover: show artwork + a frame image on top (two pictures)
        self.cover_frame_img = self.create_rounded_image(SIDE_BOX_IMAGE, (s(270), s(270)), radius=max(16, s(34)))
        self.cover_art_img = self.create_rounded_image(None, (s(250), s(250)), radius=max(14, s(30)))
        self.cover_canvas.delete("all")
        self.cover_art_item = self.cover_canvas.create_image(cover_w // 2, cover_h // 2, image=self.cover_art_img)
        self.cover_frame_item = self.cover_canvas.create_image(cover_w // 2, cover_h // 2, image=self.cover_frame_img)

        # Right info
        self.info_x = art_x + s(305)
        self.title_text_id = self.bg_canvas.create_text(self.info_x, mb[1]+s(55), text="Scan a Card",
                                                        fill=TEXT, font=("Segoe UI", max(16, s(30)), "bold"), anchor="w")
        self.artist_text_id = self.bg_canvas.create_text(self.info_x, mb[1]+s(105), text="Waiting for RFID Tag",
                                                         fill=MUTED, font=("Segoe UI", max(10, s(12))), anchor="w")
        self.bg_canvas.create_line(self.info_x, mb[1]+s(140), mb[2]-s(30), mb[1]+s(140), fill="#2A3D5E")
        self.bg_canvas.create_text(self.info_x, mb[1]+s(170), text="Status", fill=MUTED,
                                   font=("Segoe UI", max(9, s(10))), anchor="w")
        self.status_text_id = self.bg_canvas.create_text(self.info_x, mb[1]+s(205), text="Ready. Scan an RFID card to begin.",
                                                         fill=ACCENT, font=("Segoe UI", max(10, s(12)), "bold"), anchor="w")

        # Extra side thumbnail (second picture on the side)
        thumb_size = s(110)
        thumb_x = mb[2] - s(26) - thumb_size // 2
        thumb_y = mb[1] + s(260)
        self.side_thumb_img = self.create_rounded_image(SIDE_BOX_IMAGE, (thumb_size, thumb_size), radius=max(12, s(20)))
        self.side_thumb_item = self.bg_canvas.create_image(thumb_x, thumb_y, image=self.side_thumb_img)

        # Progress time texts
        self.current_time_text_id = self.bg_canvas.create_text(pb[0]+s(26), pb[1]+s(28), text="0:00",
                                                               fill=MUTED, font=("Segoe UI", max(9, s(10))), anchor="w")
        self.total_time_text_id = self.bg_canvas.create_text(pb[2]-s(26), pb[1]+s(28), text="0:00",
                                                             fill=MUTED, font=("Segoe UI", max(9, s(10))), anchor="e")

        # NEW Progress slider (canvas)
        prog_x = pb[0] + s(26)
        prog_y = pb[1] + s(50)
        prog_w = pb[2] - pb[0] - s(52)
        prog_h = max(10, s(12))

        self.progress_slider = CanvasSlider(
            self.bg_canvas, prog_x, prog_y,
            prog_w, prog_h,
            min_val=0.0, max_val=100.0, value=0.0,
            on_change=self._on_progress_change,
            track_color="#223552",
            fill_color=ACCENT,
            knob_color=TEXT,
            border_hex=CANVAS_SOFT_BORDER,
            show_knob=True
        )

        # Waveform
        self.wave_area = (pb[0]+s(26), pb[1]+s(86), pb[2]-s(26), pb[3]-s(18))
        self._init_waveform_bars()

        # Buttons
        self.prev_img, self.prev_img_hover = self.create_round_button_images("#13233A", "#1A3354", "⏮", max(44, s(64)))
        self.play_img, self.play_img_hover = self.create_round_button_images("#2C6BFF", "#4FA3FF", "▶️", max(60, s(90)))
        self.pause_img, self.pause_img_hover = self.create_round_button_images("#2C6BFF", "#4FA3FF", "⏸", max(60, s(90)))
        self.next_img, self.next_img_hover = self.create_round_button_images("#13233A", "#1A3354", "⏭", max(44, s(64)))

        btn_y = cb[1] + s(55)
        center_x = (cb[0] + cb[2]) // 2

        self.prev_item = self.bg_canvas.create_image(center_x - s(160), btn_y, image=self.prev_img)
        self.play_item = self.bg_canvas.create_image(center_x, btn_y, image=self.play_img)
        self.next_item = self.bg_canvas.create_image(center_x + s(160), btn_y, image=self.next_img)

        self.bg_canvas.tag_bind(self.prev_item, "<Button-1>", lambda e: self.previous_song())
        self.bg_canvas.tag_bind(self.play_item, "<Button-1>", lambda e: self.toggle_play())
        self.bg_canvas.tag_bind(self.next_item, "<Button-1>", lambda e: self.next_song())

        self.bg_canvas.tag_bind(self.prev_item, "<Enter>", lambda e: self.bg_canvas.itemconfigure(self.prev_item, image=self.prev_img_hover))
        self.bg_canvas.tag_bind(self.prev_item, "<Leave>", lambda e: self.bg_canvas.itemconfigure(self.prev_item, image=self.prev_img))
        self.bg_canvas.tag_bind(self.next_item, "<Enter>", lambda e: self.bg_canvas.itemconfigure(self.next_item, image=self.next_img_hover))
        self.bg_canvas.tag_bind(self.next_item, "<Leave>", lambda e: self.bg_canvas.itemconfigure(self.next_item, image=self.next_img))
        self.bg_canvas.tag_bind(self.play_item, "<Enter>", lambda e: self._play_hover(True))
        self.bg_canvas.tag_bind(self.play_item, "<Leave>", lambda e: self._play_hover(False))

        # NEW Volume slider (canvas)
        self.bg_canvas.create_text(cb[0]+s(26), cb[1]+s(140), text="Master Volume", fill=MUTED,
                                   font=("Segoe UI", max(9, s(10))), anchor="w")

        vol_x = cb[0] + s(140)
        vol_y = cb[1] + s(132)
        vol_w = cb[2] - cb[0] - s(170)
        vol_h = max(10, s(12))

        self.volume_slider = CanvasSlider(
            self.bg_canvas, vol_x, vol_y,
            vol_w, vol_h,
            min_val=0.0, max_val=1.0, value=self.volume_level,
            on_change=self._on_volume_change,
            track_color="#223552",
            fill_color="#2C6BFF",
            knob_color=TEXT,
            border_hex=CANVAS_SOFT_BORDER,
            show_knob=True
        )

        self.bg_canvas.create_text(cb[0]+s(26), cb[1]+s(175),
                                   text="Place an RFID card on the reader to control playback.",
                                   fill=MUTED, font=("Segoe UI", max(8, s(9))), anchor="w")

        # Keep image refs to avoid Tk image GC issues (especially on macOS).
        self._img_refs = [
            self.bg_img,
            self.overlay_img,
            self.header_panel,
            self.main_panel,
            self.prog_panel,
            self.ctrl_panel,
            getattr(self, "cover_frame_img", None),
            getattr(self, "cover_art_img", None),
            getattr(self, "side_thumb_img", None),
            self.prev_img,
            self.prev_img_hover,
            self.play_img,
            self.play_img_hover,
            self.pause_img,
            self.pause_img_hover,
            self.next_img,
            self.next_img_hover,
        ]

        # Marker if nothing ended up on the canvas for any reason.
        try:
            if len(self.bg_canvas.find_all()) == 0:
                self.bg_canvas.configure(bg="#300000")
                self.bg_canvas.create_text(
                    self.app_w // 2,
                    self.app_h // 2,
                    text="UI failed to render (check terminal for errors)",
                    fill="#FFFFFF",
                    font=("TkDefaultFont", 14, "bold"),
                )
        except Exception:
            pass

    def _create_widgets_compat(self):
        # Canvas-only fallback for older/system Tk on macOS: avoid PhotoImage entirely.
        s = self._s
        self.bg_canvas = tk.Canvas(self, width=self.app_w, height=self.app_h, highlightthickness=0, bd=0, bg=WIDGET_BG)
        self.bg_canvas.pack(fill="both", expand=True)

        self.header_box   = (s(28),  s(22),  self.app_w - s(28),  s(110))
        self.main_box     = (s(28),  s(130), self.app_w - s(28),  s(495))
        self.progress_box = (s(28),  s(515), self.app_w - s(28),  s(655))
        self.control_box  = (s(28),  s(675), self.app_w - s(28),  s(870))

        hb, mb, pb, cb = self.header_box, self.main_box, self.progress_box, self.control_box

        def panel(box, fill="#0F1930", outline="#223552", r=22):
            x1, y1, x2, y2 = box
            self.bg_canvas.create_round_rect(x1, y1, x2, y2, radius=r, fill=fill, outline=outline, width=1)

        panel(hb, fill="#0F172A", outline="#1E2A44", r=22)
        panel(mb, fill="#0E1730", outline="#1E2A44", r=26)
        panel(pb, fill="#0F172A", outline="#1E2A44", r=22)
        panel(cb, fill="#0E1730", outline="#1E2A44", r=26)

        # Header
        self.bg_canvas.create_text(hb[0]+s(26), hb[1]+s(30), text="RFID Music Player", fill=TEXT,
                                   font=("Helvetica", max(12, s(18)), "bold"), anchor="w")
        self.bg_canvas.create_text(hb[0]+s(26), hb[1]+s(62), text="Tap & Listen", fill=MUTED,
                                   font=("Helvetica", max(9, s(10))), anchor="w")
        self.serial_text_id = self.bg_canvas.create_text(hb[2]-s(26), hb[1]+s(34), text="SERIAL: CONNECTING",
                                                         fill=ACCENT, font=("Helvetica", max(9, s(10)), "bold"), anchor="e")

        # Left cover placeholder
        art_x = mb[0] + s(26)
        art_y = mb[1] + s(28)
        cover_box = (art_x, art_y, art_x + s(280), art_y + s(280))
        self.bg_canvas.create_round_rect(*cover_box, radius=34, fill="#111B2D", outline="#223552", width=2)
        self.bg_canvas.create_text(art_x + s(140), art_y + s(140), text="Cover", fill=MUTED, font=("Helvetica", max(10, s(12)), "bold"))
        self.cover_canvas = None
        self.cover_item = None

        # Right info
        self.info_x = art_x + s(305)
        self.title_text_id = self.bg_canvas.create_text(self.info_x, mb[1]+s(55), text="Scan a Card",
                                                        fill=TEXT, font=("Helvetica", max(16, s(30)), "bold"), anchor="w")
        self.artist_text_id = self.bg_canvas.create_text(self.info_x, mb[1]+s(105), text="Waiting for RFID Tag",
                                                         fill=MUTED, font=("Helvetica", max(10, s(12))), anchor="w")
        self.bg_canvas.create_line(self.info_x, mb[1]+s(140), mb[2]-s(30), mb[1]+s(140), fill="#2A3D5E")
        self.bg_canvas.create_text(self.info_x, mb[1]+s(170), text="Status", fill=MUTED,
                                   font=("Helvetica", max(9, s(10))), anchor="w")
        self.status_text_id = self.bg_canvas.create_text(self.info_x, mb[1]+s(205), text="Ready. Scan an RFID card to begin.",
                                                         fill=ACCENT, font=("Helvetica", max(10, s(12)), "bold"), anchor="w")

        # Progress time texts
        self.current_time_text_id = self.bg_canvas.create_text(pb[0]+26, pb[1]+28, text="0:00",
                                                               fill=MUTED, font=("Helvetica", 10), anchor="w")
        self.total_time_text_id = self.bg_canvas.create_text(pb[2]-26, pb[1]+28, text="0:00",
                                                             fill=MUTED, font=("Helvetica", 10), anchor="e")

        # Progress slider
        prog_x = pb[0] + s(26)
        prog_y = pb[1] + s(50)
        prog_w = (pb[2] - pb[0] - s(52))
        prog_h = max(10, s(12))
        self.progress_slider = CanvasSlider(
            self.bg_canvas, prog_x, prog_y,
            prog_w, prog_h,
            min_val=0.0, max_val=100.0, value=0.0,
            on_change=self._on_progress_change,
            track_color="#223552",
            fill_color=ACCENT,
            knob_color=TEXT,
            border_hex=CANVAS_SOFT_BORDER,
            show_knob=True
        )

        # Waveform
        self.wave_area = (pb[0]+26, pb[1]+86, pb[2]-26, pb[3]-18)
        self._init_waveform_bars()

        # Controls (simple circles + text)
        btn_y = cb[1] + 55
        center_x = (cb[0] + cb[2]) // 2

        def circle_button(cx, label, fill, r):
            x1, y1, x2, y2 = cx - r, btn_y - r, cx + r, btn_y + r
            tag = f"btn_{label}_{cx}"
            self.bg_canvas.create_oval(x1, y1, x2, y2, fill=fill, outline="#2A3D5E", width=2, tags=tag)
            self.bg_canvas.create_text(cx, btn_y, text=label, fill=TEXT, font=("Helvetica", 18, "bold"), tags=tag)
            return tag

        prev_tag = circle_button(center_x - 160, "⏮", "#13233A", 32)
        play_tag = circle_button(center_x, "▶️", "#2C6BFF", 45)
        next_tag = circle_button(center_x + 160, "⏭", "#13233A", 32)

        self.prev_item = None
        self.play_item = None
        self.next_item = None
        self._compat_play_tag = play_tag

        self.bg_canvas.tag_bind(prev_tag, "<Button-1>", lambda e: self.previous_song())
        self.bg_canvas.tag_bind(play_tag, "<Button-1>", lambda e: self.toggle_play())
        self.bg_canvas.tag_bind(next_tag, "<Button-1>", lambda e: self.next_song())

        # Volume slider
        self.bg_canvas.create_text(cb[0]+26, cb[1]+140, text="Master Volume", fill=MUTED,
                                   font=("Helvetica", 10), anchor="w")

        vol_x = cb[0] + s(140)
        vol_y = cb[1] + s(132)
        vol_w = (cb[2] - cb[0] - s(170))
        vol_h = max(10, s(12))

        self.volume_slider = CanvasSlider(
            self.bg_canvas, vol_x, vol_y,
            vol_w, vol_h,
            min_val=0.0, max_val=1.0, value=self.volume_level,
            on_change=self._on_volume_change,
            track_color="#223552",
            fill_color="#2C6BFF",
            knob_color=TEXT,
            border_hex=CANVAS_SOFT_BORDER,
            show_knob=True
        )

        self.bg_canvas.create_text(cb[0]+26, cb[1]+175,
                                   text="Place an RFID card on the reader to control playback.",
                                   fill=MUTED, font=("Helvetica", 9), anchor="w")
        self.bg_canvas.create_text(
            cb[2] - 26,
            cb[3] - 18,
            text="Compat UI (no images). Install Tk 8.6 for full UI.",
            fill="#7F8AA0",
            font=("Helvetica", 9),
            anchor="e",
        )

        self._img_refs = []

    def set_cover(self, cover_path: Optional[str]):
        if self.cover_canvas is None:
            return
        s = self._s
        img_path = cover_path or None
        self.cover_art_img = self.create_rounded_image(img_path, (s(250), s(250)), radius=max(14, s(30)))
        try:
            self.cover_canvas.itemconfigure(self.cover_art_item, image=self.cover_art_img)
        except Exception:
            self.cover_canvas.delete("all")
            cover_w = s(280)
            cover_h = s(280)
            self.cover_art_item = self.cover_canvas.create_image(cover_w // 2, cover_h // 2, image=self.cover_art_img)
            self.cover_frame_item = self.cover_canvas.create_image(cover_w // 2, cover_h // 2, image=self.cover_frame_img)

        # Update side thumbnail too
        try:
            if hasattr(self, "side_thumb_item"):
                thumb_size = s(110)
                self.side_thumb_img = self.create_rounded_image(img_path, (thumb_size, thumb_size), radius=max(12, s(20)))
                self.bg_canvas.itemconfigure(self.side_thumb_item, image=self.side_thumb_img)
        except Exception:
            pass

    def _play_hover(self, entering: bool):
        if self.compat_ui or not getattr(self, "play_item", None):
            return
        if entering:
            self.bg_canvas.itemconfigure(self.play_item, image=self.pause_img_hover if self.is_playing else self.play_img_hover)
        else:
            self.bg_canvas.itemconfigure(self.play_item, image=self.pause_img if self.is_playing else self.play_img)

    def _set_play_button_state(self, playing: bool):
        try:
            if self.compat_ui or not getattr(self, "play_item", None):
                return
            self.bg_canvas.itemconfigure(self.play_item, image=self.pause_img if playing else self.play_img)
        except Exception:
            pass

    # ---------- Marquee ----------
    def set_title_text(self, text: str):
        self.title_full = text if text else "Unknown"
        self._marquee_index = 0
        if len(self.title_full) <= self._marquee_window_chars:
            self.bg_canvas.itemconfigure(self.title_text_id, text=self.title_full)

    def start_marquee(self):
        if len(self.title_full) <= self._marquee_window_chars:
            self.bg_canvas.itemconfigure(self.title_text_id, text=self.title_full)
        else:
            pad = "   •   "
            s = self.title_full + pad
            i = self._marquee_index % len(s)
            rotated = s[i:] + s[:i]
            visible = rotated[:self._marquee_window_chars]
            self.bg_canvas.itemconfigure(self.title_text_id, text=visible)
            self._marquee_index += 1
        self.after(140, self.start_marquee)

    # ---------- Waveform ----------
    def _init_waveform_bars(self):
        x1, y1, x2, y2 = self.wave_area
        w = x2 - x1
        h = y2 - y1

        self.wave_ids = []
        self.wave_vals = [0.18] * self.wave_count
        self.wave_targets = [0.18] * self.wave_count

        gap = 2
        bar_w = max(2, int((w - (self.wave_count - 1) * gap) / self.wave_count))
        if bar_w < 2:
            bar_w = 2

        for i in range(self.wave_count):
            bx1 = x1 + i * (bar_w + gap)
            bx2 = bx1 + bar_w
            by2 = y2
            by1 = by2 - 4
            rid = self.bg_canvas.create_rectangle(bx1, by1, bx2, by2, fill=ACCENT, width=0)
            self.wave_ids.append(rid)

    def update_waveform_genuine(self):
        now = time.time()
        idle_base = 0.14

        if self.is_playing:
            if now - self.wave_last_update > 0.10:
                base = 0.16 + 0.25 * self.volume_level
                for i in range(self.wave_count):
                    wave = 0.22 * (1 + (i % 7) / 10.0)
                    rnd = random.random() * 0.55
                    self.wave_targets[i] = min(1.0, base + wave * rnd)
                self.wave_last_update = now

            for i in range(self.wave_count):
                self.wave_vals[i] += (self.wave_targets[i] - self.wave_vals[i]) * 0.18
        else:
            if now - self.wave_last_update > 0.25:
                for i in range(self.wave_count):
                    self.wave_targets[i] = idle_base + random.random() * 0.10
                self.wave_last_update = now

            for i in range(self.wave_count):
                self.wave_vals[i] += (self.wave_targets[i] - self.wave_vals[i]) * 0.10

        x1, y1, x2, y2 = self.wave_area
        h = y2 - y1
        max_h = h * 0.92

        for i, rid in enumerate(self.wave_ids):
            v = self.wave_vals[i]
            bh = max(3, v * max_h)
            by2 = y2
            by1 = y2 - bh
            coords = self.bg_canvas.coords(rid)
            self.bg_canvas.coords(rid, coords[0], by1, coords[2], by2)

        self.after(60, self.update_waveform_genuine)

    # ---------- Slider callbacks ----------
    def _on_volume_change(self, v: float):
        self._audio_set_volume(v)

    def _on_progress_change(self, v: float):
        if self.progress_slider.dragging:
            self._audio_set_pos_seconds(v)

    # ---------- Progress updates ----------
    def update_progress(self):
        if self.is_playing and self.audio_available:
            current_time = self._audio_get_pos_seconds()
            self.bg_canvas.itemconfigure(self.current_time_text_id, text=fmt_time(current_time))

            if not self.progress_slider.dragging:
                if self.song_length and self.song_length > 0:
                    self.progress_slider.set_value(current_time, invoke=False)

        self.after(300, self.update_progress)

    def check_music_end(self):
        if self.is_playing and self.audio_available and not self._audio_is_busy():
            if self.current_folder:
                self.play_random_song_from_folder(self.current_folder)
        self.after(1000, self.check_music_end)

    # ---------- Controls ----------
    def toggle_play(self):
        if not self.current_song_path or not self.audio_available:
            return
        if self.is_playing:
            self._audio_pause()
            self.is_playing = False
            self._set_play_button_state(False)
            self.bg_canvas.itemconfigure(self.status_text_id, text="Paused")
        else:
            self._audio_unpause()
            self.is_playing = True
            self._set_play_button_state(True)
            self.bg_canvas.itemconfigure(self.status_text_id, text="Playing...")

    def next_song(self):
        if self.current_folder:
            if self.audio_available:
                self._audio_stop()
            self.play_random_song_from_folder(self.current_folder)

    def previous_song(self):
        if len(self.song_history) > 1:
            self.song_history.pop()
            prev_song = self.song_history.pop()
            self.play_specific_song(prev_song)

    # ---------- Playback ----------
    def play_specific_song(self, song_path):
        if not self.audio_available:
            return

        song_path = self._abs_path(song_path) if song_path and not os.path.isabs(song_path) else song_path
        if not song_path or not os.path.exists(song_path):
            return

        self._audio_stop()

        self.current_song_path = song_path
        self._audio_play_file(song_path, start_at=0.0)
        if not self.audio_available:
            return

        self.is_playing = True
        self._set_play_button_state(True)
        self.song_history.append(song_path)

        if MP3 is not None:
            try:
                audio = MP3(song_path)
                self.song_length = float(audio.info.length)
            except Exception:
                self.song_length = 0.0
        else:
            self.song_length = 0.0

        self.bg_canvas.itemconfigure(self.total_time_text_id, text=fmt_time(self.song_length) if self.song_length else "0:00")
        self.progress_slider.set_range(0.0, self.song_length if self.song_length > 0 else 100.0)
        self.progress_slider.set_value(0.0, invoke=False)

        song_name = os.path.splitext(os.path.basename(song_path))[0]
        self.set_title_text(song_name)
        self.bg_canvas.itemconfigure(self.status_text_id, text="Now Playing")

    def play_random_song_from_folder(self, folder):
        if not self.audio_available:
            self._pending_folder_after_audio = folder
            return

        folder = self._abs_path(folder) if folder and not os.path.isabs(folder) else folder
        if not folder or not os.path.exists(folder):
            return
        try:
            mp3_files = [f for f in os.listdir(folder) if f.lower().endswith(".mp3")]
        except Exception:
            mp3_files = []
        if not mp3_files:
            return
        chosen = random.choice(mp3_files)
        self.play_specific_song(os.path.join(folder, chosen))

    # ---------- RFID Tap logic ----------
    def handle_rfid_tap(self, uid):
        now = time.time()

        if uid not in songs:
            self.bg_canvas.itemconfigure(self.status_text_id, text=f"Unknown card: {uid}")
            return

        info = songs[uid]

        if uid != self.current_uid:
            self.current_uid = uid
            self.current_folder = self._abs_path(info["folder"]) if info.get("folder") else None
            self.tap_count = 1
            self.last_tap_time = now
            self.song_history.clear()

            self.bg_canvas.itemconfigure(self.artist_text_id, text=info.get("artist", ""))
            self.bg_canvas.itemconfigure(self.status_text_id, text=f"Loading: {info.get('title','')}")
            self.set_title_text(info.get("title", "Unknown"))
            self.set_cover(info.get("cover"))

            if self.audio_available:
                self._audio_stop()

            self.play_random_song_from_folder(self.current_folder)
            return

        if now - self.last_tap_time > self.tap_reset_seconds:
            self.tap_count = 0

        self.tap_count += 1
        self.last_tap_time = now

        if self.tap_count == 2:
            self.bg_canvas.itemconfigure(self.status_text_id, text="Skipping…")
            if self.audio_available:
                self._audio_stop()
            self.play_random_song_from_folder(self.current_folder)
            return

        if self.tap_count == 3:
            if self.is_playing:
                try:
                    if self.audio_available:
                        self._audio_pause()
                    self.is_playing = False
                    self._set_play_button_state(False)
                except Exception:
                    pass
            self.bg_canvas.itemconfigure(self.status_text_id, text="Paused")
            return

        if self.tap_count == 4:
            if not self.is_playing and self.current_song_path:
                try:
                    if self.audio_available:
                        self._audio_unpause()
                    self.is_playing = True
                    self._set_play_button_state(True)
                except Exception:
                    pass
            self.bg_canvas.itemconfigure(self.status_text_id, text="Resumed")
            return

        if self.tap_count > 4:
            self.tap_count = 1
            self.bg_canvas.itemconfigure(self.status_text_id, text="Restarting playlist…")
            if self.audio_available:
                self._audio_stop()
            self.play_random_song_from_folder(self.current_folder)

    # ---------- Serial ----------
    def read_serial(self):
        if serial is None:
            self._ui_after(0, lambda: self.bg_canvas.itemconfigure(self.serial_text_id, text="SERIAL: PYSerial missing", fill=BAD))
            self._ui_after(
                0,
                lambda: self.bg_canvas.itemconfigure(
                    self.status_text_id,
                    text="Install pyserial: python3 -m pip install pyserial (or use a venv).",
                ),
            )
            return

        port = pick_serial_port(SERIAL_PORT)
        if not port:
            self._ui_after(0, lambda: self.bg_canvas.itemconfigure(self.serial_text_id, text="SERIAL: NOT FOUND", fill=BAD))
            self._ui_after(0, lambda: self.bg_canvas.itemconfigure(self.status_text_id, text="No serial ports detected (set RFID_SERIAL_PORT)."))
            return

        try:
            ser = serial.Serial(port, BAUDRATE, timeout=1)
            time.sleep(2)
            self._ui_after(0, lambda: self.bg_canvas.itemconfigure(self.serial_text_id, text=f"SERIAL: {port}", fill=GOOD))
        except Exception as e:
            print(f"Error opening serial port {port}: {e}")
            self._ui_after(0, lambda: self.bg_canvas.itemconfigure(self.serial_text_id, text="SERIAL: ERROR", fill=BAD))
            self._ui_after(0, lambda: self.bg_canvas.itemconfigure(self.status_text_id, text="Serial unavailable (check port settings)."))
            return

        while True:
            try:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("Card UID:"):
                    uid = line.replace("Card UID:", "").strip().upper()
                    now = time.time()

                    if uid == self.last_uid_seen and (now - self.last_uid_time) < self.serial_min_interval:
                        continue

                    self.last_uid_seen = uid
                    self.last_uid_time = now
                    self._ui_after(0, lambda uid=uid: self.handle_rfid_tap(uid))
            except Exception as e:
                print("Serial reading error:", e)
                break


if __name__ == "__main__":
    try:
        os.chdir(BASE_DIR)
    except Exception:
        pass
    _missing_deps_banner_and_exit()
    if "--smoke" in sys.argv:
        app = MusicPlayerApp()
        app.update_idletasks()
        app.update()
        try:
            items = len(app.bg_canvas.find_all())
        except Exception:
            items = -1
        print(f"smoke_ok canvas_items={items}")
        app._on_close()
        raise SystemExit(0)

    app = MusicPlayerApp()
    app.mainloop()
