#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ToolchangerPanel rewritten from scratch with a cleaner architecture, safer polling,
and stricter separation between bg I/O and GTK UI updates.

Updated to use KlipperScreen/Moonraker's shared Spoolman proxy instead of a
panel-local Spoolman URL. This removes the broken custom Spoolman IP handling
and reuses the same configured Spoolman connection that the built-in
KlipperScreen Spoolman panel uses.

Also updated to auto-detect tool count from Moonraker's toolchanger status
(tool_numbers / tool_names) and remove the manual tool count setting.
"""

from __future__ import annotations

import cairo
import gi
import json
import math
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional



gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

CONFIG_PATH = os.path.expanduser("~/.toolchanger_settings.json")
POLL_INTERVAL_SECONDS = 1.0



# -----------------------------------------------------------------------------
# Theme helpers
# -----------------------------------------------------------------------------

def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_hex(color: str, fallback: str = "#333b54") -> str:
    if not color:
        return fallback
    raw = color.strip().lstrip("#")
    if len(raw) != 6:
        return fallback
    try:
        int(raw, 16)
    except ValueError:
        return fallback
    return f"#{raw.lower()}"


def hex_to_rgb01(color: str) -> tuple[float, float, float]:
    color = normalize_hex(color)
    raw = color.lstrip("#")
    return (
        int(raw[0:2], 16) / 255.0,
        int(raw[2:4], 16) / 255.0,
        int(raw[4:6], 16) / 255.0,
    )


def rgb01_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(clamp01(r) * 255),
        int(clamp01(g) * 255),
        int(clamp01(b) * 255),
    )


def adjust_color(color: str, factor: float) -> str:
    r, g, b = hex_to_rgb01(color)
    return rgb01_to_hex(r * factor, g * factor, b * factor)


def mix_colors(a: str, b: str, t: float) -> str:
    t = clamp01(t)
    ar, ag, ab = hex_to_rgb01(a)
    br, bg, bb = hex_to_rgb01(b)
    return rgb01_to_hex(
        ar + (br - ar) * t,
        ag + (bg - ag) * t,
        ab + (bb - ab) * t,
    )


def luminance(color: str) -> float:
    r, g, b = hex_to_rgb01(color)
    return 0.299 * r + 0.587 * g + 0.114 * b


def hex_to_gdk(color: str) -> Gdk.RGBA:
    r, g, b = hex_to_rgb01(color)
    return Gdk.RGBA(r, g, b, 1.0)


def gdk_to_hex(rgba: Gdk.RGBA) -> str:
    return rgb01_to_hex(rgba.red, rgba.green, rgba.blue)


BASE_THEMES: Dict[str, Dict[str, str]] = {
    "Ocean": {
        "bg": "#1a2035",
        "card": "#242d48",
        "accent": "#00d4ff",
        "text": "#ffffff",
        "bar_bg": "#151c30",
        "btn_bg": "#252f4a",
    },
    "Ember": {
        "bg": "#1f1208",
        "card": "#2e1a0a",
        "accent": "#ff7722",
        "text": "#ffe8d0",
        "bar_bg": "#120c04",
        "btn_bg": "#2a1808",
    },
    "Stealth": {
        "bg": "#0d0d0d",
        "card": "#1a1a1a",
        "accent": "#cccccc",
        "text": "#ffffff",
        "bar_bg": "#080808",
        "btn_bg": "#1a1a1a",
    },
    "Neon": {
        "bg": "#0a001a",
        "card": "#130028",
        "accent": "#cc00ff",
        "text": "#f0d0ff",
        "bar_bg": "#06000e",
        "btn_bg": "#130028",
    },
    "Crimson": {
        "bg": "#1a0510",
        "card": "#2a0a18",
        "accent": "#ff2255",
        "text": "#ffd0da",
        "bar_bg": "#0e0208",
        "btn_bg": "#200810",
    },
    "Arctic": {
        "bg": "#0a1520",
        "card": "#0f2030",
        "accent": "#44ddaa",
        "text": "#d0fff0",
        "bar_bg": "#060f18",
        "btn_bg": "#0d1e2e",
    },
    "Sunset": {
        "bg": "#2a0f0f",
        "card": "#3a1a1a",
        "accent": "#ff8844",
        "text": "#ffe6d5",
        "bar_bg": "#1a0808",
        "btn_bg": "#3a1a1a",
    },
    "Forest": {
        "bg": "#0e1a12",
        "card": "#16261c",
        "accent": "#22cc66",
        "text": "#d8ffe8",
        "bar_bg": "#08120c",
        "btn_bg": "#16261c",
    },
    "Midnight Blue": {
        "bg": "#050a18",
        "card": "#0c1428",
        "accent": "#4488ff",
        "text": "#d6e4ff",
        "bar_bg": "#030612",
        "btn_bg": "#0c1428",
    },
}


def derive_theme_fields(base: Dict[str, str]) -> Dict[str, str]:
    bg = normalize_hex(base["bg"])
    card = normalize_hex(base["card"])
    accent = normalize_hex(base["accent"])
    text = normalize_hex(base["text"])
    bar_bg = normalize_hex(base["bar_bg"])
    btn_bg = normalize_hex(base["btn_bg"])

    return {
        "bg": bg,
        "card": card,
        "card_border": mix_colors(card, accent, 0.28),
        "accent": accent,
        "accent_dark": adjust_color(accent, 0.78),
        "btn_bg": btn_bg,
        "btn_bg2": mix_colors(btn_bg, accent, 0.12),
        "btn_border": mix_colors(btn_bg, accent, 0.35),
        "text": text,
        "bar_bg": bar_bg,
        "warn": "#ffb020",
        "danger": "#ff4d4f",
        "ok": "#12d67a",
        "muted": mix_colors(text, bg, 0.55),
    }


THEMES = {name: derive_theme_fields(values) for name, values in BASE_THEMES.items()}


def make_css(theme: Dict[str, str]) -> bytes:
    accent = theme["accent"]
    accent_dark = theme["accent_dark"]
    btn_text = "#001820" if luminance(accent) > 0.45 else theme["text"]

    css = f"""
.tc-root {{ background-color: {theme['bg']}; }}
.tc-card {{ background-color: {theme['card']}; border-radius: 14px; border: 2px solid {theme['card_border']}; }}
.tc-card-active {{ background-color: {theme['card']}; border-radius: 14px; border: 3px solid {accent}; }}
.tc-tool-label {{ color: {accent}; font-size: 18px; font-weight: 800; }}
.tc-mat-label {{ color: {theme['text']}; font-size: 16px; font-weight: 800; }}
.tc-mat-label-empty {{ color: {theme['text']}; font-size: 16px; font-weight: 800; }}
.tc-temp-label {{ color: {theme['text']}; font-size: 26px; font-weight: 800; padding: 4px; }}
.tc-bottom-bar {{ background-color: {theme['bar_bg']}; border-top: 1px solid {theme['card_border']}; }}
.tc-btn-global {{ background: {theme['btn_bg']}; color: {theme['text']}; border-radius: 8px; font-size: 12px; font-weight: 700; border: 1px solid {theme['btn_border']}; }}
.tc-btn-select {{ background: {accent_dark}; color: {btn_text}; border-radius: 8px; font-size: 12px; font-weight: 800; border: 1px solid {accent}; }}
.tc-badge-active {{ background-color: #003a20; color: #00ff88; border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px; border: 1px solid #00cc66; }}
.tc-badge-heating {{ background-color: #3f2700; color: #ffbf40; border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px; border: 1px solid #ffb020; }}
.tc-badge-parked {{ background-color: {theme['btn_bg']}; color: {theme['text']}; border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px; border: 1px solid {theme['btn_border']}; }}
.tc-badge-error {{ background-color: #3a0a0a; color: #ff4444; border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px; border: 1px solid #aa2222; }}
.tc-badge-changing {{ background-color: #002a4a; color: #44c8ff; border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px; border: 1px solid #44c8ff; }}
.tc-badge-pid {{ background-color: #3a123f; color: #ff8cff; border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px; border: 1px solid #ff8cff; }}
.tc-popup {{ background-color: {theme['card']}; border: 2px solid {accent}; border-radius: 15px; }}
.tc-popup-title {{ color: {theme['text']}; font-size: 24px; font-weight: 900; }}
.tc-popup-subtitle {{ color: {theme['muted']}; font-size: 11px; font-weight: 700; }}
.tc-popup-card {{ background-color: {mix_colors(theme['card'], theme['bg'], 0.20)}; border-radius: 14px; border: 1px solid {theme['card_border']}; }}
.tc-popup-card-active {{ background-color: {mix_colors(theme['card'], accent, 0.08)}; border-radius: 14px; border: 2px solid {accent}; }}
.tc-popup-card-title {{ color: {theme['text']}; font-size: 16px; font-weight: 900; }}
.tc-popup-card-sub {{ color: {theme['muted']}; font-size: 11px; font-weight: 700; }}
.tc-popup-card-temp {{ color: {accent}; font-size: 20px; font-weight: 900; }}
.tc-settings-meta {{ color: {theme['muted']}; font-size: 11px; font-weight: 700; }}
.tc-popup-flat-btn, .tc-popup-flat-btn:hover, .tc-popup-flat-btn:active, .tc-popup-flat-btn:checked {{ background: transparent; background-image: none; border: none; box-shadow: none; padding: 0; }}
"""
    return css.encode("utf-8")


# -----------------------------------------------------------------------------
# State models
# -----------------------------------------------------------------------------

@dataclass
class ToolState:
    index: int
    heater_name: str
    material: str = "EMPTY"
    color_hex: str = "#333b54"
    remaining_ratio: float = -1.0
    temperature: float = 0.0
    target: float = 0.0
    active: bool = False
    spool_id: Optional[int] = None
    reachable: bool = True
    spool_error: bool = False
    ktc_state: str = "unknown"

    @property
    def display_title(self) -> str:
        return f"T{self.index}"

    @property
    def is_heating(self) -> bool:
        return self.target > 0 and self.temperature + 5 < self.target

    @property
    def status_label(self) -> str:
        if not self.reachable:
            return "OFFLINE"
        if self.spool_error:
            return "ERROR"
        if self.ktc_state == "error":
            return "ERROR"
        if self.ktc_state == "pid_tuning":
            return "PID TUNE"
        if self.ktc_state == "active":
            return "ACTIVE"
        if self.ktc_state == "changing":
            return "CHANGING"
        if self.ktc_state == "docked":
            return "PARKED"
        if self.is_heating:
            return "HEATING"
        return "UNKNOWN"

    @property
    def status_css(self) -> str:
        if not self.reachable or self.spool_error:
            return "tc-badge-error"
        if self.ktc_state == "error":
            return "tc-badge-error"
        if self.ktc_state == "pid_tuning":
            return "tc-badge-pid"
        if self.ktc_state == "active":
            return "tc-badge-active"
        if self.ktc_state == "changing":
            return "tc-badge-changing"
        if self.ktc_state == "docked":
            return "tc-badge-parked"
        if self.is_heating:
            return "tc-badge-heating"
        return "tc-badge-parked"


@dataclass
class CardWidgets:
    frame: Gtk.Box
    badge: Gtk.Label
    temp: Gtk.Label
    mat: Gtk.Label
    spool_area: Gtk.DrawingArea


@dataclass
class RuntimeSnapshot:
    tools: List[ToolState]
    moonraker_ok: bool = True


# -----------------------------------------------------------------------------
# Utility UI builders
# -----------------------------------------------------------------------------

def popup_window(parent: Gtk.Window) -> Gtk.Window:
    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_decorated(False)
    win.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
    return win


def button(label: str, css_class: str, callback: Callable[..., Any]) -> Gtk.Button:
    b = Gtk.Button(label=label)
    b.get_style_context().add_class(css_class)
    b.connect("clicked", callback)
    return b


def box(orientation: Gtk.Orientation = Gtk.Orientation.VERTICAL, spacing: int = 0) -> Gtk.Box:
    return Gtk.Box(orientation=orientation, spacing=spacing)


# -----------------------------------------------------------------------------
# Main panel
# -----------------------------------------------------------------------------

class ToolchangerPanel:
    def __init__(self, screen: Gtk.Window, title: str):
        self._screen = screen
        self.title = "Tool Changer"
        self.menu = [title]

        self._poll_stop = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._command_queue: "queue.Queue[str]" = queue.Queue()
        self._command_thread: Optional[threading.Thread] = None
        self._active_popup: Optional[Gtk.Window] = None
        self._pid_tuning_tool_index: Optional[float] = None
        self._pid_tuning_started_at: Optional[float] = None

        self._css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        config = self._load_config()
        self.num_tools = 2
        self._theme_name = config.get("theme", "Ocean")
        self._custom = config.get("custom")
        self._theme = self._resolve_theme()
        self._apply_theme()

        self._tool_states: List[ToolState] = []
        self._card_widgets: Dict[int, CardWidgets] = {}

        self.content = self._build_root()
        self._rebuild_cards()
        self.content.show_all()

        self._start_command_worker()
        self._start_polling_worker()

    # ... content omitted for brevity ...
