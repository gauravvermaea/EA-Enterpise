"""eax screen (R3.1; owner, 13 Nov 2026: "can we have a menu driven command line like we used to have in turbo pascal?";
decided: `eax screen`, plain `eax` opens it, the classic look, the mouse too; "keep both kinds of menus"): a full-screen
text interface in the terminal.

  menu bar     the groups of help.txt (Start, Status, Backups, Updates, Test, Settings, Site, Developer, Help): F10 or
               Alt+letter opens one, the arrows move, Enter picks, Escape closes; the mouse works everywhere
  pull-down    the group's commands, each with its one line
  dialog       a command's options from help.txt: choices as lists, flags as tick boxes, values as fields; the whole
               command shown as it is filled; Run and Cancel
  dashboard    each container in its state's colour, the disks, refreshed every few seconds
  status line  F1 Help, F10 Menu, F5 Refresh, Alt+F5 User screen, Alt+X Exit
  output       a command that only prints runs in a window inside the screen; one that asks or follows (logs, a
               console, a restore) switches to the plain terminal and comes back with Enter (Turbo Pascal's Alt+F5)

Textual is fetched once into work/tools/pylib by uv (nothing installed elsewhere); without it (offline the first time,
piped, in a script, an old console, EAX_SCREEN=off) the numbered menu (eax menu, D636) opens instead. What it shows and
does without the screen is in screen_model.py."""

from __future__ import annotations

import os
import subprocess
import sys

from . import help as help_
from . import menu as menu_
from . import screen_model as sm
from .core import ROOT

TEXTUAL = "0.86.3"
PYLIB = ROOT / "work" / "tools" / "pylib"


def argv_for(line: list[str], form: str | None = None) -> list[str]:
    """The program and arguments that run an eax command in the form of eax that opened the screen."""
    form = os.environ.get("EAX_FORM", "") if form is None else form
    if form == "sh":
        return ["bash", str(ROOT / "eax.sh"), *line]
    if form == "ps1":
        return [os.environ.get("EAX_FORM_EXE") or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(ROOT / "eax.ps1"), *line]
    return [sys.executable, str(ROOT / "eaxpy.py"), *line]


def why_not(stdin_tty: bool | None = None, term: str | None = None) -> str:
    """Why the full screen cannot open here ("" when it can)."""
    if os.environ.get("EAX_SCREEN", "").lower() in ("off", "0", "no", "false"):
        return "EAX_SCREEN=off"
    if not (sys.stdin.isatty() and sys.stdout.isatty() if stdin_tty is None else stdin_tty):
        return "not a terminal (piped or in a script)"
    if (os.environ.get("TERM", "") if term is None else term) == "dumb":
        return "a terminal without colours or a cursor (TERM=dumb)"
    return ""


def load_textual(fetch=None) -> bool:
    """Textual importable, fetched once into work/tools/pylib with uv when it is not."""
    if str(PYLIB) not in sys.path:
        sys.path.insert(0, str(PYLIB))
    try:
        import textual  # noqa: F401
        return True
    except ImportError:
        pass
    uv = os.environ.get("EAX_UV") or str(ROOT / "work" / "tools" / ("uv.exe" if os.name == "nt" else "uv"))
    cmd = [uv, "pip", "install", "--quiet", "--target", str(PYLIB), "--python", sys.executable, f"textual=={TEXTUAL}"]
    print(f"First run of eax screen: fetching Textual {TEXTUAL} into work/tools/pylib (once)...", flush=True)
    try:
        code = (fetch or subprocess.call)(cmd)
    except OSError:
        code = 1
    if code != 0:
        return False
    import importlib
    importlib.invalidate_caches()
    try:
        import textual  # noqa: F401, F811
        return True
    except ImportError:
        return False


def build_app(form: str, windows: bool, how: str):
    """The Textual application (built here so importing this module never needs Textual)."""
    from rich.markup import escape
    from rich.text import Text
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button,
        Checkbox,
        DataTable,
        Input,
        Label,
        OptionList,
        RichLog,
        Select,
        Static,
    )
    from textual.widgets.option_list import Option

    groups = sm.menus(form, windows)

    class PullDown(ModalScreen):
        """A group's commands under its name on the menu bar."""
        BINDINGS = [Binding("escape", "dismiss(None)", "Close"), Binding("left", "move(-1)", show=False),
                    Binding("right", "move(1)", show=False)]

        def __init__(self, index: int) -> None:
            super().__init__(classes="pulldown-screen")
            self.index = index

        def compose(self) -> ComposeResult:
            g = groups[self.index]
            width = max(len(c["name"]) for c in g["commands"]) + 2
            opts = [Option(escape(f"{c['name']:<{width}} {c['summary']}"), id=c["name"]) for c in g["commands"]]
            box = OptionList(*opts, id="pulldown")
            box.styles.offset = (sum(len(x["short"]) + 3 for x in groups[:self.index]), 1)
            yield box

        def on_mount(self) -> None:
            self.query_one("#pulldown", OptionList).focus()

        def action_move(self, step: int) -> None:
            self.dismiss(("move", (self.index + step) % len(groups)))

        @on(OptionList.OptionSelected)
        def picked(self, event: OptionList.OptionSelected) -> None:
            self.dismiss(("run", next(c for c in groups[self.index]["commands"] if c["name"] == event.option.id)))

        def on_click(self, event) -> None:                # a click outside the list closes it
            if getattr(event, "widget", None) is self:
                self.dismiss(None)

    class Dialog(ModalScreen):
        """A command's options: lists, tick boxes and fields; the whole command shown as it is filled; Run or Cancel."""
        BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

        def __init__(self, cmd: dict) -> None:
            super().__init__()
            self.cmd, self.flds = cmd, sm.fields(cmd["args"])

        def compose(self) -> ComposeResult:
            with Vertical(id="dialog"):
                yield Label(Text(f" {self.cmd['name']} "), id="dialog-title")
                yield Static(Text(self.cmd["summary"]), classes="summary")
                with VerticalScroll(id="dialog-fields"):
                    for f in self.flds:
                        if f["kind"] == "flag":
                            yield Checkbox(escape(f["label"]), id=f["id"])
                        elif f["kind"] == "choice":
                            yield Label(Text(f["label"] + ("" if not f["optional"] else " (may be left out)")))
                            with Horizontal(classes="choice-row"):
                                yield Select([(c, c) for c in f["choices"]], id=f["id"], allow_blank=True, prompt="(none)")
                                yield Input(id=f"{f['id']}_typed", placeholder="or type it")
                        else:
                            yield Label(Text(f["label"] + (" (several: spaces between)" if f["many"] else "")
                                             + ("" if not f["optional"] else " (may be left out)")))
                            yield Input(id=f["id"])
                    if not self.flds:
                        yield Static("This command has no options.", classes="quiet")
                yield Static("", id="dialog-line")
                yield Static("", id="dialog-missing")
                with Horizontal(id="dialog-buttons"):
                    yield Button("Run", id="run", variant="primary")
                    yield Button("Cancel", id="cancel")

        def values(self) -> dict:
            out = {}
            for f in self.flds:
                v = self.query_one(f"#{f['id']}").value
                out[f["id"]] = "" if v is Select.BLANK else v
                if f["kind"] == "choice":
                    out[f"{f['id']}_typed"] = self.query_one(f"#{f['id']}_typed", Input).value
            return out

        def refresh_line(self) -> None:
            line, missing = sm.line_for(self.cmd["name"], self.flds, self.values())
            self.query_one("#dialog-line", Static).update(Text(f"Will run:  {sm.shown(line, how)}"))
            self.query_one("#dialog-missing", Static).update(Text(missing))
            self.query_one("#run", Button).disabled = bool(missing)

        def on_mount(self) -> None:
            self.refresh_line()

        @on(Input.Changed)
        @on(Checkbox.Changed)
        @on(Select.Changed)
        def changed(self) -> None:
            self.refresh_line()

        @on(Button.Pressed, "#cancel")
        def cancel(self) -> None:
            self.dismiss(None)

        @on(Button.Pressed, "#run")
        def run(self) -> None:
            line, missing = sm.line_for(self.cmd["name"], self.flds, self.values())
            if not missing:
                self.dismiss(line)

    class Output(ModalScreen):
        """A command's output, in a window inside the screen, as it comes."""
        BINDINGS = [Binding("escape", "dismiss(None)", "Close"), Binding("enter", "dismiss(None)", "Close", show=False)]

        def __init__(self, line: list[str]) -> None:
            super().__init__()
            self.line = line

        def compose(self) -> ComposeResult:
            with Vertical(id="output"):
                yield Label(Text(f" {sm.shown(self.line, how)} "), id="output-title")
                yield RichLog(id="output-log", wrap=True, markup=False, highlight=False)
                yield Static("Running...", id="output-state")
                yield Button("Close", id="close")

        def on_mount(self) -> None:
            self.go()

        @work(thread=True)
        def go(self) -> None:
            log = self.query_one("#output-log", RichLog)
            try:
                p = subprocess.Popen(argv_for(self.line, form), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
                for ln in p.stdout:
                    self.app.call_from_thread(log.write, ln.rstrip("\n"))
                code = p.wait()
            except OSError as exc:
                self.app.call_from_thread(log.write, f"Could not run it: {exc}")
                code = 1
            self.app.call_from_thread(self.query_one("#output-state", Static).update,
                                      "Done." if code == 0 else f"Ended with exit code {code}.")

        @on(Button.Pressed, "#close")
        def close(self) -> None:
            self.dismiss(None)

    class HelpWindow(ModalScreen):
        BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

        def compose(self) -> ComposeResult:
            with Vertical(id="output"):
                yield Label(" Help ", id="output-title")
                yield RichLog(id="output-log", wrap=True, markup=False, highlight=False)
                yield Button("Close", id="close")

        def on_mount(self) -> None:
            text, _ = help_.render(form, how, windows)
            log = self.query_one("#output-log", RichLog)
            for ln in text.splitlines():
                log.write(ln)

        @on(Button.Pressed, "#close")
        def close(self) -> None:
            self.dismiss(None)

    class EaxScreen(App):
        TITLE = "EA Explorer"
        CSS = CLASSIC
        BINDINGS = [Binding("f10", "menu(0)", "Menu"), Binding("f5", "refresh", "Refresh"), Binding("f1", "help", "Help"),
                    Binding("alt+x", "quit", "Exit"), Binding("alt+f5", "user_screen", "User screen")] + [
            Binding(f"alt+{g['key']}", f"menu({i})", show=False) for i, g in enumerate(groups) if g["key"]]

        def compose(self) -> ComposeResult:
            with Horizontal(id="menubar"):
                for i, g in enumerate(groups):
                    text, at = sm.bar_label(g["short"], g["key"])
                    label = Text(text)
                    if at >= 0:
                        label.stylize("bold underline #aa0000", at, at + 1)     # the Alt letter, as Turbo Pascal showed it
                    yield Button(label, id=f"m{i}", classes="menu-item")
            with Vertical(id="desk"):
                yield Label(" Containers ", classes="panel-title")
                yield DataTable(id="containers", cursor_type="none", zebra_stripes=False)
                yield Label(" Disks ", classes="panel-title")
                yield Static("", id="disks")
                yield Static("", id="note")
            yield Static(sm.STATUS_LINE, id="statusline")

        def on_mount(self) -> None:
            t = self.query_one("#containers", DataTable)
            t.add_columns("Container", "State", "Status")
            self.action_refresh()
            self.set_interval(5, self.action_refresh)

        def action_refresh(self) -> None:
            self.load()

        @work(thread=True, exclusive=True)
        def load(self) -> None:
            from .core import compose_out
            try:
                rows = sm.containers(compose_out(["ps", "-a", "--format", "json"]))
            except Exception as exc:  # noqa: BLE001 - Docker not running: said on the dashboard
                rows, note = [], f"Docker did not answer: {exc}"
            else:
                note = "" if rows else "No containers: start EA Explorer with Start > up."
            dk = sm.disks([ROOT, ROOT / "work", ROOT / "persist"])
            self.call_from_thread(self.show, rows, dk, note)

        def show(self, rows: list[dict], dk: list[dict], note: str) -> None:
            t = self.query_one("#containers", DataTable)
            t.clear()
            for r in rows:
                t.add_row(Text(r["service"]), Text(r["health"] or r["state"], style=f"bold {r['colour']}"), Text(r["status"]))
            self.query_one("#disks", Static).update(Text(
                "\n".join(f"{d['path']}: {sm.gb(d['free'])} free of {sm.gb(d['total'])} ({d['used']}% used)" for d in dk)))
            self.query_one("#note", Static).update(Text(note))

        @on(Button.Pressed, ".menu-item")
        def clicked(self, event: Button.Pressed) -> None:
            self.action_menu(int(event.button.id[1:]))

        def action_menu(self, index: int) -> None:
            def back(result) -> None:
                if not result:
                    return
                what, value = result
                if what == "move":
                    self.action_menu(value)
                else:
                    self.push_screen(Dialog(value), self.ran)
            self.push_screen(PullDown(index), back)

        def ran(self, line) -> None:
            if not line:
                return
            if sm.in_window(line):
                self.push_screen(Output(line))
            else:
                self.user_screen(line)

        def user_screen(self, line: list[str] | None) -> None:
            with self.suspend():
                if line:
                    print(f"\n{sm.shown(line, how)}\n", flush=True)
                    try:
                        code = subprocess.call(argv_for(line, form), cwd=str(ROOT))
                    except OSError as exc:
                        print(f"Could not run it: {exc}")
                        code = 1
                    print(f"\n(exit code {code}) Press Enter to return to the screen.", flush=True)
                else:
                    print("\nThe user screen. Press Enter to return to the screen.", flush=True)
                try:
                    input()
                except EOFError:
                    pass
            self.action_refresh()

        def action_user_screen(self) -> None:
            self.user_screen(None)

        def action_help(self) -> None:
            self.push_screen(HelpWindow())

    return EaxScreen()


# the classic look (owner: "classic Turbo Pascal look"): a blue desk, cyan menus, grey dialogs, a cyan status line
CLASSIC = """
Screen { background: #0000aa; color: #ffffff; }
#menubar { height: 1; background: #00aaaa; }
.menu-item { min-width: 0; height: 1; border: none; background: #00aaaa; color: #000000; padding: 0 1; margin: 0; }
.menu-item:hover, .menu-item:focus { background: #00aa00; color: #000000; text-style: bold; }
#desk { padding: 1 2; }
.panel-title { background: #aaaaaa; color: #000000; text-style: bold; margin-top: 1; }
#containers { height: auto; max-height: 24; background: #0000aa; color: #ffffff; }
#disks, #note { color: #ffff55; }
#statusline { dock: bottom; height: 1; background: #00aaaa; color: #000000; }
.pulldown-screen { align: left top; background: transparent; }
#pulldown { width: auto; max-width: 100; height: auto; max-height: 24; background: #aaaaaa; color: #000000;
            border: solid #000000; }
#pulldown > .option-list--option-highlighted { background: #00aa00; color: #000000; }
Dialog, Output, HelpWindow { align: center middle; background: rgba(0, 0, 0, 0.3); }
#dialog, #output { width: 90%; max-width: 110; height: auto; max-height: 90%; background: #aaaaaa; color: #000000;
                   border: double #ffffff; padding: 0 1; }
#output { height: 90%; }
#dialog-title, #output-title { width: 100%; content-align: center middle; background: #ffffff; color: #0000aa; text-style: bold; }
#dialog-fields { height: auto; max-height: 20; }
#dialog-line { background: #000000; color: #55ffff; margin-top: 1; padding: 0 1; }
#dialog-missing { color: #aa0000; }
#dialog-buttons { height: 3; align: center middle; }
.choice-row { height: auto; }
.choice-row Select { width: 1fr; }
.choice-row Input { width: 1fr; }
#output-log { background: #000000; color: #c0c0c0; height: 1fr; }
.quiet { color: #555555; }
"""


def main(argv: list[str] | None = None) -> int:
    why = why_not()
    if why or not load_textual():
        if why:
            print(f"eax screen: {why}; the numbered menu instead.")
        else:
            print("eax screen: Textual could not be fetched (offline?); the numbered menu instead. It is fetched once, "
                  "into work/tools/pylib, the next time.")
        return menu_.main(argv or [])
    form, how, windows = menu_._form()
    app = build_app(form, windows, how)
    try:
        app.run(mouse=True)
    except KeyboardInterrupt:
        pass
    return 0

