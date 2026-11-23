"""
desktop_app.py
==============
Quantum Traffic Router - Desktop Interface.

Architecture:
- High-DPI hardware accelerated interface built with Tkinter.
- Dynamic Slippy Map rendering with Web Mercator (EPSG:3857) projection.
- Custom vector anti-aliased UI components (rounded entry fields, pill buttons, floating HUD).
- Asynchronous worker threading for non-blocking optimization execution.
"""

import sys, os, io, math, threading, queue, ssl
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

SSL_CTX = ssl._create_unverified_context()

# Configure Windows high-DPI scaling to prevent interface blur
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from traffic_core import solve, THEME as T, APP_VERSION

# Safe fallback for converge_iter
try:
    from traffic_core import converge_iter
except ImportError:
    def converge_iter(hist):
        if not hist: return "-"
        try:
            final = hist[-1]
            threshold = final * 1.01 if final > 0 else final
            return next(i for i, c in enumerate(hist) if c <= threshold)
        except Exception:
            return len(hist)

FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS

DATA_DIR = os.path.join(os.path.expanduser("~"), "TrafficRouterData")
SLIPPY_CACHE = os.path.join(DATA_DIR, "slippy_tiles")
os.makedirs(SLIPPY_CACHE, exist_ok=True)


# ======================= VECTOR DRAWING PRIMITIVES =======================
def draw_rounded_rect(canvas, x1, y1, x2, y2, r, fill, outline="", width=1, tags=()):
    """
    Draws a smooth rounded rectangle on Tkinter Canvas using corner arcs and filling.
    Produces anti-aliased rounded corners without any boxy rectangular frames.
    """
    if isinstance(tags, str):
        tags = (tags,)
    items = []
    max_r = min((x2 - x1) / 2.0, (y2 - y1) / 2.0)
    if r > max_r: r = max_r
    d = 2 * r

    # Fill corners
    items.append(canvas.create_oval(x1, y1, x1 + d, y1 + d, fill=fill, outline="", tags=tags))
    items.append(canvas.create_oval(x2 - d, y1, x2, y1 + d, fill=fill, outline="", tags=tags))
    items.append(canvas.create_oval(x1, y2 - d, x1 + d, y2, fill=fill, outline="", tags=tags))
    items.append(canvas.create_oval(x2 - d, y2 - d, x2, y2, fill=fill, outline="", tags=tags))

    # Fill inner rectangles
    items.append(canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", tags=tags))
    items.append(canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", tags=tags))

    if outline:
        items.append(canvas.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90, style="arc", outline=outline, width=width, tags=tags))
        items.append(canvas.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90, style="arc", outline=outline, width=width, tags=tags))
        items.append(canvas.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90, style="arc", outline=outline, width=width, tags=tags))
        items.append(canvas.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90, style="arc", outline=outline, width=width, tags=tags))
        items.append(canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width, tags=tags))
        items.append(canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width, tags=tags))
        items.append(canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width, tags=tags))
        items.append(canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width, tags=tags))
    return items

def draw_pill(canvas, x1, y1, x2, y2, fill, outline="", width=1, tags=()):
    """Draws a pill capsule where radius = height / 2."""
    h = y2 - y1
    r = h / 2.0
    return draw_rounded_rect(canvas, x1, y1, x2, y2, r, fill=fill, outline=outline, width=width, tags=tags)


# ======================= CUSTOM ROUNDED ENTRY WIDGET =======================
class RoundedEntry(tk.Canvas):
    """
    Custom canvas-rendered text input with anti-aliased rounded corners,
    dynamic focus border highlighting, and live place search autocomplete dropdown.
    """
    def __init__(self, parent, textvariable, height=42, r=12,
                 bg="#101013", fill="#18181b", border="#27272a", focus_border="#007aff",
                 font=(FONT, 10), enable_autocomplete=False, get_proximity=None, on_select=None, **kwargs):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, **kwargs)
        self.textvariable = textvariable
        self.h = height
        self.r = r
        self.fill_color = fill
        self.border_color = border
        self.focus_border = focus_border
        self.is_focused = False
        self.font = font
        self.enable_autocomplete = enable_autocomplete
        self.get_proximity = get_proximity
        self.on_select = on_select

        self.popup = None
        self.suggestions = []
        self.selected_idx = -1
        self._search_timer = None
        self._search_seq = 0
        self.item_widgets = []

        self.entry = tk.Entry(self, textvariable=textvariable, font=font,
                              bg=fill, fg="#ffffff", insertbackground="#007aff",
                              relief="flat", highlightthickness=0)
        self.entry_window = self.create_window(r + 8, height // 2, window=self.entry, anchor="w")

        self.entry.bind("<FocusIn>", self.on_focus_in)
        self.entry.bind("<FocusOut>", self.on_focus_out)
        self.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.bind("<Configure>", lambda e: self.draw())

        if self.enable_autocomplete:
            self.entry.bind("<KeyRelease>", self.on_key_release)
            self.entry.bind("<Down>", self.on_arrow_down)
            self.entry.bind("<Up>", self.on_arrow_up)
            self.entry.bind("<Return>", self.on_enter)
            self.entry.bind("<Escape>", lambda e: self.hide_popup())

    def on_focus_in(self, e):
        self.is_focused = True
        self.draw()

    def on_focus_out(self, e):
        self.is_focused = False
        self.draw()
        self.after(250, self.hide_popup)

    def draw(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20 or h < 20: return
        self.delete("bg_shape")
        border = self.focus_border if self.is_focused else self.border_color
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r=self.r,
                          fill=self.fill_color, outline=border, width=1.5, tags="bg_shape")
        self.tag_lower("bg_shape")
        self.itemconfigure(self.entry_window, width=max(10, w - 2 * (self.r + 8)))

    def on_key_release(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        text = self.textvariable.get().strip()
        if len(text) < 2:
            self.hide_popup()
            return
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
        if len(parts) == 2 and all(p.replace(".", "").replace("-", "").isdigit() for p in parts):
            self.hide_popup()
            return

        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(260, lambda: self._start_search(text))

    def _start_search(self, query):
        self._search_seq += 1
        seq = self._search_seq
        prox = self.get_proximity() if self.get_proximity else None
        def worker():
            try:
                from traffic_core import search_places
                res = search_places(query, limit=5, proximity=prox)
                if seq == self._search_seq:
                    self.after(0, lambda: self._show_suggestions(res))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _show_suggestions(self, results):
        if not results or not self.is_focused:
            self.hide_popup()
            return

        self.suggestions = results
        self.selected_idx = -1

        try:
            rx = self.winfo_rootx()
            ry = self.winfo_rooty() + self.winfo_height() + 2
            rw = max(310, self.winfo_width())
        except Exception:
            return

        if not self.popup or not self.popup.winfo_exists():
            self.popup = tk.Toplevel(self)
            self.popup.overrideredirect(True)
            self.popup.attributes("-topmost", True)
            self.popup.configure(bg="#27272a")

        for child in self.popup.winfo_children():
            child.destroy()

        container = tk.Frame(self.popup, bg="#18181b")
        container.pack(fill="both", expand=True, padx=1, pady=1)

        self.item_widgets = []
        for i, item in enumerate(results):
            row = tk.Frame(container, bg="#18181b", cursor="hand2")
            row.pack(fill="x", pady=1, padx=2)

            pin = tk.Label(row, text="📍", font=(FONT, 9), bg="#18181b", fg="#007aff")
            pin.pack(side="left", padx=(6, 4), pady=4)

            tf = tk.Frame(row, bg="#18181b")
            tf.pack(side="left", fill="x", expand=True, pady=3)

            nl = tk.Label(tf, text=item["name"], font=(FONT, 9, "bold"),
                          fg="#ffffff", bg="#18181b", anchor="w")
            nl.pack(fill="x")

            dl = tk.Label(tf, text=item["desc"], font=(FONT, 8),
                          fg="#a1a1aa", bg="#18181b", anchor="w")
            dl.pack(fill="x")

            def on_enter_h(e, r=row, t=tf, n=nl, d=dl, p=pin):
                for w in (r, t, n, d, p): w.configure(bg="#27272a")

            def on_leave_h(e, r=row, t=tf, n=nl, d=dl, p=pin):
                for w in (r, t, n, d, p): w.configure(bg="#18181b")

            def on_click_item(e, it=item):
                self._select_item(it)

            for w in (row, pin, tf, nl, dl):
                w.bind("<Enter>", on_enter_h)
                w.bind("<Leave>", on_leave_h)
                w.bind("<Button-1>", on_click_item)

            self.item_widgets.append((row, tf, nl, dl, pin))

        self.popup.update_idletasks()
        ph = container.winfo_reqheight() + 2
        self.popup.geometry(f"{rw}x{ph}+{rx}+{ry}")
        self.popup.deiconify()

    def _select_item(self, item):
        self.hide_popup()
        coord_text = f"{item['lat']:.6f}, {item['lon']:.6f}"
        self.textvariable.set(coord_text)
        if self.on_select:
            self.on_select(item["lat"], item["lon"], item["name"])

    def on_arrow_down(self, event):
        if not self.popup or not self.popup.winfo_exists() or not self.suggestions:
            return
        self.selected_idx = min(len(self.suggestions) - 1, self.selected_idx + 1)
        self._highlight_selected()
        return "break"

    def on_arrow_up(self, event):
        if not self.popup or not self.popup.winfo_exists() or not self.suggestions:
            return
        self.selected_idx = max(0, self.selected_idx - 1)
        self._highlight_selected()
        return "break"

    def _highlight_selected(self):
        for i, (r, tf, nl, dl, pl) in enumerate(self.item_widgets):
            bg_col = "#27272a" if i == self.selected_idx else "#18181b"
            for w in (r, tf, nl, dl, pl):
                w.configure(bg=bg_col)

    def on_enter(self, event):
        if self.popup and self.popup.winfo_exists() and self.suggestions and self.selected_idx >= 0:
            self._select_item(self.suggestions[self.selected_idx])
            return "break"
        self.hide_popup()

    def hide_popup(self):
        if self.popup and self.popup.winfo_exists():
            self.popup.destroy()
            self.popup = None
        self.suggestions = []
        self.selected_idx = -1


# ======================= CUSTOM ROUNDED BUTTON WIDGET =======================
class RoundedButton(tk.Canvas):
    """
    Custom interactive button featuring anti-aliased pill geometry,
    cursor transitions, and visual hover/press feedback states.
    """
    def __init__(self, parent, text, command=None, height=44, r=14,
                 bg="#101013", fill="#007aff", hover_fill="#0062cc",
                 fg="#ffffff", font=(FONT, 10, "bold"), **kwargs):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0,
                         cursor="hand2", **kwargs)
        self.text = text
        self.command = command
        self.h = height
        self.r = r
        self.base_fill = fill
        self.hover_fill = hover_fill
        self.current_fill = fill
        self.fg = fg
        self.font = font
        self.state = "normal"

        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Configure>", lambda e: self.draw())

    def config(self, **kwargs):
        if "state" in kwargs:
            self.set_state(kwargs["state"])

    def set_state(self, state):
        self.state = state
        if state == "disabled":
            self.current_fill = "#18181b"
            self.config_cursor("")
        else:
            self.current_fill = self.base_fill
            self.config_cursor("hand2")
        self.draw()

    def config_cursor(self, c):
        try: self.config(cursor=c)
        except Exception: pass

    def on_enter(self, e):
        if self.state == "normal":
            self.current_fill = self.hover_fill
            self.draw()

    def on_leave(self, e):
        if self.state == "normal":
            self.current_fill = self.base_fill
            self.draw()

    def on_click(self, e):
        if self.state == "normal" and self.command:
            self.command()

    def draw(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20 or h < 20: return
        self.delete("all")
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r=self.r,
                          fill=self.current_fill, outline="")
        txt_color = self.fg if self.state == "normal" else "#71717a"
        self.create_text(w / 2, h / 2, text=self.text,
                         fill=txt_color, font=self.font)


# ======================= CUSTOM METRIC KPI CARD =======================
class RoundedCard(tk.Canvas):
    """
    Canvas-rendered dashboard card displaying primary performance metrics,
    formatted labels, and descriptive status subtext.
    """
    def __init__(self, parent, title, accent_color, height=88, r=12,
                 bg="#09090b", card_fill="#121215", border="#27272a", **kwargs):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, **kwargs)
        self.title = title
        self.accent_color = accent_color
        self.r = r
        self.card_fill = card_fill
        self.border = border
        self.val_text = "-"
        self.sub_text = "Click RUN to evaluate"
        self.bind("<Configure>", lambda e: self.draw())

    def set_data(self, val, sub):
        self.val_text = val
        self.sub_text = sub
        self.draw()

    def draw(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20 or h < 20: return
        self.delete("all")
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r=self.r,
                          fill=self.card_fill, outline=self.border, width=1)
        self.create_text(16, 20, text=self.title, fill="#a1a1aa",
                         font=(FONT, 8, "bold"), anchor="w")
        self.create_text(16, 46, text=self.val_text, fill=self.accent_color,
                         font=(FONT, 18, "bold"), anchor="w")
        self.create_text(16, 68, text=self.sub_text, fill="#71717a",
                         font=(FONT, 8), anchor="w")


# ======================= INTERACTIVE SLIPPY MAP WIDGET =======================
class SlippyMapWidget(tk.Frame):
    """
    Embedded Slippy Map Widget using Web Mercator (EPSG:3857) projection.
    - Multi-level dynamic zoom with asynchronous background tile retrieval.
    - Satellite imagery and cartographic street tile rendering.
    - Vector road corridor overlay matching physical road curvature.
    - Floating on-canvas HUD controls with zero-overflow information badges.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=T["bg"], **kwargs)
        self.canvas = tk.Canvas(self, bg="#09090b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.zoom = 14
        self.center_lat = 31.625
        self.center_lon = 74.874
        self.layer = "satellite" # "satellite" or "street"

        self.routes_data = []
        self.start_pt = (31.6200, 74.8765)
        self.end_pt = (31.6340, 74.8723)
        self.active_mode = "combined" # "selfish", "combined", or route index (0, 1, 2, 3)

        self.tile_mem_cache = {}
        self.download_queue = set()
        self.pool = ThreadPoolExecutor(max_workers=6)
        self.drag_start = None

        # Bindings for mouse pan, zoom, click on HUD, and hover
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_release)
        self.canvas.bind("<Motion>", self.on_canvas_hover)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

    def set_layer(self, layer_type):
        self.layer = layer_type
        self.redraw()

    def toggle_layer(self):
        self.layer = "street" if self.layer == "satellite" else "satellite"
        self.redraw()

    def set_mode(self, mode):
        self.active_mode = mode
        self.redraw()

    def zoom_in(self):
        if self.zoom < 18:
            self.zoom += 1
            self.redraw()

    def zoom_out(self):
        if self.zoom > 11:
            self.zoom -= 1
            self.redraw()

    def on_mouse_wheel(self, event):
        if event.delta > 0: self.zoom_in()
        else: self.zoom_out()

    def on_canvas_click(self, event):
        items = self.canvas.find_overlapping(event.x - 1, event.y - 1, event.x + 1, event.y + 1)
        for item in items:
            tags = self.canvas.gettags(item)
            if "toggle_layer" in tags:
                self.toggle_layer()
                return
            elif "zoom_in" in tags:
                self.zoom_in()
                return
            elif "zoom_out" in tags:
                self.zoom_out()
                return
            elif "mode_selfish" in tags:
                self.set_mode("selfish")
                return
            elif "mode_combined" in tags:
                self.set_mode("combined")
                return
            elif any(t.startswith("mode_route_") for t in tags):
                tag = next(t for t in tags if t.startswith("mode_route_"))
                idx = int(tag.split("_")[-1])
                self.set_mode(idx)
                return

        self.drag_start = (event.x, event.y)

    def on_canvas_hover(self, event):
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        is_interactive = any("hud_interactive" in self.canvas.gettags(item) for item in items)
        self.canvas.config(cursor="hand2" if is_interactive else "")

    def on_drag_motion(self, event):
        if not self.drag_start: return
        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        self.drag_start = (event.x, event.y)

        n = 2.0 ** self.zoom
        d_lon = - (dx / (n * 256.0)) * 360.0
        self.center_lon += d_lon
        lat_rad = math.radians(self.center_lat)
        curr_y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * 256.0
        new_y = curr_y - dy
        new_lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * new_y / (n * 256.0))))
        self.center_lat = math.degrees(new_lat_rad)
        self.redraw()

    def on_drag_release(self, event):
        self.drag_start = None

    def load_trip_data(self, routes_data, start_pt, end_pt):
        self.routes_data = routes_data
        self.start_pt = start_pt
        self.end_pt = end_pt
        self.active_mode = "combined"

        self.center_lat = (start_pt[0] + end_pt[0]) / 2.0
        self.center_lon = (start_pt[1] + end_pt[1]) / 2.0

        span = max(abs(start_pt[0] - end_pt[0]) * 1.3, abs(start_pt[1] - end_pt[1]))
        self.zoom = max(12, min(16, int(round(math.log2(360.0 / max(0.005, span)))) - 2))
        self.redraw()

    def geo_to_pixel(self, lat, lon):
        lat_rad = math.radians(lat)
        n = 2.0 ** self.zoom
        x = (lon + 180.0) / 360.0 * n * 256.0
        y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * 256.0
        return x, y

    def fetch_tile_async(self, zoom, x, y, layer):
        key = (layer, zoom, x, y)
        if key in self.download_queue: return
        self.download_queue.add(key)

        def worker():
            cache_file = os.path.join(SLIPPY_CACHE, f"{layer}_{zoom}_{x}_{y}.png")
            if not os.path.exists(cache_file):
                if layer == "satellite":
                    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
                else:
                    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
                headers = {"User-Agent": "QuantumTrafficRouter/10.0 (Windows NT 10.0; High-DPI)"}
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5, context=SSL_CTX) as resp:
                        content = resp.read()
                        with open(cache_file, "wb") as f: f.write(content)
                except Exception:
                    self.download_queue.discard(key)
                    return
            self.after(0, lambda: self.on_tile_ready(key, cache_file))

        self.pool.submit(worker)

    def on_tile_ready(self, key, cache_file):
        self.download_queue.discard(key)
        try:
            if os.path.exists(cache_file):
                img = Image.open(cache_file).convert("RGB")
                self.tile_mem_cache[key] = ImageTk.PhotoImage(img)
                self.redraw()
        except Exception:
            pass

    def mask_corners(self, w, h, r=16):
        """
        Masks the 4 corners of the map canvas with the window background color,
        giving the slippy map smooth anti-aliased rounded corners.
        """
        bg_col = T["bg"]

        # Top-Left Corner
        pts_tl = [0, 0, r, 0]
        for s in range(9):
            ang = (math.pi / 2) * (s / 8.0)
            pts_tl.extend([r - r * math.sin(ang), r - r * math.cos(ang)])
        pts_tl.extend([0, r, 0, 0])
        self.canvas.create_polygon(pts_tl, fill=bg_col, outline=bg_col)

        # Top-Right Corner
        pts_tr = [w, 0, w - r, 0]
        for s in range(9):
            ang = (math.pi / 2) * (s / 8.0)
            pts_tr.extend([w - r + r * math.sin(ang), r - r * math.cos(ang)])
        pts_tr.extend([w, r, w, 0])
        self.canvas.create_polygon(pts_tr, fill=bg_col, outline=bg_col)

        # Bottom-Left Corner
        pts_bl = [0, h, 0, h - r]
        for s in range(9):
            ang = (math.pi / 2) * (s / 8.0)
            pts_bl.extend([r - r * math.cos(ang), h - r + r * math.sin(ang)])
        pts_bl.extend([r, h, 0, h])
        self.canvas.create_polygon(pts_bl, fill=bg_col, outline=bg_col)

        # Bottom-Right Corner
        pts_br = [w, h, w, h - r]
        for s in range(9):
            ang = (math.pi / 2) * (s / 8.0)
            pts_br.extend([w - r + r * math.cos(ang), h - r + r * math.sin(ang)])
        pts_br.extend([w - r, h, w, h])
        self.canvas.create_polygon(pts_br, fill=bg_col, outline=bg_col)

        # Sleek rounded border outline around entire map
        draw_rounded_rect(self.canvas, 1, 1, w - 1, h - 1, r=r, fill="",
                          outline="#27272a", width=1.5)

    def offset_polyline(self, pts, shift_px):
        """
        Applies a perpendicular pixel offset to a polyline in screen space.
        Enables multi-corridor display where alternative routes share highway sections,
        ensuring all routes are simultaneously visible side-by-side.
        """
        if abs(shift_px) < 0.1 or len(pts) < 2:
            return pts
        new_pts = []
        for j in range(len(pts)):
            p = pts[j]
            if j == 0:
                p_next = pts[j + 1]
                dx, dy = p_next[0] - p[0], p_next[1] - p[1]
            elif j == len(pts) - 1:
                p_prev = pts[j - 1]
                dx, dy = p[0] - p_prev[0], p[1] - p_prev[1]
            else:
                dx = pts[j + 1][0] - pts[j - 1][0]
                dy = pts[j + 1][1] - pts[j - 1][1]
            dist = math.hypot(dx, dy) or 1e-6
            nx = -dy / dist
            ny = dx / dist
            new_pts.append((p[0] + nx * shift_px, p[1] + ny * shift_px))
        return new_pts

    def redraw(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 50 or h < 50: return

        self.canvas.delete("all")
        cx, cy = w / 2.0, h / 2.0
        center_x, center_y = self.geo_to_pixel(self.center_lat, self.center_lon)

        self.canvas.config(bg="#09090b")

        # ---------------- 1. Render Slippy Tiles (4K Resolution) ----------------
        n = 2.0 ** self.zoom
        tile_x_min = int((center_x - cx) / 256.0)
        tile_x_max = int((center_x + cx) / 256.0) + 1
        tile_y_min = int((center_y - cy) / 256.0)
        tile_y_max = int((center_y + cy) / 256.0) + 1

        for tx in range(tile_x_min, tile_x_max + 1):
            for ty in range(tile_y_min, tile_y_max + 1):
                if tx < 0 or tx >= n or ty < 0 or ty >= n: continue
                key = (self.layer, self.zoom, tx, ty)
                px = cx + (tx * 256.0 - center_x)
                py = cy + (ty * 256.0 - center_y)

                if key in self.tile_mem_cache:
                    self.canvas.create_image(px, py, anchor="nw", image=self.tile_mem_cache[key])
                else:
                    cache_file = os.path.join(SLIPPY_CACHE, f"{self.layer}_{self.zoom}_{tx}_{ty}.png")
                    if os.path.exists(cache_file):
                        try:
                            img = Image.open(cache_file).convert("RGB")
                            self.tile_mem_cache[key] = ImageTk.PhotoImage(img)
                            self.canvas.create_image(px, py, anchor="nw", image=self.tile_mem_cache[key])
                            continue
                        except Exception: pass
                    self.canvas.create_rectangle(px, py, px+256, py+256, fill="#121215", outline="#1c1c20")
                    self.fetch_tile_async(self.zoom, tx, ty, self.layer)

        # ---------------- 2. Render Curves Following True Road Geometry ----------------
        route_colors = ["#007aff", "#34c759", "#ff9500", "#af52de", "#5856d6", "#ff2d55", "#32ade6", "#ffd60a"]
        n_vis = len(self.routes_data)
        is_multi = (self.active_mode == "combined" and n_vis > 1)

        for i, r in enumerate(self.routes_data):
            if self.active_mode == "selfish" and i != 0: continue
            if isinstance(self.active_mode, int) and self.active_mode != i: continue

            pts = r["pts"]
            if len(pts) < 2: continue

            base_pts = []
            for lon, lat in pts:
                gx, gy = self.geo_to_pixel(lat, lon)
                base_pts.append((cx + (gx - center_x), cy + (gy - center_y)))

            # If showing multiple routes, apply lateral pixel offset so shared highway segments show both routes side-by-side
            if is_multi:
                shift_px = (i - (n_vis - 1) / 2.0) * 3.5
                rendered_pts = self.offset_polyline(base_pts, shift_px)
            else:
                rendered_pts = base_pts

            coords = []
            for px, py in rendered_pts:
                coords.extend([px, py])

            color = "#ff3b30" if self.active_mode == "selfish" else route_colors[i % len(route_colors)]
            lw = 7 if (self.active_mode == "selfish" or self.active_mode == i) else 5

            # Contrast outline halo for clear visibility over satellite and street map
            self.canvas.create_line(*coords, fill="#000000", width=lw+4, capstyle="round", joinstyle="round")
            # Distinct corridor vector line
            self.canvas.create_line(*coords, fill=color, width=lw, capstyle="round", joinstyle="round")

        # ---------------- 3. Render Origin & Destination Pins ----------------
        for pt, col, label in [(self.start_pt, "#34c759", "START"), (self.end_pt, "#ff3b30", "END")]:
            if not pt: continue
            gx, gy = self.geo_to_pixel(pt[0], pt[1])
            px, py = cx + (gx - center_x), cy + (gy - center_y)

            self.canvas.create_oval(px-9, py-9, px+9, py+9, fill="#000000", outline="#ffffff", width=2)
            self.canvas.create_oval(px-7, py-7, px+7, py+7, fill=col, outline="")
            self.canvas.create_text(px, py-18, text=label, fill="#ffffff", font=(FONT, 8, "bold"))

        # ---------------- 4. Mask Map Canvas to Smooth Rounded Corners ----------------
        self.mask_corners(w, h, r=16)

        # ---------------- 5. Render Floating On-Canvas HUD Controls ----------------
        self.render_hud(w, h)

    def render_hud(self, w, h):
        """
        Renders anti-aliased floating vector HUD controls directly onto the canvas.
        Includes dynamic corridor selector, layer toggle, status badge, and zoom buttons.
        """
        # ================= A. TOP-LEFT CORRIDOR SELECTOR HUD =================
        n_routes = len(self.routes_data) if self.routes_data else 2
        palette = ["#007aff", "#34c759", "#ff9500", "#af52de", "#5856d6", "#ff2d55", "#32ade6", "#ffd60a"]
        mode_items = [
            ("selfish", "Selfish", "#ff3b30"),
            ("combined", f"QPSO ({n_routes} Routes)", "#007aff")
        ]
        for i in range(n_routes):
            mode_items.append((i, f"Route {i + 1}", palette[i % len(palette)]))

        bar_x = 20
        bar_y = 20
        bar_h = 36

        btn_widths = []
        for m_id, title, _ in mode_items:
            tw = max(50, len(title) * 7 + 20)
            btn_widths.append(tw)

        total_w = sum(btn_widths) + (len(mode_items) - 1) * 6 + 16
        draw_pill(self.canvas, bar_x, bar_y, bar_x + total_w, bar_y + bar_h,
                  fill="#121215", outline="#27272a", width=1)

        cur_x = bar_x + 8
        for (m_id, title, active_color), bw in zip(mode_items, btn_widths):
            is_active = (self.active_mode == m_id)
            bx1 = cur_x
            by1 = bar_y + 4
            bx2 = cur_x + bw
            by2 = bar_y + bar_h - 4
            tag_name = f"mode_{m_id}" if isinstance(m_id, str) else f"mode_route_{m_id}"

            if is_active:
                draw_pill(self.canvas, bx1, by1, bx2, by2, fill=active_color, outline="",
                          tags=("hud_interactive", tag_name))
                self.canvas.create_text((bx1 + bx2)/2, (by1 + by2)/2, text=title,
                                        fill="#ffffff", font=(FONT, 8, "bold"),
                                        tags=("hud_interactive", tag_name))
            else:
                self.canvas.create_text((bx1 + bx2)/2, (by1 + by2)/2, text=title,
                                        fill="#a1a1aa", font=(FONT, 8, "bold"),
                                        tags=("hud_interactive", tag_name))
            cur_x += bw + 6

        # ================= B. TOP-RIGHT MAP LAYER TOGGLE SWITCH =================
        sw_bar_w = 200
        sw_bar_h = 36
        sw_x2 = w - 20
        sw_x1 = sw_x2 - sw_bar_w
        sw_y1 = 20
        sw_y2 = sw_y1 + sw_bar_h

        draw_pill(self.canvas, sw_x1, sw_y1, sw_x2, sw_y2, fill="#121215", outline="#27272a", width=1,
                  tags=("hud_interactive", "toggle_layer"))

        is_sat = (self.layer == "satellite")
        lbl_text = "🛰️ SATELLITE" if is_sat else "🗺️ STREET MAP"
        lbl_color = "#34c759" if is_sat else "#a1a1aa"
        self.canvas.create_text(sw_x1 + 60, (sw_y1 + sw_y2)/2, text=lbl_text,
                                fill=lbl_color, font=(FONT, 8, "bold"),
                                tags=("hud_interactive", "toggle_layer"))

        pill_w = 46
        pill_h = 24
        px1 = sw_x2 - pill_w - 8
        py1 = sw_y1 + 6
        px2 = sw_x2 - 8
        py2 = sw_y1 + 6 + pill_h

        switch_fill = "#34c759" if is_sat else "#27272a"
        draw_pill(self.canvas, px1, py1, px2, py2, fill=switch_fill, outline="",
                  tags=("hud_interactive", "toggle_layer"))

        knob_r = 9
        kx = (px2 - knob_r - 3) if is_sat else (px1 + knob_r + 3)
        ky = (py1 + py2) / 2
        self.canvas.create_oval(kx - knob_r, ky - knob_r + 1, kx + knob_r, ky + knob_r + 2,
                                fill="#000000", outline="", tags=("hud_interactive", "toggle_layer"))
        self.canvas.create_oval(kx - knob_r, ky - knob_r, kx + knob_r, ky + knob_r,
                                fill="#ffffff", outline="#e4e4e7", tags=("hud_interactive", "toggle_layer"))

        # ================= C. BOTTOM-LEFT CORRIDOR STATUS HUD =================
        card_w = 340
        card_h = 76
        cx1 = 20
        cy2 = h - 20
        cy1 = cy2 - card_h
        cx2 = cx1 + card_w

        draw_rounded_rect(self.canvas, cx1, cy1, cx2, cy2, r=14, fill="#121215", outline="#27272a", width=1)

        layer_desc = "Satellite" if self.layer == "satellite" else "Street Map"

        if self.active_mode == "selfish":
            title = "⚠️ SELFISH ROUTING"
            t_col = "#ff3b30"
            line1 = "100% Traffic on shortest path."
            line2 = f"Zoom: {self.zoom}x  •  Bottleneck gridlock"
        elif self.active_mode == "combined":
            title = f"✨ QPSO EQUILIBRIUM ({n_routes} CORRIDORS)"
            t_col = "#34c759"
            line1 = f"Traffic solved across {n_routes} corridors."
            line2 = f"Zoom: {self.zoom}x  •  Zero bottleneck gridlock"
        elif isinstance(self.active_mode, int) and self.active_mode < len(self.routes_data):
            r = self.routes_data[self.active_mode]
            colors = ["#007aff", "#34c759", "#ff9500", "#af52de", "#5856d6", "#ff2d55", "#32ade6", "#ffd60a"]
            t_col = colors[self.active_mode % len(colors)]
            title = f"CORRIDOR {self.active_mode + 1}: {r['name'].upper()}"
            line1 = f"{r.get('cars', 0)} cars  •  Cap: {r.get('capacity', 0)}/hr  •  {r.get('km', 0):.2f} km"
            line2 = f"Zoom: {self.zoom}x  •  {r.get('road_type', 'Arterial')}"
        else:
            title = "INTERACTIVE MAP"
            t_col = "#007aff"
            line1 = "Mouse wheel to zoom, drag to pan."
            line2 = f"Zoom: {self.zoom}x  •  {layer_desc}"

        # Specified width prevents any text from overflowing out of the block
        self.canvas.create_text(cx1 + 16, cy1 + 18, text=title, fill=t_col,
                                font=(FONT, 9, "bold"), anchor="w", width=card_w - 32)
        self.canvas.create_text(cx1 + 16, cy1 + 38, text=line1, fill="#ffffff",
                                font=(FONT, 8), anchor="w", width=card_w - 32)
        self.canvas.create_text(cx1 + 16, cy1 + 56, text=line2, fill="#71717a",
                                font=(FONT, 8), anchor="w", width=card_w - 32)

        # ================= D. BOTTOM-RIGHT CIRCULAR ZOOM BUTTONS =================
        zx = w - 38
        zy_in = h - 70
        zy_out = h - 30
        zr = 17

        self.canvas.create_oval(zx - zr, zy_in - zr, zx + zr, zy_in + zr,
                                fill="#121215", outline="#27272a", width=1,
                                tags=("hud_interactive", "zoom_in"))
        self.canvas.create_text(zx, zy_in, text="＋", fill="#ffffff",
                                font=(FONT, 12, "bold"), tags=("hud_interactive", "zoom_in"))

        self.canvas.create_oval(zx - zr, zy_out - zr, zx + zr, zy_out + zr,
                                fill="#121215", outline="#27272a", width=1,
                                tags=("hud_interactive", "zoom_out"))
        self.canvas.create_text(zx, zy_out - 1, text="－", fill="#ffffff",
                                font=(FONT, 12, "bold"), tags=("hud_interactive", "zoom_out"))


# ======================= SEGMENTED TAB CONTROL =======================
class IOSSegmentedBar(tk.Frame):
    """
    Pill-shaped segmented tab control managing active dashboard views.
    """
    def __init__(self, parent, tabs, on_tab_change, **kwargs):
        super().__init__(parent, bg="#121215", padx=3, pady=3,
                         highlightbackground="#27272a", highlightthickness=1, **kwargs)
        self.tabs = tabs
        self.on_tab_change = on_tab_change
        self.current_idx = 0
        self.buttons = []

        for i, title in enumerate(tabs):
            btn = tk.Button(
                self, text=title, font=(FONT, 9, "bold"),
                bg="#007aff" if i == 0 else "#121215",
                fg="#ffffff" if i == 0 else "#a1a1aa",
                activebackground="#0062cc", activeforeground="#ffffff",
                relief="flat", cursor="hand2", padx=16, pady=6,
                command=lambda idx=i: self.select(idx)
            )
            btn.pack(side="left", padx=2)
            self.buttons.append(btn)

    def select(self, idx):
        self.current_idx = idx
        for i, b in enumerate(self.buttons):
            if i == idx:
                b.config(bg="#007aff", fg="#ffffff")
            else:
                b.config(bg="#121215", fg="#a1a1aa")
        if self.on_tab_change:
            self.on_tab_change(idx)


# ======================= MAIN WINDOW APPLICATION =======================
class TrafficRouterApp:
    def __init__(self, root):
        self.root = root
        root.title("Quantum Traffic Router")

        # Set application window icon if present
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        for loc in [base_dir, os.path.dirname(os.path.abspath(__file__)), os.getcwd()]:
            icon_candidate = os.path.join(loc, "logo.ico")
            if not os.path.exists(icon_candidate):
                icon_candidate = os.path.join(loc, "logo_q_B_flow.ico")
            if os.path.exists(icon_candidate):
                try:
                    root.iconbitmap(icon_candidate)
                    break
                except Exception:
                    pass

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(1440, sw - 80)}x{min(880, sh - 120)}")
        root.configure(bg=T["bg"])

        self.q = queue.Queue()
        self.running = False
        self.conv_pil = None

        self.setup_style()
        self.build_header()

        body = tk.Frame(root, bg=T["bg"])
        body.pack(fill="both", expand=True)
        self.build_input_panel(body)
        self.build_tabs(body)

        self.poll_queue()

    def setup_style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TProgressbar", troughcolor="#18181b", background="#007aff", thickness=4)
        st.configure("Treeview", background="#121215", fieldbackground="#121215", foreground="#f4f4f5", rowheight=30)
        st.configure("Treeview.Heading", background="#18181b", foreground="#a1a1aa", font=(FONT, 9, "bold"))
        st.configure("Dark.TCombobox",
                     fieldbackground="#18181b", background="#27272a",
                     foreground="#ffffff", bordercolor="#27272a",
                     arrowcolor="#007aff", darkcolor="#18181b", lightcolor="#18181b",
                     padding=4)
        st.map("Dark.TCombobox",
               fieldbackground=[("readonly", "#18181b")],
               foreground=[("readonly", "#ffffff")],
               selectbackground=[("readonly", "#27272a")],
               selectforeground=[("readonly", "#ffffff")])
        self.root.option_add("*TCombobox*Listbox.background", "#18181b")
        self.root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#007aff")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def build_header(self):
        head = tk.Frame(self.root, bg="#101013", padx=24, pady=14,
                        highlightbackground="#1f1f23", highlightthickness=1)
        head.pack(fill="x")

        # Application navigation header
        tk.Label(head, text="Quantum Traffic Router", font=(FONT, 13, "bold"),
                 fg="#ffffff", bg="#101013").pack(side="left")

    def build_input_panel(self, parent):
        left = tk.Frame(parent, bg="#101013", padx=20, pady=16,
                        highlightbackground="#1f1f23", highlightthickness=1)
        left.pack(side="left", fill="y")

        # Sidebar title
        tk.Label(left, text="TRIP CORRIDORS", font=(FONT, 9, "bold"),
                 fg="#ffffff", bg="#101013").pack(anchor="w", pady=(0, 12), padx=4)

        self.start = tk.StringVar(value="31.6200, 74.8765")
        self.end = tk.StringVar(value="31.6340, 74.8723")

        # Origin and destination input fields with live place autocomplete
        tk.Label(left, text="ORIGIN", font=(FONT, 8, "bold"),
                 fg="#a1a1aa", bg="#101013").pack(anchor="w", padx=4, pady=(8, 4))
        self.entry_origin = RoundedEntry(
            left, textvariable=self.start, height=42, r=12,
            bg="#101013", fill="#18181b", border="#27272a",
            focus_border="#007aff", font=(FONT, 10),
            enable_autocomplete=True,
            get_proximity=lambda: (self.slippy_map.center_lat, self.slippy_map.center_lon) if hasattr(self, 'slippy_map') else None,
            on_select=self.on_origin_selected
        )
        self.entry_origin.pack(fill="x", pady=(0, 6))

        tk.Label(left, text="DESTINATION", font=(FONT, 8, "bold"),
                 fg="#a1a1aa", bg="#101013").pack(anchor="w", padx=4, pady=(8, 4))
        self.entry_dest = RoundedEntry(
            left, textvariable=self.end, height=42, r=12,
            bg="#101013", fill="#18181b", border="#27272a",
            focus_border="#007aff", font=(FONT, 10),
            enable_autocomplete=True,
            get_proximity=self.get_dest_proximity,
            on_select=self.on_dest_selected
        )
        self.entry_dest.pack(fill="x", pady=(0, 6))

        self.demo = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(left, text="Offline demo city mode", variable=self.demo,
                             font=(FONT, 8), bg="#101013", fg="#a1a1aa", selectcolor="#18181b",
                             activebackground="#101013", activeforeground="#ffffff", relief="flat")
        chk.pack(anchor="w", pady=(8, 14), padx=2)

        # Primary optimization action button
        self.run_btn = RoundedButton(
            left, text="⚡  RUN OPTIMIZATION", command=self.on_run,
            height=46, r=14, bg="#101013", fill="#007aff", hover_fill="#0062cc"
        )
        self.run_btn.pack(fill="x", pady=(4, 10))

        self.bar = ttk.Progressbar(left, style="TProgressbar", mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=(8, 6))

        self.status = tk.StringVar(value="Ready. Enter coordinates & click Run.")
        status_lbl = tk.Label(left, textvariable=self.status, wraplength=280, font=(FONT, 8),
                              fg="#71717a", bg="#101013", justify="left")
        status_lbl.pack(anchor="w", padx=2)

    def build_tabs(self, parent):
        right_area = tk.Frame(parent, bg=T["bg"])
        right_area.pack(side="right", fill="both", expand=True, padx=(14, 14), pady=(10, 14))

        # Dashboard tab navigation bar
        tab_titles = ["  📊  Analytics & Results  ", "  📈  Convergence Dynamics  ", "  🗺️  Interactive Slippy Map  "]
        self.segmented_bar = IOSSegmentedBar(right_area, tab_titles, self.on_tab_change)
        self.segmented_bar.pack(anchor="w", pady=(0, 10))

        # Container for tab pages
        self.tab_container = tk.Frame(right_area, bg=T["bg"])
        self.tab_container.pack(fill="both", expand=True)

        self.tab_results = tk.Frame(self.tab_container, bg=T["bg"])
        self.tab_conv = tk.Frame(self.tab_container, bg=T["bg"])
        self.tab_map = tk.Frame(self.tab_container, bg=T["bg"])
        self.tab_frames = [self.tab_results, self.tab_conv, self.tab_map]

        # Show first tab by default
        self.tab_results.pack(fill="both", expand=True)

        # ---- Tab 0: Results Dashboard (Rounded KPI Cards + Tables) ----
        kpi_row = tk.Frame(self.tab_results, bg=T["bg"])
        kpi_row.pack(fill="x", padx=4, pady=(6, 14))

        self.cards = []
        card_configs = [
            ("TIME SAVED (QPSO)", "#34c759"),
            ("REAL TRAFFIC LOAD", "#32ade6"),
            ("SELFISH DELAY", "#ff3b30"),
            ("QPSO DELAY", "#34c759")
        ]
        for title, accent_color in card_configs:
            rc = RoundedCard(kpi_row, title=title, accent_color=accent_color,
                             bg=T["bg"], card_fill="#121215", border="#27272a", r=12)
            rc.pack(side="left", fill="both", expand=True, padx=4)
            self.cards.append(rc)

        tk.Label(self.tab_results, text="ALGORITHM BENCHMARK COMPARISON", bg=T["bg"], fg="#32ade6",
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=4, pady=(10, 6))
        self.tbl_compare = self.make_table(
            self.tab_results,
            ["Algorithm", "Traffic Split (Vehicles)", "Total Travel Time", "Worst Delay", "Run Time (s)", "Converged"],
            [110, 180, 110, 100, 90, 90]
        )

        tk.Label(self.tab_results, text="REAL CORRIDOR INFRASTRUCTURE & ALLOCATION", bg=T["bg"], fg="#32ade6",
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=4, pady=(16, 6))
        self.tbl_routes = self.make_table(
            self.tab_results,
            ["Corridor", "Road Hierarchy", "Length (km)", "Real Capacity", "QPSO Vehicles"],
            [100, 120, 110, 130, 110]
        )

        # ---- Tab 1: Convergence Dynamics ----
        self.conv_box = tk.Frame(self.tab_conv, bg="#121215", highlightbackground="#27272a", highlightthickness=1)
        self.conv_box.pack(fill="both", expand=True, padx=4, pady=6)
        self.conv_label = tk.Label(self.conv_box, bg="#121215", fg="#a1a1aa",
                                   text="The convergence dynamics graph will appear here after clicking RUN.", font=(FONT, 11))
        self.conv_label.pack(fill="both", expand=True)
        self.conv_box.bind("<Configure>", lambda e: self.update_conv_image())

        # ---- Tab 2: Interactive Slippy Map ----
        self.slippy_map = SlippyMapWidget(self.tab_map)
        self.slippy_map.pack(fill="both", expand=True)

    def on_tab_change(self, idx):
        for i, f in enumerate(self.tab_frames):
            if i == idx:
                f.pack(fill="both", expand=True)
            else:
                f.pack_forget()
        if idx == 1:
            self.update_conv_image()
        elif idx == 2:
            self.slippy_map.redraw()

    def update_conv_image(self):
        if not self.conv_pil: return
        w = self.conv_box.winfo_width()
        h = self.conv_box.winfo_height()
        if w < 100 or h < 100: return
        tw, th = max(200, w - 20), max(200, h - 20)
        scale = min(tw / self.conv_pil.width, th / self.conv_pil.height, 1.0)
        nw, nh = max(10, int(self.conv_pil.width * scale)), max(10, int(self.conv_pil.height * scale))
        photo = ImageTk.PhotoImage(self.conv_pil.resize((nw, nh), RESAMPLE))
        self.conv_label.config(image=photo, text="")
        self.conv_label.image = photo

    def make_table(self, parent, columns, widths):
        frame = tk.Frame(parent, bg="#27272a", highlightthickness=1, highlightbackground="#27272a")
        frame.pack(fill="x", padx=4)
        tv = ttk.Treeview(frame, columns=columns, show="headings", height=4, selectmode="none")
        for c, w in zip(columns, widths):
            tv.heading(c, text=c, anchor="w")
            tv.column(c, width=w, minwidth=70, anchor="w", stretch=True)
        tv.pack(fill="x", padx=1, pady=1)
        return tv

    def get_dest_proximity(self):
        try:
            from traffic_core import parse_coordinates
            return parse_coordinates(self.start.get())
        except Exception:
            if hasattr(self, "slippy_map") and self.slippy_map.start_pt:
                return self.slippy_map.start_pt
            return None

    def on_origin_selected(self, lat, lon, name):
        if hasattr(self, "slippy_map"):
            self.slippy_map.start_pt = (lat, lon)
            self.slippy_map.center_lat = lat
            self.slippy_map.center_lon = lon
            self.slippy_map.redraw()

    def on_dest_selected(self, lat, lon, name):
        if hasattr(self, "slippy_map"):
            self.slippy_map.end_pt = (lat, lon)
            if self.slippy_map.start_pt:
                self.slippy_map.center_lat = (self.slippy_map.start_pt[0] + lat) / 2.0
                self.slippy_map.center_lon = (self.slippy_map.start_pt[1] + lon) / 2.0
                span = max(abs(self.slippy_map.start_pt[0] - lat) * 1.3, abs(self.slippy_map.start_pt[1] - lon))
                self.slippy_map.zoom = max(11, min(16, int(round(math.log2(360.0 / max(0.005, span)))) - 2))
            else:
                self.slippy_map.center_lat = lat
                self.slippy_map.center_lon = lon
            self.slippy_map.redraw()

    def on_run(self):
        if self.running: return
        self.running = True
        self.run_btn.config(state="disabled")
        self.status.set("Starting optimization...")

        args = (self.start.get(), self.end.get())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, start_t, end_t):
        try:
            res = solve(start_t, end_t,
                        status=lambda m, t=None: self.q.put(("status", (m, t))),
                        demo=self.demo.get())
            self.q.put(("done", res))
        except Exception as err:
            self.q.put(("error", str(err)))

    def poll_queue(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "status":
                    msg, target = val
                    self.status.set(msg)
                    if target: self.bar["value"] = target
                elif kind == "done":
                    self.on_done(val)
                elif kind == "error":
                    messagebox.showerror("Execution Error", val)
                    self.status.set("Failed.")
                    self.run_btn.config(state="normal")
                    self.running = False
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def on_done(self, res):
        self.running = False
        self.run_btn.config(state="normal")
        self.bar["value"] = 100
        k = len(res["routes_data"])
        self.status.set(f"Optimization complete. Solved using {k} dynamic corridors (Min: 2).")

        # 1. Update KPI Cards
        sm = res["summary"]
        self.cards[0].set_data(f"{sm['pct']:.1f}%", "less total travel time")
        self.cards[1].set_data(f"{sm['real_cars']} cars", f"peak load ({k} corridors)")
        self.cards[2].set_data(f"{sm['selfish_cost']:.0f} min", "every car on Route 1")
        self.cards[3].set_data(f"{sm['best_cost']:.0f} min", f"{k} routes: {sm['split']}")

        # 2. Update Tables
        self.tbl_compare.delete(*self.tbl_compare.get_children())
        for row in res["compare_rows"]:
            self.tbl_compare.insert("", "end", values=row)

        self.tbl_routes.delete(*self.tbl_routes.get_children())
        for row in res["route_rows"]:
            self.tbl_routes.insert("", "end", values=row)

        # 3. Update Convergence Tab
        self.conv_pil = Image.open(io.BytesIO(res["images"]["conv"])).convert("RGB")
        self.update_conv_image()

        # 4. Load Routes into the Interactive Google Maps-style Slippy Map
        self.slippy_map.load_trip_data(res["routes_data"], res["start_pt"], res["end_pt"])
        self.segmented_bar.select(2)

if __name__ == "__main__":
    from main import main
    main()
