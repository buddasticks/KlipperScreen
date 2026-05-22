import gi
import os
import re

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.screen_panel import ScreenPanel


TOOL_CFG_PATH = "/home/biqu/printer_data/config/toolchanger/tools"


class Panel(ScreenPanel):

    def __init__(self, screen, title):
        super().__init__(screen, title)

        self.tools = {}
        self.values = {}
        self.buttons = {}

        self.load_tools()
        self.build_ui()

    # ------------------------------------------------------------
    # LOAD + SORT
    # ------------------------------------------------------------

    def load_tools(self):

        self.tools = {}

        try:
            files = os.listdir(TOOL_CFG_PATH)
        except Exception as e:
            print(f"[tool_offsets] cannot read path: {e}")
            return

        tool_list = []

        for file in files:

            if not file.endswith(".cfg"):
                continue

            tool_name = file.replace(".cfg", "")
            path = os.path.join(TOOL_CFG_PATH, file)

            data = self.parse_tool_file(path, tool_name)

            if data:
                tool_list.append((tool_name, data))

        def sort_key(item):
            m = re.search(r"(\d+)", item[0])
            return int(m.group(1)) if m else 9999

        tool_list.sort(key=sort_key)

        self.tools = {name: data for name, data in tool_list}

    # ------------------------------------------------------------
    # PARSE
    # ------------------------------------------------------------

    def parse_tool_file(self, path, tool_name):

        try:
            with open(path, "r") as f:
                text = f.read()
        except:
            return None

        section_pattern = rf"^\[tool\s+{re.escape(tool_name)}\]\s*(.*?)(?=^\[|\Z)"
        match = re.search(section_pattern, text, re.S | re.M | re.I)

        if not match:
            return None

        block = match.group(1)

        return {
            "x": self.extract(block, "gcode_x_offset"),
            "y": self.extract(block, "gcode_y_offset"),
            "z": self.extract(block, "gcode_z_offset"),
        }

    def extract(self, text, key):
        m = re.search(rf"{key}\s*:\s*(-?\d+\.?\d*)", text)
        return float(m.group(1)) if m else 0.0

    # ------------------------------------------------------------
    # UI ROOT
    # ------------------------------------------------------------

    def build_ui(self):

        self.values = {}
        self.buttons = {}

        self.apply_css()

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )
        root.get_style_context().add_class("to-root")

        root.set_margin_start(14)
        root.set_margin_end(14)
        root.set_margin_top(14)
        root.set_margin_bottom(14)

        title = Gtk.Label(label="TOOL OFFSET DASHBOARD")
        title.get_style_context().add_class("to-dashboard-title")
        title.set_xalign(0)

        root.pack_start(title, False, False, 0)

        # --------------------------------------------------------
        # SCROLL AREA
        # --------------------------------------------------------

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.AUTOMATIC
        )

        scroll.set_vexpand(True)

        grid = Gtk.Grid()
        grid.set_row_spacing(14)
        grid.set_column_spacing(15)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)

        for i, tool in enumerate(self.tools.keys()):

            tile = self.build_tool_tile(tool)

            grid.attach(tile, i, 0, 1, 1)

        scroll.add(grid)

        root.pack_start(scroll, True, True, 0)

        # --------------------------------------------------------
        # FIXED BOTTOM BUTTON
        # --------------------------------------------------------

        apply_btn = Gtk.Button(label="Apply Changes")
        apply_btn.set_size_request(-1, 60)
        apply_btn.get_style_context().add_class("to-apply")

        apply_btn.connect("clicked", self.on_apply)

        root.pack_end(apply_btn, False, False, 0)

        self.content.add(root)
        self.content.show_all()

    # ------------------------------------------------------------
    # TOOL TILE
    # ------------------------------------------------------------

    def build_tool_tile(self, tool):

        data = self.tools.get(tool, {"x": 0, "y": 0, "z": 0})

        self.values.setdefault(tool, data.copy())
        self.buttons.setdefault(tool, {})

        tile = Gtk.EventBox()
        tile.get_style_context().add_class("to-card")

        tile.set_size_request(185, -1)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10
        )

        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)

        header = Gtk.Label(label=tool)
        header.set_xalign(0)
        header.get_style_context().add_class("to-tool-title")

        box.pack_start(header, False, False, 0)

        box.pack_start(
            self.axis_row(tool, "x", data["x"]),
            False,
            False,
            0
        )

        box.pack_start(
            self.axis_row(tool, "y", data["y"]),
            False,
            False,
            0
        )

        box.pack_start(
            self.axis_row(tool, "z", data["z"]),
            False,
            False,
            0
        )

        tile.add(box)

        return tile

    # ------------------------------------------------------------
    # AXIS ROW
    # ------------------------------------------------------------

    def axis_row(self, tool, axis, value):

        row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )

        label = Gtk.Label(label=axis.upper())
        label.set_xalign(0)
        label.get_style_context().add_class("to-axis-label")

        btn = Gtk.Button(label=f"{value:.3f}")
        btn.set_size_request(-1, 50)
        btn.get_style_context().add_class("to-pill")

        self.values.setdefault(tool, {})[axis] = value
        self.buttons.setdefault(tool, {})[axis] = btn

        btn.connect(
            "clicked",
            lambda _, t=tool, a=axis: self.open_numpad(t, a)
        )

        row.pack_start(label, False, False, 0)
        row.pack_start(btn, True, True, 0)

        return row

    # ------------------------------------------------------------
    # NUMPAD
    # ------------------------------------------------------------

    def open_numpad(self, tool, axis):

        win = Gtk.Window(title=f"{tool} {axis}")

        win.set_default_size(420, 520)

        win.set_modal(True)
        win.set_transient_for(self._screen)

        win.set_position(Gtk.WindowPosition.CENTER)

        win.get_style_context().add_class("to-numpad-window")

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16
        )

        root.set_margin_start(20)
        root.set_margin_end(20)
        root.set_margin_top(20)
        root.set_margin_bottom(20)

        header = Gtk.Label(
            label=f"{tool} - Axis {axis.upper()}"
        )

        header.get_style_context().add_class("to-numpad-header")
        header.set_xalign(0)

        root.pack_start(header, False, False, 0)

        entry = Gtk.Entry()

        entry.set_text(str(self.values[tool][axis]))
        entry.set_editable(False)
        entry.set_can_focus(False)
        entry.set_alignment(0.5)

        entry.get_style_context().add_class("to-numpad-entry")

        root.pack_start(entry, False, False, 12)

        grid = Gtk.Grid()

        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(True)

        keys = [
            "7", "8", "9",
            "4", "5", "6",
            "1", "2", "3",
            "0", ".", "-"
        ]

        def add(c):
            entry.set_text(entry.get_text() + c)

        for i, k in enumerate(keys):

            b = Gtk.Button(label=k)

            b.set_size_request(0, 70)

            b.get_style_context().add_class("to-numpad-key")

            b.connect(
                "clicked",
                lambda _, c=k: add(c)
            )

            grid.attach(
                b,
                i % 3,
                i // 3,
                1,
                1
            )

        root.pack_start(grid, True, True, 0)

        action = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )

        def back(_):
            entry.set_text(entry.get_text()[:-1])

        def clear(_):
            entry.set_text("")

        def cancel(_):
            win.destroy()

        def ok(_):

            try:
                val = float(entry.get_text())
            except:
                return

            self.values[tool][axis] = val

            self.buttons[tool][axis].set_label(
                f"{val:.3f}"
            )

            win.destroy()

        back_btn = Gtk.Button(label="BS")
        back_btn.set_size_request(0, 60)
        back_btn.get_style_context().add_class("to-numpad-action")
        back_btn.connect("clicked", back)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.set_size_request(0, 60)
        clear_btn.get_style_context().add_class("to-numpad-action")
        clear_btn.connect("clicked", clear)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.set_size_request(0, 60)
        cancel_btn.get_style_context().add_class("to-numpad-action")
        cancel_btn.connect("clicked", cancel)

        ok_btn = Gtk.Button(label="OK")
        ok_btn.set_size_request(0, 60)
        ok_btn.get_style_context().add_class("to-numpad-action")
        ok_btn.get_style_context().add_class("to-numpad-ok")
        ok_btn.connect("clicked", ok)

        action.pack_start(back_btn, True, True, 0)
        action.pack_start(clear_btn, True, True, 0)
        action.pack_start(cancel_btn, True, True, 0)
        action.pack_start(ok_btn, True, True, 0)

        root.pack_start(action, False, False, 0)

        win.add(root)
        win.show_all()

    # ------------------------------------------------------------
    # APPLY
    # ------------------------------------------------------------

    def on_apply(self, button):

        for tool, axes in self.values.items():

            path = os.path.join(
                TOOL_CFG_PATH,
                f"{tool}.cfg"
            )

            if os.path.exists(path):
                self.write_tool_file(path, tool, axes)

        self.load_tools()

    def write_tool_file(self, path, tool_name, data):

        with open(path, "r") as f:
            lines = f.readlines()

        section = f"[tool {tool_name}]"

        in_section = False
        out = []

        for line in lines:

            s = line.strip()

            if s.lower() == section.lower():
                in_section = True
                out.append(line)
                continue

            if in_section and s.startswith("[") and s.endswith("]"):
                in_section = False

            if in_section:

                if "gcode_x_offset" in s:
                    out.append(
                        f"gcode_x_offset: {data['x']}\n"
                    )
                    continue

                if "gcode_y_offset" in s:
                    out.append(
                        f"gcode_y_offset: {data['y']}\n"
                    )
                    continue

                if "gcode_z_offset" in s:
                    out.append(
                        f"gcode_z_offset: {data['z']}\n"
                    )
                    continue

            out.append(line)

        with open(path, "w") as f:
            f.writelines(out)

    # ------------------------------------------------------------
    # CSS
    # ------------------------------------------------------------

    def apply_css(self):

        css = b"""
        .to-root {
            background-color: #1a2035;
        }

        .to-dashboard-title {
            font-size: 20px;
            font-weight: 800;
            color: #ffffff;
        }

        .to-card {
            background-color: #242d48;
            border-radius: 14px;
            border: 2px solid #2a3a5c;
        }

        .to-tool-title {
            font-size: 18px;
            font-weight: 800;
            color: #00d4ff;
        }

        .to-axis-label {
            font-size: 16px;
            font-weight: 700;
            color: #ffffff;
        }

        .to-pill {
            border-radius: 10px;
            background-color: #252f4a;
            color: #ffffff;
            border: 1px solid #3a4a6e;
            font-size: 14px;
            font-weight: 700;
        }

        .to-apply {
            background: #006080;
            color: #ffffff;
            border-radius: 10px;
            border: 2px solid #00d4ff;
            font-size: 14px;
            font-weight: 800;
        }

        .to-numpad-window {
            background-color: #1a2035;
        }

        .to-numpad-header {
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
        }

        .to-numpad-entry {
            font-size: 32px;
            font-weight: 800;
            color: #ffffff;
            background-color: #242d48;
            border-radius: 12px;
            border: 2px solid #00d4ff;
            padding: 8px;
        }

        .to-numpad-key {
            font-size: 24px;
            font-weight: 700;
            background-color: #2a3a5c;
            color: #ffffff;
            border-radius: 12px;
            border: 1px solid #3a4a6e;
        }

        .to-numpad-key:active {
            background-color: #00a8cc;
        }

        .to-numpad-action {
            font-size: 16px;
            font-weight: 700;
            background-color: #252f4a;
            color: #ffffff;
            border-radius: 12px;
            border: 1px solid #3a4a6e;
        }

        .to-numpad-action:active {
            background-color: #3a4a6e;
        }

        .to-numpad-ok {
            background-color: #006080;
            color: #ffffff;
            border: 2px solid #00d4ff;
        }

        .to-numpad-ok:active {
            background-color: #0088aa;
        }
        """

        provider = Gtk.CssProvider()

        provider.load_from_data(css)

        Gtk.StyleContext.add_provider_for_screen(
            self._screen.get_screen(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
