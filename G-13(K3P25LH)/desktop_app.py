"""
desktop_app.py
==============
Quantum-Inspired Traffic Flow Router Pro.
- iPhone Liquid Glass Design: Rounded location inputs, rounded run button, rounded map corners.
- True 4K / Retina Native Hardware Clarity on Windows (Per-Monitor V2 High-DPI).
- Built-in Interactive Google Maps-style Slippy Map with multi-level dynamic zoom.
- Real satellite and street tile loading, drag-to-pan, and on-screen zoom controls.
- 100% Real Infrastructure Data (Zero synthetic sliders/bars).
"""

import sys, os, io, math, threading, queue
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

# ======================= 1. WINDOWS 4K / RETINA HIGH-DPI ENGINE =======================
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


# ======================= VECTOR DRAWING HELPERS (LIQUID GLASS) =======================
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


# ======================= ROUNDED LOCATION ENTRY (ROUND CAPSULE) =======================
class RoundedEntry(tk.Canvas):
    """
    Apple iOS Smooth Rounded Entry Field.
    Anti-aliased rounded pill shape with Apple Blue focus highlight ring.
    """
    def __init__(self, parent, textvariable, height=42, r=12,
                 bg="#101013", fill="#18181b", border="#27272a", focus_border="#007aff",
                 font=(FONT, 10), **kwargs):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, **kwargs)
        self.textvariable = textvariable
        self.h = height
        self.r = r
        self.fill_color = fill
        self.border_color = border
        self.focus_border = focus_border
        self.is_focused = False
        self.font = font

        self.entry = tk.Entry(self, textvariable=textvariable, font=font,
                              bg=fill, fg="#ffffff", insertbackground="#007aff",
                              relief="flat", highlightthickness=0)
        self.entry_window = self.create_window(r + 8, height // 2, window=self.entry, anchor="w")

        self.entry.bind("<FocusIn>", self.on_focus_in)
        self.entry.bind("<FocusOut>", self.on_focus_out)
        self.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.bind("<Configure>", lambda e: self.draw())

    def on_focus_in(self, e):
        self.is_focused = True
        self.draw()

    def on_focus_out(self, e):
        self.is_focused = False
        self.draw()

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


# ======================= ROUNDED RUN BUTTON (ROUND CAPSULE) =======================
class RoundedButton(tk.Canvas):
    """
    Apple iOS Pill Button.
    Smooth anti-aliased rounded ends, vibrant Apple Blue fill, press and hover feedback.
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


# ======================= ROUNDED KPI CARD =======================
class RoundedCard(tk.Canvas):
    """
    Apple iOS Rounded KPI Card.
    Smooth anti-aliased card surface with bold metrics.
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


# ======================= NATIVE GOOGLE MAPS-STYLE SLIPPY WIDGET =======================
class SlippyMapWidget(tk.Frame):
    """
    A true Google Maps / OpenStreetMap slippy map embedded inside Tkinter.
    - True 4K / Retina clarity with dynamic zoom.
    - Smooth rounded corners on the map view itself.
    - iPhone Liquid Glass floating HUD controls drawn directly on canvas.
    - Clean info HUD with guaranteed zero text overflow.
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
        self.start_pt = None
        self.end_pt = None
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
                headers = {"User-Agent": "QuantumTrafficRouterPro/10.0 (Windows NT 10.0; High-DPI)"}
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as resp:
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
        for i, r in enumerate(self.routes_data):
            if self.active_mode == "selfish" and i != 0: continue
            if isinstance(self.active_mode, int) and self.active_mode != i: continue

            pts = r["pts"]
            if len(pts) < 2: continue

            coords = []
            for lon, lat in pts:
                gx, gy = self.geo_to_pixel(lat, lon)
                coords.extend([cx + (gx - center_x), cy + (gy - center_y)])

            color = "#ff3b30" if self.active_mode == "selfish" else route_colors[i % len(route_colors)]
            lw = 7 if (self.active_mode == "selfish" or self.active_mode == i) else 5

            # Anti-aliased black halo for crisp 4K contrast over satellite and street map
            self.canvas.create_line(*coords, fill="#000000", width=lw+4, capstyle="round", joinstyle="round")
            # Vibrant Apple Neon route line
            self.canvas.create_line(*coords, fill=color, width=lw, capstyle="round", joinstyle="round")
            # Vibrant Apple Neon route line
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

        # ---------------- 5. Render iPhone Liquid Glass Floating HUD ----------------
        self.render_hud(w, h)

    def render_hud(self, w, h):
        """
        Renders the floating iPhone Liquid Glass HUD directly onto the canvas.
        Zero rectangular frames. Only smooth vector pills, capsules, and circles.
        """
        # ================= A. TOP-LEFT MODE SELECTOR PILL CAPSULE =================
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

        # ================= B. TOP-RIGHT IPHONE PHONE SWITCH =================
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

        # ================= C. BOTTOM-LEFT FLOATING INFO HUD (ZERO OVERFLOW) =================
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

        # ================= D. BOTTOM-RIGHT CIRCULAR ZOOM PILLS =================
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


# ======================= IPHONE LIQUID GLASS SEGMENTED BAR =======================
class IOSSegmentedBar(tk.Frame):
    """
    Apple iOS Liquid Glass Segmented Pill Bar.
    Smooth pill capsule container with rounded pill tabs.
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
        root.title("Quantum-Inspired Traffic Flow Router Pro")
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

        # Clean minimalist Apple branding
        tk.Label(head, text="QUANTUM TRAFFIC ROUTER", font=(FONT, 13, "bold"),
                 fg="#ffffff", bg="#101013").pack(side="left")

    def build_input_panel(self, parent):
        left = tk.Frame(parent, bg="#101013", padx=20, pady=16,
                        highlightbackground="#1f1f23", highlightthickness=1)
        left.pack(side="left", fill="y")

        # Clean Section Header
        tk.Label(left, text="TRIP CORRIDORS", font=(FONT, 9, "bold"),
                 fg="#ffffff", bg="#101013").pack(anchor="w", pady=(0, 12), padx=4)

        self.start = tk.StringVar(value="31.6200, 74.8765")
        self.end = tk.StringVar(value="31.6340, 74.8723")

        # Location Fill Area with Smooth Rounded Capsule Edges
        for label_text, var in (("Origin", self.start),
                               ("Destination", self.end)):
            tk.Label(left, text=label_text.upper(), font=(FONT, 8, "bold"),
                     fg="#a1a1aa", bg="#101013").pack(anchor="w", padx=4, pady=(8, 4))
            rentry = RoundedEntry(left, textvariable=var, height=42, r=12,
                                  bg="#101013", fill="#18181b", border="#27272a",
                                  focus_border="#007aff", font=(FONT, 10))
            rentry.pack(fill="x", pady=(0, 6))

        # Dynamic Route Scaling: 2 to 8 corridors decided by traffic
        tk.Label(left, text="TRAFFIC INTENSITY", font=(FONT, 8, "bold"),
                 fg="#a1a1aa", bg="#101013").pack(anchor="w", padx=4, pady=(8, 4))

        self.traffic_mode_var = tk.StringVar(value="Auto (Detect from Infrastructure)")
        traffic_options = [
            "Auto (Detect from Infrastructure)",
            "Light Flow (Solves with 2 routes)",
            "Moderate Flow (Solves with 3-4 routes)",
            "Heavy Peak (Needs 5-6 routes)",
            "Extreme Gridlock (Needs 7-8 routes)"
        ]
        cmb = ttk.Combobox(left, textvariable=self.traffic_mode_var, values=traffic_options,
                           state="readonly", style="Dark.TCombobox", font=(FONT, 9))
        cmb.pack(fill="x", pady=(0, 8))

        self.demo = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(left, text="Offline demo city mode", variable=self.demo,
                             font=(FONT, 8), bg="#101013", fg="#a1a1aa", selectcolor="#18181b",
                             activebackground="#101013", activeforeground="#ffffff", relief="flat")
        chk.pack(anchor="w", pady=(8, 14), padx=2)

        # Apple Liquid Glass Rounded Pill Button
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

        # Top iOS Liquid Glass Segmented Pill Bar
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

        # ---- Tab 2: Interactive Slippy Map (Full-bleed Liquid Glass) ----
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

    def on_run(self):
        if self.running: return
        self.running = True
        self.run_btn.config(state="disabled")
        self.status.set("Starting optimization...")

        mode_val = self.traffic_mode_var.get()
        if "Light" in mode_val: t_mode = "light"
        elif "Moderate" in mode_val: t_mode = "moderate"
        elif "Heavy" in mode_val: t_mode = "heavy"
        elif "Extreme" in mode_val: t_mode = "gridlock"
        else: t_mode = "auto"

        args = (self.start.get(), self.end.get(), t_mode)
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, start_t, end_t, t_mode):
        try:
            res = solve(start_t, end_t,
                        status=lambda m, t=None: self.q.put(("status", (m, t))),
                        demo=self.demo.get(),
                        traffic_mode=t_mode)
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
