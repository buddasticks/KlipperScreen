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

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_start(14)
        root.set_margin_end(14)
        root.set_margin_top(14)
        root.set_margin_bottom(14)

        title = Gtk.Label(label="TOOL OFFSET DASHBOARD")
        title.get_style_context().add_class("title")
        title.set_xalign(0)

        root.pack_start(title, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

        for tool in self.tools.keys():
            row.pack_start(self.build_tool_tile(tool), False, False, 0)

        scroll.add(row)

        root.pack_start(scroll, True, True, 0)

        apply_btn = Gtk.Button(label="Apply Changes")
        apply_btn.connect("clicked", self.on_apply)

        root.pack_start(apply_btn, False, False, 10)

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
        tile.get_style_context().add_class("card")
        tile.set_size_request(260, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)

        header = Gtk.Label(label=tool)
        header.set_xalign(0)
        header.get_style_context().add_class("title")

        box.pack_start(header, False, False, 0)

        box.pack_start(self.axis_row(tool, "x", data["x"]), False, False, 0)
        box.pack_start(self.axis_row(tool, "y", data["y"]), False, False, 0)
        box.pack_start(self.axis_row(tool, "z", data["z"]), False, False, 0)

        tile.add(box)
        return tile

    # ------------------------------------------------------------
    # AXIS ROW
    # ------------------------------------------------------------

    def axis_row(self, tool, axis, value):

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        label = Gtk.Label(label=axis.upper())
        label.set_xalign(0)

        btn = Gtk.Button(label=f"{value:.3f}")
        btn.set_size_request(-1, 50)
        btn.get_style_context().add_class("pill")

        self.values.setdefault(tool, {})[axis] = value
        self.buttons.setdefault(tool, {})[axis] = btn

        btn.connect("clicked", lambda _, t=tool, a=axis: self.open_numpad(t, a))

        row.pack_start(label, False, False, 0)
        row.pack_start(btn, True, True, 0)

        return row

    # ------------------------------------------------------------
    # NUMPAD (FIXED GTK3 SAFE)
    # ------------------------------------------------------------

    def open_numpad(self, tool, axis):

        win = Gtk.Window(title=f"{tool} {axis}")
        win.set_default_size(420, 520)
        win.set_modal(True)
        win.set_transient_for(self._screen)
        win.set_position(Gtk.WindowPosition.CENTER)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_start(14)
        root.set_margin_end(14)
        root.set_margin_top(14)
        root.set_margin_bottom(14)

        header = Gtk.Label(label=f"{tool} - Axis {axis.upper()}")
        header.get_style_context().add_class("title")
        header.set_xalign(0)
        root.pack_start(header, False, False, 0)

        # DISPLAY (NO set_xalign — GTK3 SAFE)
        entry = Gtk.Entry()
        entry.set_text(str(self.values[tool][axis]))
        entry.set_editable(False)
        root.pack_start(entry, False, False, 8)

        grid = Gtk.Grid()
        grid.set_row_spacing(8)
        grid.set_column_spacing(8)

        keys = ["7","8","9","4","5","6","1","2","3","0",".","-"]

        def add(c):
            entry.set_text(entry.get_text() + c)

        for i, k in enumerate(keys):
            b = Gtk.Button(label=k)
            b.set_size_request(90, 60)
            b.connect("clicked", lambda _, c=k: add(c))
            grid.attach(b, i % 3, i // 3, 1, 1)

        root.pack_start(grid, True, True, 8)

        action = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        def back(_):
            entry.set_text(entry.get_text()[:-1])

        def clear(_):
            entry.set_text("")

        def ok(_):
            try:
                val = float(entry.get_text())
            except:
                return

            self.values[tool][axis] = val
            self.buttons[tool][axis].set_label(f"{val:.3f}")
            win.destroy()

        back_btn = Gtk.Button(label="⌫")
        back_btn.set_size_request(120, 50)
        back_btn.connect("clicked", back)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.set_size_request(120, 50)
        clear_btn.connect("clicked", clear)

        ok_btn = Gtk.Button(label="OK")
        ok_btn.set_size_request(120, 50)
        ok_btn.connect("clicked", ok)

        action.pack_start(back_btn, True, True, 0)
        action.pack_start(clear_btn, True, True, 0)
        action.pack_start(ok_btn, True, True, 0)

        root.pack_start(action, False, False, 10)

        win.add(root)
        win.show_all()

    # ------------------------------------------------------------
    # APPLY
    # ------------------------------------------------------------

    def on_apply(self, button):

        for tool, axes in self.values.items():

            path = os.path.join(TOOL_CFG_PATH, f"{tool}.cfg")

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
                    out.append(f"gcode_x_offset: {data['x']}\n")
                    continue
                if "gcode_y_offset" in s:
                    out.append(f"gcode_y_offset: {data['y']}\n")
                    continue
                if "gcode_z_offset" in s:
                    out.append(f"gcode_z_offset: {data['z']}\n")
                    continue

            out.append(line)

        with open(path, "w") as f:
            f.writelines(out)

    # ------------------------------------------------------------
    # CSS
    # ------------------------------------------------------------

    def apply_css(self):

        css = b"""
        .card {
            background-color: #20242a;
            border-radius: 14px;
            border: 1px solid #2e3440;
        }

        .title {
            font-size: 18px;
            font-weight: bold;
            color: #eceff4;
        }

        .pill {
            border-radius: 12px;
            background-color: #2e3440;
            color: #eceff4;
        }

        button {
            border-radius: 10px;
        }
        """

        provider = Gtk.CssProvider()
        provider.load_from_data(css)

        Gtk.StyleContext.add_provider_for_screen(
            self._screen.get_screen(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
