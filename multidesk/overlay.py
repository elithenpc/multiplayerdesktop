"""Transparent, click-through X11 overlay for remote guest cursor labels."""
from __future__ import annotations

import threading


class CursorNameOverlay:
    """Draw guest names beside their real MPX cursors on the host desktop."""

    def __init__(self):
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="multidesk-cursor-overlay", daemon=True)
        self._window = None
        self._area = None
        self._labels: dict[str, tuple[str, int, int]] = {}
        self._lock = threading.RLock()
        self._error = None
        self._thread.start()
        if not self._ready.wait(8):
            raise RuntimeError("Cursor overlay did not initialise")
        if self._error:
            raise RuntimeError(self._error)

    def _run(self):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk, GLib
            import cairo

            screen = Gdk.Screen.get_default()
            visual = screen.get_rgba_visual()
            self._window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
            self._window.set_title("MultiDesk cursor names")
            self._window.set_decorated(False)
            self._window.set_app_paintable(True)
            if visual:
                self._window.set_visual(visual)
            self._window.set_keep_above(True)
            self._window.set_accept_focus(False)
            self._window.set_focus_on_map(False)
            self._window.set_skip_taskbar_hint(True)
            self._window.set_skip_pager_hint(True)
            self._window.set_type_hint(Gdk.WindowTypeHint.DOCK)
            self._window.set_default_size(screen.get_width(), screen.get_height())
            self._window.move(0, 0)
            self._area = Gtk.DrawingArea()
            self._area.connect("draw", self._draw)
            self._window.add(self._area)
            self._window.connect("realize", self._make_click_through)
            self._window.show_all()
            self._ready.set()
            Gtk.main()
        except Exception as exc:
            self._error = f"Could not initialise desktop cursor labels: {exc}"
            self._ready.set()

    def _make_click_through(self, widget):
        try:
            import cairo
            window = widget.get_window()
            if window and hasattr(window, "input_shape_combine_region"):
                window.input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass

    def _draw(self, widget, cr):
        import cairo
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        with self._lock:
            labels = list(self._labels.values())
        for name, x, y in labels:
            text = name[:32]
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(13)
            ext = cr.text_extents(text)
            tx, ty = x + 18, y + 22
            cr.set_source_rgba(0.02, 0.07, 0.14, 0.86)
            cr.rectangle(tx - 6, ty - 16, ext.width + 12, 25)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 1)
            cr.move_to(tx, ty)
            cr.show_text(text)
        return False

    def update_guest(self, guest_id: str, name: str, x: int, y: int):
        with self._lock:
            self._labels[guest_id] = (name, int(x), int(y))
        try:
            from gi.repository import GLib
            GLib.idle_add(self._area.queue_draw)
        except Exception:
            pass

    def remove_guest(self, guest_id: str):
        with self._lock:
            self._labels.pop(guest_id, None)
        try:
            from gi.repository import GLib
            GLib.idle_add(self._area.queue_draw)
        except Exception:
            pass
