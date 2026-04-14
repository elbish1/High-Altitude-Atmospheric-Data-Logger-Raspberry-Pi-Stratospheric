# =============================================================================
# gui.py — Live Tkinter dashboard (modern UI)
# Runs on the main thread. Sensor loop runs on a background thread.
# They share a dict (shared_data) protected by a threading.Lock.
# =============================================================================

from __future__ import annotations

import math
import webbrowser
import tkinter as tk
from dataclasses import dataclass
from collections import deque

# =============================================================================
# Theme + utilities
# =============================================================================

@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    surface: str
    surface_2: str
    border: str
    text: str
    text_dim: str
    shadow: str
    accent_blue: str
    accent_red: str
    accent_yellow: str
    accent_green: str
    accent_purple: str


THEME_DARK = Theme(
    name="dark",
    # Deeper true-black style
    bg="#05060a",
    surface="#0c0e14",
    surface_2="#090b10",
    border="#1c2230",
    text="#eef2ff",
    text_dim="#a7b1d6",
    shadow="#000000",
    accent_blue="#4285F4",
    accent_red="#EA4335",
    accent_yellow="#FBBC05",
    accent_green="#34A853",
    accent_purple="#A142F4",
)


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix(c1: str, c2: str, t: float) -> str:
    t = _clamp(t, 0.0, 1.0)
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return _rgb_to_hex(r, g, b)


def _format_number(v, digits=2) -> str:
    if v is None:
        return "—"
    try:
        if isinstance(v, bool):
            return "YES" if v else "NO"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return "—"
            d = 0 if abs(v) >= 1000 else digits
            return f"{v:.{d}f}"
        return str(v)
    except Exception:
        return "—"


def _format_time_label(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


# =============================================================================
# Units
# =============================================================================

class Units:
    def __init__(self, root: tk.Misc):
        self.temp = tk.StringVar(root, "C")     # C / F
        self.alt = tk.StringVar(root, "m")      # m / ft
        self.press = tk.StringVar(root, "hPa")  # hPa / inHg

    def temp_from_c(self, v_c):
        if v_c is None:
            return None, "°" + self.temp.get()
        if self.temp.get() == "F":
            return (v_c * 9 / 5) + 32, "°F"
        return v_c, "°C"

    def alt_from_m(self, v_m):
        if v_m is None:
            return None, self.alt.get()
        if self.alt.get() == "ft":
            return v_m * 3.28084, "ft"
        return v_m, "m"

    def press_from_hpa(self, v_hpa):
        if v_hpa is None:
            return None, self.press.get()
        if self.press.get() == "inHg":
            return v_hpa * 0.0295299830714, "inHg"
        return v_hpa, "hPa"


# =============================================================================
# Drawing primitives (rounded cards + small animations)
# =============================================================================

class RoundedCard(tk.Canvas):
    def __init__(self, master, theme: Theme, radius=18, pad=14, **kw):
        super().__init__(
            master,
            bg=theme.bg,
            highlightthickness=0,
            bd=0,
            relief="flat",
            **kw,
        )
        self._theme = theme
        self._radius = radius
        self._pad = pad
        # IMPORTANT: Tkinter internally uses Widget._w for the widget path name.
        # Never reuse that attribute name for width/height state.
        self._width_px = 10
        self._height_px = 10
        self.bind("<Configure>", self._on_resize)

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)
        self._redraw()

    def _on_resize(self, _evt):
        self._width_px = max(10, self.winfo_width())
        self._height_px = max(10, self.winfo_height())
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self._width_px, self._height_px
        r = min(self._radius, w // 2, h // 2)
        # shadow
        sh = 5
        self._rounded_rect(
            sh, sh, w - 1, h - 1,
            r,
            fill=_mix(self._theme.shadow, self._theme.bg, 0.25),
            outline="",
        )
        # surface
        self._rounded_rect(
            0, 0, w - 1 - sh, h - 1 - sh,
            r,
            fill=self._theme.surface,
            outline=self._theme.border,
            width=1,
        )

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
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
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kw)


class Segmented(tk.Frame):
    def __init__(self, master, theme: Theme, label: str, var: tk.StringVar, options: list[str]):
        super().__init__(master, bg=theme.bg)
        self._theme = theme
        self._var = var
        self._btns: dict[str, tk.Label] = {}

        self._lbl = tk.Label(self, text=label, bg=theme.bg, fg=theme.text_dim, font=("Segoe UI", 9))
        self._lbl.pack(side="left", padx=(0, 10))

        wrap = tk.Frame(self, bg=theme.bg)
        wrap.pack(side="left")

        for i, opt in enumerate(options):
            b = tk.Label(
                wrap,
                text=opt,
                padx=10,
                pady=6,
                cursor="hand2",
                font=("Segoe UI Semibold", 9),
                bd=1,
                relief="solid",
            )
            b.pack(side="left")
            b.bind("<Button-1>", lambda _e, o=opt: self._on_pick(o))
            self._btns[opt] = b

            if i < len(options) - 1:
                sep = tk.Frame(wrap, width=2, bg=theme.bg)
                sep.pack(side="left")

        self._var.trace_add("write", lambda *_: self._apply())
        self._apply()

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)
        self._lbl.configure(bg=theme.bg, fg=theme.text_dim)
        for b in self._btns.values():
            b.configure(font=("Segoe UI Semibold", 9))
        self._apply()

    def _on_pick(self, opt: str):
        self._var.set(opt)

    def _apply(self):
        for opt, b in self._btns.items():
            selected = (self._var.get() == opt)
            b.configure(
                bg=self._theme.accent_blue if selected else self._theme.surface_2,
                fg="#ffffff" if selected else self._theme.text,
                highlightthickness=0,
                bd=1,
                relief="solid",
            )
            b.configure(
                borderwidth=1,
            )
            b.configure(
                highlightbackground=self._theme.accent_blue if selected else self._theme.border,
            )


# =============================================================================
# Graph widget (pure Tk Canvas)
# =============================================================================

class LineGraph(tk.Canvas):
    def __init__(self, master, theme: Theme, title: str, color: str, max_points=180):
        super().__init__(master, bg=theme.bg, highlightthickness=0, bd=0)
        self._theme = theme
        self._title = title
        self._color = color
        self._max_points = max_points
        self._values = deque(maxlen=max_points)
        self._labels = deque(maxlen=max_points)
        self.bind("<Configure>", lambda _e: self._draw())

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)
        self._draw()

    def push(self, label: str, value):
        self._labels.append(label)
        self._values.append(value)

    def _draw(self):
        self.delete("all")
        w = max(10, self.winfo_width())
        h = max(10, self.winfo_height())

        pad = 16
        title_h = 28
        plot_x1, plot_y1 = pad, pad + title_h
        plot_x2, plot_y2 = w - pad, h - pad

        # Title
        self.create_text(
            pad, pad,
            anchor="nw",
            text=self._title,
            fill=self._theme.text,
            font=("Segoe UI Semibold", 11),
        )

        # Plot background
        self.create_rectangle(
            plot_x1, plot_y1, plot_x2, plot_y2,
            fill=self._theme.surface,
            outline=self._theme.border,
            width=1,
        )

        vals = [v for v in self._values if isinstance(v, (int, float))]
        if len(vals) < 2:
            self.create_text(
                (plot_x1 + plot_x2) / 2,
                (plot_y1 + plot_y2) / 2,
                text="Waiting for data…",
                fill=self._theme.text_dim,
                font=("Segoe UI", 10),
            )
            return

        vmin = min(vals)
        vmax = max(vals)
        if abs(vmax - vmin) < 1e-9:
            vmax = vmin + 1.0

        # Grid lines
        grid = 4
        for i in range(grid + 1):
            y = plot_y1 + (plot_y2 - plot_y1) * i / grid
            self.create_line(plot_x1, y, plot_x2, y, fill=_mix(self._theme.border, self._theme.surface, 0.4))

        # Build points
        n = len(self._values)
        xs = []
        ys = []
        for i, v in enumerate(self._values):
            if not isinstance(v, (int, float)):
                continue
            x = plot_x1 + (plot_x2 - plot_x1) * (i / max(1, n - 1))
            t = (v - vmin) / (vmax - vmin)
            y = plot_y2 - (plot_y2 - plot_y1) * t
            xs.append(x)
            ys.append(y)

        if len(xs) < 2:
            return

        # Line + glow
        for width, alpha in [(8, 0.15), (5, 0.22), (3, 1.0)]:
            c = _mix(self._color, self._theme.surface, 1 - alpha)
            self.create_line(*sum(zip(xs, ys), ()), fill=c, width=width, smooth=True)

        # Last value badge
        last = None
        for v in reversed(self._values):
            if isinstance(v, (int, float)):
                last = v
                break
        if last is not None:
            badge = f"{_format_number(last)}"
            self.create_text(
                plot_x2 - 10, plot_y1 + 10,
                anchor="ne",
                text=badge,
                fill=self._theme.text,
                font=("Segoe UI Semibold", 10),
            )


class TimeSeriesGraph(tk.Canvas):
    """
    A simple interactive time-series plot:
    - Axes + ticks (X time, Y value)
    - Mouse wheel zoom (time window)
    - Click-drag pan (time navigation)
    """

    def __init__(
        self,
        master,
        theme: Theme,
        title: str,
        color: str,
        y_unit: str = "",
        max_points: int = 3600,
    ):
        super().__init__(master, bg=theme.bg, highlightthickness=0, bd=0)
        self._theme = theme
        self._title = title
        self._color = color
        self._y_unit = y_unit
        self._labels = deque(maxlen=max_points)  # time labels (HH:MM:SS)
        self._values = deque(maxlen=max_points)

        self._view_window = 180  # points shown (default 3 minutes @1Hz)
        self._view_end_offset = 0  # 0 means newest at right edge
        self._drag = None

        # Axis controls
        self._y_auto = True
        self._y_scale = 1.0   # >1 zoom in (less span)
        self._y_offset = 0.0  # shift center in data units

        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<MouseWheel>", self._on_wheel)          # Windows
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_move)
        self.bind("<ButtonRelease-1>", self._on_drag_end)
        self.bind("<ButtonPress-3>", self._on_y_drag_start)
        self.bind("<B3-Motion>", self._on_y_drag_move)
        self.bind("<ButtonRelease-3>", self._on_y_drag_end)

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)
        self._draw()

    def set_y_unit(self, unit: str):
        self._y_unit = unit or ""
        self._draw()

    def set_window_points(self, points: int):
        self._view_window = int(_clamp(points, 30, 3600))
        self._view_end_offset = int(_clamp(self._view_end_offset, 0, max(0, len(self._values) - 2)))
        self._draw()

    def reset_view(self):
        self._view_window = 180
        self._view_end_offset = 0
        self._y_auto = True
        self._y_scale = 1.0
        self._y_offset = 0.0
        self._draw()

    def push(self, label: str, value):
        self._labels.append(label)
        self._values.append(value)

    def _on_wheel(self, e):
        # Wheel:
        # - normal: zoom X (time)
        # - Shift+wheel: zoom Y (value)
        delta = e.delta
        shift = bool(e.state & 0x0001)
        if shift:
            self._y_auto = False
            if delta > 0:
                self._y_scale = _clamp(self._y_scale * 1.15, 0.2, 25.0)
            else:
                self._y_scale = _clamp(self._y_scale / 1.15, 0.2, 25.0)
            self._draw()
            return

        if delta > 0:
            self.set_window_points(int(self._view_window * 0.85))
        else:
            self.set_window_points(int(self._view_window * 1.15))

    def _on_drag_start(self, e):
        self._drag = {"x": e.x, "start_offset": self._view_end_offset}

    def _on_drag_move(self, e):
        if not self._drag:
            return
        w = max(10, self.winfo_width())
        pad_l = 56
        pad_r = 14
        plot_w = max(1, w - pad_l - pad_r)
        dx = e.x - self._drag["x"]
        points_shift = int((dx / plot_w) * max(5, self._view_window))
        # dragging right should move to older data
        new_offset = self._drag["start_offset"] + points_shift
        max_offset = max(0, len(self._values) - 2)
        self._view_end_offset = int(_clamp(new_offset, 0, max_offset))
        self._draw()

    def _on_drag_end(self, _e):
        self._drag = None

    def _on_y_drag_start(self, e):
        self._y_auto = False
        self._drag = {"y": e.y, "start_offset": self._y_offset}

    def _on_y_drag_move(self, e):
        if not self._drag or "y" not in self._drag:
            return
        h = max(10, self.winfo_height())
        pad_t = 14 + 22
        pad_b = 34
        plot_h = max(1, h - pad_t - pad_b)
        dy = e.y - self._drag["y"]
        # convert pixels to data-unit offset approximately; scale using current span guess.
        labels, values = self._view_slice()
        vals = [v for v in values if isinstance(v, (int, float))]
        if len(vals) < 2:
            return
        vmin = min(vals)
        vmax = max(vals)
        span = (vmax - vmin) / max(0.1, self._y_scale)
        units_per_px = span / plot_h
        self._y_offset = self._drag["start_offset"] + (dy * units_per_px)
        self._draw()

    def _on_y_drag_end(self, _e):
        self._drag = None

    def _view_slice(self):
        n = len(self._values)
        if n <= 1:
            return [], []
        end = n - self._view_end_offset
        start = max(0, end - self._view_window)
        vals = list(self._values)[start:end]
        labs = list(self._labels)[start:end]
        return labs, vals

    def _nice_ticks(self, vmin: float, vmax: float, n: int = 5):
        if vmax <= vmin:
            return [vmin]
        span = vmax - vmin
        raw = span / max(1, n)
        mag = 10 ** math.floor(math.log10(raw))
        norm = raw / mag
        step = 1 * mag
        if norm >= 5:
            step = 5 * mag
        elif norm >= 2:
            step = 2 * mag
        elif norm >= 1:
            step = 1 * mag
        start = math.floor(vmin / step) * step
        ticks = []
        x = start
        while x <= vmax + step:
            if x >= vmin - step:
                ticks.append(x)
            x += step
        return ticks

    def _draw(self):
        self.delete("all")
        w = max(10, self.winfo_width())
        h = max(10, self.winfo_height())

        pad_t = 14
        pad_r = 14
        pad_b = 34
        pad_l = 56
        title_h = 22

        plot_x1, plot_y1 = pad_l, pad_t + title_h
        plot_x2, plot_y2 = w - pad_r, h - pad_b

        # Title
        title = self._title + (f" ({self._y_unit})" if self._y_unit else "")
        self.create_text(
            pad_l, pad_t,
            anchor="nw",
            text=title,
            fill=self._theme.text,
            font=("Segoe UI Semibold", 11),
        )

        # Plot background
        self.create_rectangle(
            plot_x1, plot_y1, plot_x2, plot_y2,
            fill=self._theme.surface,
            outline=self._theme.border,
            width=1,
        )

        labels, values = self._view_slice()
        vals = [v for v in values if isinstance(v, (int, float))]
        if len(vals) < 2:
            self.create_text(
                (plot_x1 + plot_x2) / 2,
                (plot_y1 + plot_y2) / 2,
                text="Waiting for data...",
                fill=self._theme.text_dim,
                font=("Segoe UI", 10),
            )
            return

        vmin = min(vals)
        vmax = max(vals)
        if abs(vmax - vmin) < 1e-9:
            vmax = vmin + 1.0

        if not self._y_auto:
            mid = (vmin + vmax) / 2.0 + self._y_offset
            span = (vmax - vmin) / max(0.1, self._y_scale)
            vmin = mid - span / 2.0
            vmax = mid + span / 2.0

        # Y ticks + grid
        ticks = self._nice_ticks(vmin, vmax, n=4)
        for t in ticks:
            ty = (t - vmin) / (vmax - vmin)
            y = plot_y2 - (plot_y2 - plot_y1) * ty
            self.create_line(plot_x1, y, plot_x2, y, fill=_mix(self._theme.border, self._theme.surface, 0.45))
            self.create_text(
                plot_x1 - 8, y,
                anchor="e",
                text=_format_number(t, digits=2),
                fill=self._theme.text_dim,
                font=("Segoe UI", 9),
            )

        # X axis ticks (time)
        n = len(values)
        if n >= 2:
            xticks = 4
            for i in range(xticks + 1):
                x = plot_x1 + (plot_x2 - plot_x1) * i / xticks
                idx = int((n - 1) * i / xticks)
                lab = labels[idx] if idx < len(labels) else ""
                self.create_line(x, plot_y2, x, plot_y2 + 5, fill=self._theme.border)
                self.create_text(
                    x, plot_y2 + 16,
                    anchor="n",
                    text=lab,
                    fill=self._theme.text_dim,
                    font=("Segoe UI", 9),
                )

        # Polyline points
        xs = []
        ys = []
        for i, v in enumerate(values):
            if not isinstance(v, (int, float)):
                continue
            x = plot_x1 + (plot_x2 - plot_x1) * (i / max(1, n - 1))
            t = (v - vmin) / (vmax - vmin)
            y = plot_y2 - (plot_y2 - plot_y1) * t
            xs.append(x)
            ys.append(y)

        if len(xs) >= 2:
            coords: list[float] = []
            for x, y in zip(xs, ys):
                coords.append(x)
                coords.append(y)

            # Cheaper draw: fewer glow passes + no smoothing (Tk smoothing is expensive).
            for width, alpha in [(6, 0.18), (3, 1.0)]:
                c = _mix(self._color, self._theme.surface, 1 - alpha)
                self.create_line(*coords, fill=c, width=width, smooth=False)

        # View hint
        view_seconds = self._view_window
        hint = f"X: wheel/drag   Y: Shift+wheel / right-drag   Window: {_format_time_label(view_seconds)}"
        self.create_text(
            plot_x2, pad_t,
            anchor="ne",
            text=hint,
            fill=self._theme.text_dim,
            font=("Segoe UI", 9),
        )


# =============================================================================
# App pages
# =============================================================================

class DashboardPage(tk.Frame):
    def __init__(self, master, theme: Theme, units: Units):
        super().__init__(master, bg=theme.bg)
        self._theme = theme
        self._units = units
        self._cards: dict[str, dict] = {}

        self._title = tk.Label(self, text="Live Dashboard", bg=theme.bg, fg=theme.text, font=("Segoe UI Semibold", 16))
        self._title.pack(anchor="w", padx=18, pady=(16, 10))

        self._grid = tk.Frame(self, bg=theme.bg)
        self._grid.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # Cards definition: (label, key, accent, formatter)
        self._defs = [
            ("Baro Altitude", "altitude_baro_m", theme.accent_blue, "alt_m"),
            ("GPS Altitude", "alt_gps_m", theme.accent_purple, "alt_m"),
            ("Temperature", "temperature_c", theme.accent_yellow, "temp_c"),
            ("Pressure", "pressure_hpa", theme.accent_red, "press_hpa"),
            ("Humidity", "humidity_pct", theme.accent_green, "pct"),
            ("GPS Fix", "gps_fix", theme.accent_green, "bool"),
            ("Satellites", "satellites", theme.accent_blue, "int"),
            ("Latitude", "lat", theme.accent_purple, "deg"),
            ("Longitude", "lon", theme.accent_purple, "deg"),
            ("Accel Z", "accel_z", theme.accent_yellow, "ms2"),
        ]

        for i, d in enumerate(self._defs):
            r, c = divmod(i, 3)
            self._grid.columnconfigure(c, weight=1, uniform="col")
            self._grid.rowconfigure(r, weight=1, uniform="row")
            self._add_card(r, c, *d)

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)
        self._title.configure(bg=theme.bg, fg=theme.text)
        self._grid.configure(bg=theme.bg)
        for key, c in self._cards.items():
            c["card"].set_theme(theme)
            c["label"].configure(bg=theme.surface, fg=theme.text_dim)
            c["value"].configure(bg=theme.surface, fg=theme.text)
            c["unit"].configure(bg=theme.surface, fg=theme.text_dim)
            c["bar"].configure(bg=c["accent"])

    def _add_card(self, r, c, label, key, accent, fmt):
        wrap = tk.Frame(self._grid, bg=self._theme.bg)
        wrap.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)

        card = RoundedCard(wrap, self._theme, radius=22)
        card.pack(fill="both", expand=True)

        # content overlay frame (to place real widgets)
        inner = tk.Frame(wrap, bg=self._theme.surface)
        inner.place(relx=0, rely=0, relwidth=1, relheight=1, x=0, y=0)

        bar = tk.Frame(inner, bg=accent, width=6)
        bar.pack(side="left", fill="y")

        body = tk.Frame(inner, bg=self._theme.surface)
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        lbl = tk.Label(body, text=label, bg=self._theme.surface, fg=self._theme.text_dim, font=("Segoe UI", 10))
        lbl.pack(anchor="w")

        row = tk.Frame(body, bg=self._theme.surface)
        row.pack(anchor="w", pady=(4, 0))

        val = tk.Label(row, text="—", bg=self._theme.surface, fg=self._theme.text, font=("Segoe UI Semibold", 20))
        val.pack(side="left")

        unit = tk.Label(row, text="", bg=self._theme.surface, fg=self._theme.text_dim, font=("Segoe UI", 11))
        unit.pack(side="left", padx=(10, 0), pady=(6, 0))

        self._cards[key] = {
            "card": card,
            "inner": inner,
            "bar": bar,
            "label": lbl,
            "value": val,
            "unit": unit,
            "accent": accent,
            "fmt": fmt,
        }

    def update_values(self, snap: dict):
        for key, c in self._cards.items():
            raw = snap.get(key)
            fmt = c["fmt"]
            txt = "—"
            unit = ""

            if fmt == "temp_c":
                v, u = self._units.temp_from_c(raw)
                txt = _format_number(v, digits=2)
                unit = u
            elif fmt == "alt_m":
                v, u = self._units.alt_from_m(raw)
                txt = _format_number(v, digits=1)
                unit = u
            elif fmt == "press_hpa":
                v, u = self._units.press_from_hpa(raw)
                txt = _format_number(v, digits=2)
                unit = u
            elif fmt == "pct":
                txt = _format_number(raw, digits=1)
                unit = "%"
            elif fmt == "deg":
                txt = _format_number(raw, digits=6)
                unit = "°"
            elif fmt == "ms2":
                txt = _format_number(raw, digits=3)
                unit = "m/s²"
            elif fmt == "int":
                txt = _format_number(raw, digits=0)
                unit = ""
            elif fmt == "bool":
                if raw is None:
                    txt, unit = "—", ""
                else:
                    txt = "YES" if bool(raw) else "NO"
                    unit = ""
                    c["bar"].configure(bg=self._theme.accent_green if bool(raw) else self._theme.accent_red)

            c["value"].configure(text=txt)
            c["unit"].configure(text=unit)


class GraphsPage(tk.Frame):
    def __init__(self, master, theme: Theme, units: Units):
        super().__init__(master, bg=theme.bg)
        self._theme = theme
        self._units = units
        # Keep base-unit history so unit switching can rebuild accurately.
        # Up to 24h @ 1Hz = 86400 points (keep headroom).
        self._raw_ts = deque(maxlen=90000)
        self._raw_alt_m = deque(maxlen=90000)
        self._raw_temp_c = deque(maxlen=90000)
        self._raw_pres_hpa = deque(maxlen=90000)
        self._raw_hum_pct = deque(maxlen=90000)
        self._title = tk.Label(self, text="Graphs & Analysis", bg=theme.bg, fg=theme.text, font=("Segoe UI Semibold", 16))
        self._title.pack(anchor="w", padx=18, pady=(16, 10))

        # Controls (time window)
        ctrl = tk.Frame(self, bg=theme.bg)
        ctrl.pack(fill="x", padx=14, pady=(0, 6))

        self._time_range = tk.StringVar(self, "3m")
        tk.Label(ctrl, text="Time range", bg=theme.bg, fg=theme.text_dim, font=("Segoe UI", 9)).pack(side="left", padx=(4, 8))
        self._time_menu = tk.OptionMenu(
            ctrl,
            self._time_range,
            "1m", "2m", "3m", "5m", "10m", "15m", "30m",
            "45m", "1h", "2h", "3h", "6h", "12h", "24h",
        )
        self._time_menu.pack(side="left")
        self._time_range.trace_add("write", lambda *_: self._apply_window())

        self._btn_reset = tk.Label(ctrl, text="Reset view", cursor="hand2", padx=10, pady=6, bd=1, relief="solid")
        self._btn_reset.pack(side="right", padx=4)
        self._btn_reset.bind("<Button-1>", lambda _e: self._reset_all())

        grid = tk.Frame(self, bg=theme.bg)
        grid.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        for c in range(2):
            grid.columnconfigure(c, weight=1, uniform="gcol")
        for r in range(2):
            grid.rowconfigure(r, weight=1, uniform="grow")

        self.g_alt = TimeSeriesGraph(grid, theme, "Altitude (baro)", theme.accent_blue, y_unit="m")
        self.g_temp = TimeSeriesGraph(grid, theme, "Temperature", theme.accent_yellow, y_unit="°C")
        self.g_pres = TimeSeriesGraph(grid, theme, "Pressure", theme.accent_red, y_unit="hPa")
        self.g_hum = TimeSeriesGraph(grid, theme, "Humidity", theme.accent_green, y_unit="%")

        self.g_alt.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.g_temp.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.g_pres.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.g_hum.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)
        self._title.configure(bg=theme.bg, fg=theme.text)
        # OptionMenu styling (best-effort across Tk builds)
        try:
            self._time_menu.configure(
                bg=theme.surface_2,
                fg=theme.text,
                activebackground=_mix(theme.surface_2, theme.accent_blue, 0.15),
                activeforeground=theme.text,
                highlightthickness=0,
                bd=1,
                relief="solid",
            )
            self._time_menu["menu"].configure(
                bg=theme.surface,
                fg=theme.text,
                activebackground=_mix(theme.surface_2, theme.accent_blue, 0.15),
                activeforeground=theme.text,
                bd=0,
            )
        except Exception:
            pass
        self._btn_reset.configure(
            bg=theme.surface_2,
            fg=theme.text,
            highlightthickness=0,
            borderwidth=1,
        )
        self._btn_reset.configure(highlightbackground=theme.border)
        for g in [self.g_alt, self.g_temp, self.g_pres, self.g_hum]:
            g.set_theme(theme)

    def push(self, ts: str, alt_b, temp, pres, hum):
        # Store raw base units, then render using current unit selection.
        self._raw_ts.append(ts)
        self._raw_alt_m.append(alt_b)
        self._raw_temp_c.append(temp)
        self._raw_pres_hpa.append(pres)
        self._raw_hum_pct.append(hum)

        self._push_converted(ts, alt_b, temp, pres, hum)

    def _push_converted(self, ts: str, alt_m, temp_c, pres_hpa, hum_pct):
        alt_v, alt_u = self._units.alt_from_m(alt_m)
        tmp_v, tmp_u = self._units.temp_from_c(temp_c)
        prs_v, prs_u = self._units.press_from_hpa(pres_hpa)

        self.g_alt.set_y_unit(alt_u)
        self.g_temp.set_y_unit(tmp_u)
        self.g_pres.set_y_unit(prs_u)
        self.g_hum.set_y_unit("%")

        self.g_alt.push(ts, alt_v)
        self.g_temp.push(ts, tmp_v)
        self.g_pres.push(ts, prs_v)
        self.g_hum.push(ts, hum_pct)

    def on_units_changed(self):
        # Reset graphs to avoid mixed-unit history causing wrong scaling.
        for g in (self.g_alt, self.g_temp, self.g_pres, self.g_hum):
            g.reset_view()
            g._labels.clear()  # noqa: SLF001
            g._values.clear()  # noqa: SLF001

        for ts, a, t, p, h in zip(self._raw_ts, self._raw_alt_m, self._raw_temp_c, self._raw_pres_hpa, self._raw_hum_pct):
            self._push_converted(ts, a, t, p, h)
        self.redraw_all()

    def redraw_all(self):
        for g in (self.g_alt, self.g_temp, self.g_pres, self.g_hum):
            g._draw()  # noqa: SLF001

    def redraw_step(self, idx: int):
        # Draw only one graph per tick to reduce UI lag.
        graphs = (self.g_alt, self.g_temp, self.g_pres, self.g_hum)
        graphs[idx % len(graphs)]._draw()  # noqa: SLF001

    def _apply_window(self):
        v = self._time_range.get()
        points = 180
        if v.endswith("m"):
            points = int(v[:-1]) * 60
        elif v.endswith("h"):
            points = int(v[:-1]) * 3600
        for g in (self.g_alt, self.g_temp, self.g_pres, self.g_hum):
            g.set_window_points(points)

    def _reset_all(self):
        for g in (self.g_alt, self.g_temp, self.g_pres, self.g_hum):
            g.reset_view()


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    return u


def _open_url(url: str):
    u = _normalize_url(url)
    if u:
        webbrowser.open(u)


CREDITS_TEAM = [
    {"name": "Yousef Amr Abdelazeem Elbish", "id": "2301295", "linkedin": "https://linkedin.com/in/elbish1", "portfolio": "https://yousef-elbish.vercel.app"},
    {"name": "Noor Mohamed Elmansy", "id": "2301271", "linkedin": "www.linkedin.com/in/noor-elmansy-309b99313", "portfolio": "https://noor-portofolio.netlify.app"},
    {"name": "Fatma Mohamed Soliman", "id": "2301166", "linkedin": "https://www.linkedin.com/in/fatma-mohamed-b59820290", "portfolio": "https://cute-twilight-78cf35.netlify.app/"},
    {"name": "Ahmed Kamel Hassanin", "id": "2301030", "linkedin": "https://www.linkedin.com/in/ahmed-kamel-4b161828a"},
    {"name": "Abanoub Amir George", "id": "2301001", "linkedin": "https://www.linkedin.com/in/abanoub-amir-6a1b512a3"},
    {"name": "Nada Wesam Alhlwany", "id": "2301270", "linkedin": "https://www.linkedin.com/in/nada-wesam"},
    {"name": "Sohaila Adel Nassar", "id": "2301118", "linkedin": "https://www.linkedin.com/in/sohaila-adel-2b01502b8"},
    {"name": "Mahmoud Abdelghany Depian", "id": "2301226", "linkedin": "https://www.linkedin.com/in/mahmoud-depian"},
    {"name": "Adham Sameh", "id": "2301047", "linkedin": "https://www.linkedin.com/in/adham-sameh-8b2a6b378"},
    {"name": "Ola Zaher Mohamed", "id": "2301153", "linkedin": "https://www.linkedin.com/in/ola-zaher"},
    {"name": "Mohamed Abdallah Mohamed", "id": "2301202"},
]

THANKS_LETTER = """We would like to express our sincere and heartfelt gratitude to Dr. Eman Salah for her continuous support, patient guidance, and invaluable feedback throughout every stage of this project.

Her encouragement helped us navigate challenges with confidence, and her insights deepened our understanding of how Internet of Things concepts translate into real, working systems—from sensor integration and data logging to practical deployment considerations.

We are especially grateful for the time she invested in reviewing our progress, suggesting improvements, and inspiring us to aim for quality and clarity in both our implementation and our documentation.

She consistently challenged us to think critically, refine our design decisions, and connect classroom theory with hands-on engineering practice. Her feedback strengthened not only the technical outcome of this work, but also our teamwork, communication, and problem-solving skills.

This project would not have reached a successful conclusion without her dedication, professionalism, and commitment to our learning. We truly appreciate her effort, mentorship, and the positive impact she has had on our academic journey.

With deep respect and appreciation, we thank Dr. Eman Salah for inspiring us to build something meaningful and for helping us grow as future computing and IoT practitioners."""


class CreditsPage(tk.Frame):
    """Scrollable credits: project info, team, links with icon badges, thank-you letter."""

    def __init__(self, master, theme: Theme):
        super().__init__(master, bg=theme.bg)
        self._theme = theme

        header = tk.Frame(self, bg=theme.bg)
        header.pack(fill="x", padx=20, pady=(18, 8))

        tk.Label(
            header,
            text="CREDITS",
            bg=theme.bg,
            fg=theme.accent_yellow,
            font=("Georgia", 26, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header,
            text="High Altitude Atmospheric Data Logger",
            bg=theme.bg,
            fg=theme.accent_blue,
            font=("Cambria", 18, "italic"),
        ).pack(anchor="w", pady=(4, 0))

        meta = tk.Frame(self, bg=theme.bg)
        meta.pack(fill="x", padx=20, pady=(0, 12))
        lines = [
            ("Group", "S1", theme.accent_green),
            ("Institution", "Al Ryada University for Science and Technology", theme.accent_purple),
            ("Faculty", "Faculty of Computers and Artificial Intelligence", theme.text_dim),
            ("Course", "INTERNET OF THINGS (CCS 329)", theme.accent_red),
            ("Submitted To", "Dr. Eman Salah", theme.accent_yellow),
            ("Semester", "Spring 2025-2026", theme.text),
        ]
        for label, value, color in lines:
            row = tk.Frame(meta, bg=theme.bg)
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=f"{label}:", bg=theme.bg, fg=theme.text_dim, font=("Consolas", 10, "bold")).pack(side="left", padx=(0, 8))
            tk.Label(row, text=value, bg=theme.bg, fg=color, font=("Segoe UI Semibold", 11)).pack(side="left")

        tk.Frame(self, height=2, bg=theme.border).pack(fill="x", padx=20, pady=10)

        tk.Label(
            self,
            text="TEAM MEMBERS",
            bg=theme.bg,
            fg=theme.accent_blue,
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w", padx=20, pady=(4, 8))

        scroll_wrap = tk.Frame(self, bg=theme.bg)
        scroll_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        canvas = tk.Canvas(scroll_wrap, bg=theme.bg, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(scroll_wrap, orient="vertical", command=canvas.yview, bg=theme.surface_2, troughcolor=theme.bg)
        inner = tk.Frame(canvas, bg=theme.bg)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _cfg_inner(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(win_id, width=canvas.winfo_width())

        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _focus_scroll(_e=None):
            canvas.focus_set()

        scroll_wrap.bind("<Enter>", _focus_scroll)
        canvas.bind("<Enter>", _focus_scroll)
        canvas.bind("<MouseWheel>", _wheel)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        try:
            canvas.configure(takefocus=1)
        except Exception:
            pass

        accents = [
            theme.accent_blue, theme.accent_green, theme.accent_yellow,
            theme.accent_red, theme.accent_purple,
        ]
        for i, m in enumerate(CREDITS_TEAM):
            self._member_card(inner, i + 1, m, accents[i % len(accents)])

        tk.Frame(inner, height=2, bg=theme.border).pack(fill="x", pady=16, padx=8)

        thanks_hdr = tk.Label(
            inner,
            text="THANK YOU LETTER",
            bg=theme.bg,
            fg=theme.accent_green,
            font=("Georgia", 17, "bold"),
        )
        thanks_hdr.pack(anchor="w", padx=8, pady=(8, 6))

        thanks_box = tk.Frame(inner, bg=_mix(theme.surface, theme.accent_purple, 0.08), highlightbackground=theme.border, highlightthickness=1)
        thanks_box.pack(fill="x", padx=8, pady=(0, 24))

        thanks_lbl = tk.Label(
            thanks_box,
            text=THANKS_LETTER,
            bg=_mix(theme.surface, theme.accent_purple, 0.08),
            fg=theme.text,
            font=("Georgia", 14, "italic"),
            justify="left",
            wraplength=880,
            padx=22,
            pady=22,
        )
        thanks_lbl.pack(anchor="w")

        def _thanks_wrap(_e=None):
            try:
                w = max(280, inner.winfo_width() - 48)
                thanks_lbl.configure(wraplength=w)
            except Exception:
                pass

        def _inner_configure(e=None):
            _thanks_wrap()
            _cfg_inner(e)

        inner.bind("<Configure>", _inner_configure)
        self.after_idle(lambda: _inner_configure())

    def _linkedin_badge(self, parent, bg: str) -> tk.Canvas:
        c = tk.Canvas(parent, width=26, height=26, bg=bg, highlightthickness=0, bd=0)
        c.create_polygon(
            4, 4, 22, 4, 22, 22, 4, 22,
            smooth=True,
            fill="#0A66C2",
            outline="",
        )
        c.create_text(13, 13, text="in", fill="#ffffff", font=("Arial", 10, "bold"))
        return c

    def _web_badge(self, parent, theme: Theme, surface_bg: str) -> tk.Canvas:
        c = tk.Canvas(parent, width=26, height=26, bg=surface_bg, highlightthickness=0, bd=0)
        c.create_polygon(
            4, 4, 22, 4, 22, 22, 4, 22,
            smooth=True,
            fill=_mix(theme.accent_green, "#ffffff", 0.15),
            outline=theme.border,
        )
        c.create_text(13, 13, text="www", fill=theme.text, font=("Consolas", 7, "bold"))
        return c

    def _member_card(self, parent, index: int, m: dict, accent: str):
        t = self._theme
        card = tk.Frame(parent, bg=t.surface, highlightbackground=accent, highlightthickness=2)
        card.pack(fill="x", padx=8, pady=6)

        top = tk.Frame(card, bg=t.surface)
        top.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(
            top,
            text=f"{index}.  {m['name']}",
            bg=t.surface,
            fg=accent,
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")
        tk.Label(
            top,
            text=f"ID: {m['id']} |   Group: S1",
            bg=t.surface,
            fg=t.text_dim,
            font=("Consolas", 10),
        ).pack(anchor="w", pady=(4, 0))

        links = tk.Frame(card, bg=t.surface)
        links.pack(fill="x", padx=14, pady=(0, 12))

        if m.get("linkedin"):
            row = tk.Frame(links, bg=t.surface)
            row.pack(anchor="w", pady=3)
            self._linkedin_badge(row, t.surface).pack(side="left", padx=(0, 8))
            lbl = tk.Label(
                row,
                text=_normalize_url(m["linkedin"]),
                bg=t.surface,
                fg=t.accent_blue,
                font=("Consolas", 9, "underline"),
                cursor="hand2",
            )
            lbl.pack(side="left")
            u = _normalize_url(m["linkedin"])
            lbl.bind("<Button-1>", lambda _e, url=u: _open_url(url))

        if m.get("portfolio"):
            row = tk.Frame(links, bg=t.surface)
            row.pack(anchor="w", pady=3)
            self._web_badge(row, t, t.surface).pack(side="left", padx=(0, 8))
            lbl = tk.Label(
                row,
                text=m["portfolio"],
                bg=t.surface,
                fg=t.accent_green,
                font=("Consolas", 9, "underline"),
                cursor="hand2",
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda _e, url=m["portfolio"]: _open_url(url))

    def set_theme(self, theme: Theme):
        self._theme = theme
        self.configure(bg=theme.bg)


# =============================================================================
# Main App shell (borderless + navigation)
# =============================================================================

class _AppShell(tk.Frame):
    def __init__(self, root: tk.Tk, shared_data: dict, data_lock):
        super().__init__(root)
        self.root = root
        self.data = shared_data
        self.lock = data_lock

        self.units = Units(root)
        self._theme = THEME_DARK

        self._history = {
            "ts": deque(maxlen=240),
            "altitude_baro_m": deque(maxlen=240),
            "temperature_c": deque(maxlen=240),
            "pressure_hpa": deque(maxlen=240),
            "humidity_pct": deque(maxlen=240),
        }

        self._build_root()
        self._build_layout()
        self._apply_theme(self._theme)
        self._tick_anim = 0

        # When units change, rebuild graphs cleanly (no mixed units).
        self.units.temp.trace_add("write", lambda *_: self._on_units_changed())
        self.units.alt.trace_add("write", lambda *_: self._on_units_changed())
        self.units.press.trace_add("write", lambda *_: self._on_units_changed())

        self._refresh()

    def _build_root(self):
        self.root.title("HAB Ground Monitor")
        self.root.configure(bg=self._theme.bg)

        # Start borderless + maximized, but allow switching to a normal resizable window.
        self._borderless = True
        self.root.overrideredirect(True)
        self.root.state("zoomed")
        self.root.minsize(980, 620)

        self.pack(fill="both", expand=True)

        self._drag = {"x": 0, "y": 0}
        self.root.bind("<Map>", self._on_map_restore)

    def _build_layout(self):
        # Top bar
        self.top = tk.Frame(self, bg=self._theme.bg, height=48)
        self.top.pack(fill="x")

        self.top_left = tk.Frame(self.top, bg=self._theme.bg)
        self.top_left.pack(side="left", padx=14)

        self.app_title = tk.Label(
            self.top_left,
            text="HAB Ground Monitor (SIM)",
            bg=self._theme.bg,
            fg=self._theme.text,
            font=("Segoe UI Semibold", 12),
        )
        self.app_title.pack(side="left")

        # Drag window by top bar
        for w in (self.top, self.top_left, self.app_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)

        self.top_right = tk.Frame(self.top, bg=self._theme.bg)
        self.top_right.pack(side="right", padx=10)

        # Dark-only app: 3 symbol buttons (styled like web pills)
        self.btn_min = tk.Label(self.top_right, text="—", cursor="hand2", padx=12, pady=7)
        self.btn_mode = tk.Label(self.top_right, text="⛶", cursor="hand2", padx=12, pady=7)
        self.btn_close = tk.Label(self.top_right, text="×", cursor="hand2", padx=12, pady=7)
        self.btn_min.pack(side="left", padx=6)
        self.btn_mode.pack(side="left", padx=6)
        self.btn_close.pack(side="left", padx=6)

        self.btn_close.bind("<Button-1>", lambda _e: self.root.destroy())
        self.btn_min.bind("<Button-1>", lambda _e: self._minimize())
        self.btn_mode.bind("<Button-1>", lambda _e: self._toggle_screen_mode())

        # Main split: sidebar + content
        self.main = tk.Frame(self, bg=self._theme.bg)
        self.main.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(self.main, bg=self._theme.surface_2, width=270)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = tk.Frame(self.main, bg=self._theme.bg)
        self.content.pack(side="left", fill="both", expand=True)

        # Sidebar nav (no "Navigation" word)
        self.nav_title = None
        tk.Frame(self.sidebar, height=10, bg=self._theme.surface_2).pack(fill="x", pady=(10, 0))

        self.nav_dash = tk.Label(self.sidebar, text="\u25C6  Dashboard", cursor="hand2", padx=14, pady=10, anchor="w")
        self.nav_graph = tk.Label(self.sidebar, text="\u25B2  Graphs", cursor="hand2", padx=14, pady=10, anchor="w")
        self.nav_credits = tk.Label(self.sidebar, text="\u2605  Credits", cursor="hand2", padx=14, pady=10, anchor="w")
        self.nav_dash.pack(fill="x", padx=10, pady=4)
        self.nav_graph.pack(fill="x", padx=10, pady=4)
        self.nav_credits.pack(fill="x", padx=10, pady=4)

        self.nav_dash.bind("<Button-1>", lambda _e: self._show("dash"))
        self.nav_graph.bind("<Button-1>", lambda _e: self._show("graphs"))
        self.nav_credits.bind("<Button-1>", lambda _e: self._show("credits"))

        # Units controls
        tk.Frame(self.sidebar, height=1, bg=self._theme.border).pack(fill="x", padx=16, pady=14)
        self.units_title = tk.Label(self.sidebar, text="Units", bg=self._theme.surface_2, fg=self._theme.text_dim, font=("Segoe UI Semibold", 10))
        self.units_title.pack(anchor="w", padx=16, pady=(0, 10))

        self.seg_temp = Segmented(self.sidebar, self._theme, "Temp", self.units.temp, ["C", "F"])
        self.seg_alt = Segmented(self.sidebar, self._theme, "Alt", self.units.alt, ["m", "ft"])
        self.seg_pr = Segmented(self.sidebar, self._theme, "Press", self.units.press, ["hPa", "inHg"])
        for s in (self.seg_temp, self.seg_alt, self.seg_pr):
            s.pack(anchor="w", padx=16, pady=8)

        # Status
        tk.Frame(self.sidebar, height=1, bg=self._theme.border).pack(fill="x", padx=16, pady=14)
        self.status = tk.Label(self.sidebar, text="Waiting for data…", bg=self._theme.surface_2, fg=self._theme.text_dim, font=("Segoe UI", 9))
        self.status.pack(anchor="w", padx=16, pady=(0, 16))

        # Pages
        self.pages: dict[str, tk.Frame] = {}
        self.pages["dash"] = DashboardPage(self.content, self._theme, self.units)
        self.pages["graphs"] = GraphsPage(self.content, self._theme, self.units)
        self.pages["credits"] = CreditsPage(self.content, self._theme)
        for p in self.pages.values():
            p.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._current = ""
        self._show("dash")

    def _start_drag(self, e):
        self._drag["x"] = e.x
        self._drag["y"] = e.y

    def _do_drag(self, e):
        # When maximized/zoomed, dragging doesn't make sense; restore first
        if self.root.state() == "zoomed":
            self.root.state("normal")
        x = self.root.winfo_x() + (e.x - self._drag["x"])
        y = self.root.winfo_y() + (e.y - self._drag["y"])
        self.root.geometry(f"+{x}+{y}")

    def _minimize(self):
        # Tk doesn't allow iconify() while override-redirect is set.
        self.root.overrideredirect(False)
        self.root.iconify()

    def _on_map_restore(self, _e):
        # When restored from taskbar, re-apply borderless mode.
        try:
            if self._borderless and not self.root.overrideredirect():
                self.root.overrideredirect(True)
                self.root.state("zoomed")
        except Exception:
            pass

    def _toggle_screen_mode(self):
        # One button toggles: borderless fullscreen <-> resizable window
        self._borderless = not self._borderless
        if self._borderless:
            self.root.overrideredirect(True)
            self.root.state("zoomed")
        else:
            self.root.overrideredirect(False)
            self.root.state("normal")
            # A nice default size; user can resize.
            self.root.geometry("1200x760")

    def _apply_theme(self, theme: Theme):
        self._theme = theme
        self.root.configure(bg=theme.bg)
        self.configure(bg=theme.bg)
        self.top.configure(bg=theme.bg)
        self.top_left.configure(bg=theme.bg)
        self.top_right.configure(bg=theme.bg)
        self.app_title.configure(bg=theme.bg, fg=theme.text)

        # Top buttons
        for b, bg, fg, bd in [
            (self.btn_min, theme.surface_2, theme.text, theme.border),
            (self.btn_mode, theme.surface_2, theme.text, theme.border),
            (self.btn_close, theme.accent_red, "#ffffff", theme.accent_red),
        ]:
            b.configure(bg=bg, fg=fg, font=("Segoe UI Semibold", 9), bd=1, relief="solid")
            b.configure(highlightthickness=0)
            b.configure(borderwidth=1)
            b.configure(highlightbackground=bd)

        # Dark-only button styling
        btn_bg = _mix(theme.surface_2, "#ffffff", 0.06)
        btn_fg = theme.text
        btn_bd = _mix(theme.border, "#ffffff", 0.10)
        self.btn_min.configure(bg=btn_bg, fg=btn_fg, highlightbackground=btn_bd, font=("Segoe UI Semibold", 11))
        self.btn_mode.configure(bg=btn_bg, fg=btn_fg, highlightbackground=btn_bd, font=("Segoe UI Semibold", 11))
        self.btn_close.configure(font=("Segoe UI Semibold", 12))

        self.main.configure(bg=theme.bg)
        self.sidebar.configure(bg=theme.surface_2)
        self.content.configure(bg=theme.bg)

        # nav_title removed
        self.units_title.configure(bg=theme.surface_2, fg=theme.text_dim)
        self.status.configure(bg=theme.surface_2, fg=theme.text_dim)

        for nav in (self.nav_dash, self.nav_graph, self.nav_credits):
            nav.configure(font=("Segoe UI Semibold", 10))

        self.seg_temp.set_theme(theme)
        self.seg_alt.set_theme(theme)
        self.seg_pr.set_theme(theme)

        for p in self.pages.values():
            if hasattr(p, "set_theme"):
                p.set_theme(theme)

        self._apply_nav_state()

    def _apply_nav_state(self):
        t = self._theme
        def style(btn: tk.Label, active: bool):
            btn.configure(
                bg=_mix(t.accent_blue, "#000000", 0.25) if active else t.surface_2,
                fg="#ffffff" if active else t.text,
                bd=1,
                relief="solid",
                highlightthickness=0,
                borderwidth=1,
            )
            btn.configure(highlightbackground=t.accent_blue if active else t.border)
            btn.configure(pady=12)

        style(self.nav_dash, self._current == "dash")
        style(self.nav_graph, self._current == "graphs")
        style(self.nav_credits, self._current == "credits")

    def _show(self, which: str):
        if which not in self.pages:
            return
        self._current = which
        self.pages[which].tkraise()
        self._apply_nav_state()
        # Force a full redraw once when entering graphs page.
        if which == "graphs":
            p = self.pages.get("graphs")
            if p and hasattr(p, "redraw_all"):
                p.redraw_all()

    def _on_units_changed(self):
        p = self.pages.get("graphs")
        if p and hasattr(p, "on_units_changed"):
            p.on_units_changed()

    def _refresh(self):
        with self.lock:
            snap = dict(self.data)

        ts = snap.get("timestamp", "")
        ts_short = ts[11:19] if isinstance(ts, str) and len(ts) >= 19 else ""

        # Animate status dot (text-based, no emojis)
        self._tick_anim = (self._tick_anim + 1) % 4
        dots = "." * (self._tick_anim + 1)
        if ts_short:
            self.status.configure(text=f"Live update {dots}   {ts_short}")
        else:
            self.status.configure(text=f"Waiting for data{dots}")

        # Dashboard
        dash: DashboardPage = self.pages["dash"]  # type: ignore[assignment]
        dash.update_values(snap)

        # Graphs (raw units; conversion is handled on dashboard; graphs keep physical units)
        graphs: GraphsPage = self.pages["graphs"]  # type: ignore[assignment]
        graphs.push(
            ts_short or "",
            snap.get("altitude_baro_m"),
            snap.get("temperature_c"),
            snap.get("pressure_hpa"),
            snap.get("humidity_pct"),
        )

        # Redraw graphs in a lightweight way to avoid UI lag:
        # draw one graph per tick (round-robin).
        if self._current == "graphs":
            graphs.redraw_step(self._tick_anim)

        self.root.after(1000, self._refresh)


# =============================================================================
# Public entry point used by main.py (keep signature stable)
# =============================================================================

class BalloonDashboard:
    """
    Backwards-compatible entry point used by main.py.
    Creates the modern multi-page UI while keeping the same constructor.
    """

    def __init__(self, root: tk.Tk, shared_data: dict, data_lock):
        self._app = _AppShell(root, shared_data, data_lock)
