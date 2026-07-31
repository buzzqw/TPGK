"""Symbolic icon helpers for the TPGK UI.

GTK stock icons (Gtk.STOCK_*) have been deprecated since GTK 3.10 and render as
low-resolution, visually dated glyphs. This module centralizes construction of
modern symbolic Gtk.Image icons, plus two custom-drawn split-view icons that
no icon theme reliably ships under a single portable name.
"""
import cairo
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


ICON_SIZE = 20  # a bit larger than the GTK default 16px for readability


def symbolic_image(icon_name: str, pixel_size: int = ICON_SIZE) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
    image.set_pixel_size(pixel_size)
    return image


def _symbolic_color() -> Gdk.RGBA:
    # get_color() on a freshly-created, unparented widget is unreliable (it can
    # report white regardless of the active theme, making icons invisible on
    # light backgrounds). The theme's named "theme_fg_color" is a plain color
    # table lookup, so it resolves correctly even before the widget is realized.
    ctx = Gtk.Image().get_style_context()
    ok, color = ctx.lookup_color("theme_fg_color")
    if ok:
        return color
    return ctx.get_color(Gtk.StateFlags.NORMAL)


def split_view_image(vertical: bool, size: int = ICON_SIZE) -> Gtk.Image:
    """A small two-pane rectangle icon.

    vertical=True draws a vertical divider (left/right panes) which matches
    TPGK's "Split Vertical" mode; vertical=False draws a horizontal divider
    (top/bottom panes) for "Split Horizontal".
    """
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    color = _symbolic_color()
    cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
    cr.set_line_width(1.6)

    margin = 2.0
    x0, y0 = margin, margin
    x1, y1 = size - margin, size - margin

    cr.rectangle(x0, y0, x1 - x0, y1 - y0)
    cr.stroke()

    if vertical:
        cr.move_to(size / 2, y0)
        cr.line_to(size / 2, y1)
    else:
        cr.move_to(x0, size / 2)
        cr.line_to(x1, size / 2)
    cr.stroke()

    pixbuf = Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)
    image = Gtk.Image.new_from_pixbuf(pixbuf)
    return image


def icon_button(icon_name: str = None, label: str = None, tooltip: str = None,
                 pixel_size: int = ICON_SIZE, custom_image: Gtk.Image = None) -> Gtk.Button:
    """Build a flat, symbolic-icon button suitable for a Gtk.HeaderBar.

    Sized generously (36x36 minimum) so it stays an easy, comfortable click
    target for users with reduced vision or fine-motor precision.
    """
    btn = Gtk.Button()
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_size_request(36, 36)
    image = custom_image if custom_image is not None else symbolic_image(icon_name, pixel_size)
    if label:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.pack_start(image, False, False, 0)
        box.pack_start(Gtk.Label(label=label), False, False, 0)
        btn.add(box)
    else:
        btn.add(image)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn
