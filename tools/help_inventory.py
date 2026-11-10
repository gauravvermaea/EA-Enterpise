"""What on-screen help EA Explorer needs (D497): every page (route), tab and sub-tab, pop-up, wizard step, field and
button found in the web screens' sources, as catalogue keys.

Used by services/api/tests/test_help_catalogue.py (the build fails when a key has no entry in
services/web/src/help/catalogue.json) and by hand:

    python3 tools/help_inventory.py            # every key needed, and the ones still missing
    python3 tools/help_inventory.py --missing  # only the missing ones

Keys:
  page:#/route          a top-level route in App.jsx
  tab:Label             a tab or sub-tab (any tab bar), by its label
  popup:Title           a pop-up, by its title; the dynamic parts of a title are written *
  step:Label            a wizard step
  field:Label           a form field, by its label (or aria-label / placeholder when it has no label)
  button:Text           a button without its own title (tooltip); buttons that carry title=... already have a tooltip
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services" / "web" / "src"
CATALOGUE = SRC / "help" / "catalogue.json"

# text that is not worth a help entry: symbols, single characters, numbers
_SKIP_TEXT = re.compile(r"^[\W\d_]*$|^.$")


def norm(text: str) -> str:
    """One key form for a piece of screen text: spaces collapsed, trailing colons and ellipses dropped."""
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"(\s*[:…]|\.\.\.)$", "", t).strip()
    return t


def _string_literals(expr: str) -> list[str]:
    """The texts a JSX attribute expression can show: a literal, a template with ${...} as *, or each branch of a ternary
    whose branches are literals or templates. Strings compared against (x === "a") are conditions, not texts; anything
    else (a variable) gives nothing."""
    expr = expr.strip()
    if expr.startswith("{") and expr.endswith("}"):
        expr = expr[1:-1].strip()
    out: list[str] = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c in "\"'":
            j = i + 1
            while j < len(expr) and expr[j] != c:
                j += 2 if expr[j] == "\\" else 1
            if not re.search(r"(===|!==|==|!=)$", expr[:i].rstrip()):     # a compared value is a condition, not text
                out.append(expr[i + 1:j])
            i = j + 1
        elif c == "`":
            j, depth = i + 1, 0
            while j < len(expr):
                if expr[j] == "\\":
                    j += 2
                    continue
                if expr.startswith("${", j):
                    depth += 1
                    j += 2
                    continue
                if expr[j] == "}" and depth:
                    depth -= 1
                elif expr[j] == "`" and not depth:
                    break
                elif expr[j] == "`" and depth:          # a template inside ${...}: skip to its end
                    k = expr.index("`", j + 1) if "`" in expr[j + 1:] else len(expr)
                    j = k
                j += 1
            out.append(_template(expr[i + 1:j]))
            i = j + 1
        elif c == "$" and expr.startswith("${", i):
            i += 2
        else:
            i += 1
    return [norm(o) for o in out if o is not None]


def _template(body: str) -> str:
    """A template literal's body with every ${...} (nested braces and templates too) replaced by *."""
    res, i = [], 0
    while i < len(body):
        if body.startswith("${", i):
            depth, j = 1, i + 2
            while j < len(body) and depth:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                j += 1
            res.append("*")
            i = j
        else:
            res.append(body[i])
            i += 1
    return re.sub(r"\*(\s*\*)+", "*", "".join(res))


def _attr(tag: str, name: str) -> str | None:
    """An attribute's raw value in a JSX opening tag: "..." or {...} (balanced braces)."""
    m = re.search(r"(?<![\w-])" + name + r"=", tag)
    if not m:
        return None
    i = m.end()
    if i < len(tag) and tag[i] == '"':
        j = tag.index('"', i + 1)
        return tag[i:j + 1]
    if i < len(tag) and tag[i] == "{":
        depth, j = 0, i
        while j < len(tag):
            if tag[j] == "{":
                depth += 1
            elif tag[j] == "}":
                depth -= 1
                if not depth:
                    return tag[i:j + 1]
            j += 1
    return None


def _opening_tags(src: str, name: str):
    """Each JSX opening tag <name ...> (attributes may hold braces and arrows), with its end position."""
    for m in re.finditer(r"<" + name + r"(?=[\s>/])", src):
        i, depth, quote = m.end(), 0, None
        while i < len(src):
            c = src[i]
            if quote:
                if c == "\\":
                    i += 1
                elif c == quote:
                    quote = None
            elif (c in "\"'`" and depth) or c == '"':
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and not depth:
                yield src[m.start():i + 1], i + 1
                break
            i += 1


def _leading_text(src: str, pos: int) -> str:
    """The literal text right after an opening tag, up to the next tag or expression."""
    m = re.match(r"([^<{]*)", src[pos:])
    return norm(m.group(1)) if m else ""


def _first_child_text(src: str, pos: int) -> str:
    """The words of a label written as <label><span>Words</span>...: the first child element's leading text."""
    m = re.match(r"\s*<(span|b|strong|em|small|div)(\s[^>]*)?>([^<{]*)", src[pos:])
    if not m or (m.group(2) and "title=" in m.group(2)):
        return ""
    return norm(m.group(3))


def _keep(text: str) -> bool:
    return bool(text) and not _SKIP_TEXT.match(text) and text != "*"


def routes() -> set[str]:
    app = (SRC / "App.jsx").read_text(encoding="utf-8")
    found = set(re.findall(r'route(?:\.startsWith\(|\s*===\s*)"(#/[a-z0-9-]*)', app))
    return {"page:" + r for r in found}


def _pairs(text: str) -> list[str]:
    """The labels of [key, label] pairs: ["views", "Views"] or ["views", `Views (${n})`]."""
    out = []
    for m in re.finditer(r'\[\s*"([a-z0-9_-]+)"\s*,\s*("(?:[^"\\]|\\.)*"|`[^`]*`)', text):
        lab = _string_literals(m.group(2))
        if lab:
            t = norm(re.sub(r"\s*\(\*\)|\s*\*", "", lab[0]))
            if _keep(t) and not t[0].islower():
                out.append(t)
    return out


def _balanced(src: str, start: int, open_c: str = "[", close_c: str = "]") -> str:
    depth = 0
    for j in range(start, len(src)):
        if src[j] == open_c:
            depth += 1
        elif src[j] == close_c:
            depth -= 1
            if not depth:
                return src[start:j + 1]
    return src[start:]


def tabs() -> set[str]:
    keys: set[str] = set()
    for f in SRC.glob("*.jsx"):
        src = f.read_text(encoding="utf-8")
        # tab lists held in a variable: const tabs = [...], const TABS = [...], ...Tabs = [...]
        for m in re.finditer(r"\b(?:tabs|TABS|[A-Z_]*TABS|[a-z]+Tabs)\s*=\s*\[", src):
            keys.update("tab:" + t for t in _pairs(_balanced(src, m.end() - 1)))
        # inline lists mapped straight into role="tab" elements
        for m in re.finditer(r"\{\s*\[\s*\[", src):
            arr = _balanced(src, m.start() + 1)
            after = src[m.start() + 1 + len(arr): m.start() + 1 + len(arr) + 400]
            if 'role="tab"' in after:
                keys.update("tab:" + t for t in _pairs(arr))
        # tab elements written out one by one
        for tag, end in list(_opening_tags(src, "button")) + list(_opening_tags(src, "a")):
            if 'role="tab"' in tag:
                t = _leading_text(src, end)
                if _keep(t):
                    keys.add("tab:" + t)
    return keys


def popups() -> set[str]:
    keys: set[str] = set()
    for f in SRC.glob("*.jsx"):
        src = f.read_text(encoding="utf-8")
        for tag, _end in _opening_tags(src, "Modal"):
            v = _attr(tag, "title")
            for t in _string_literals(v or ""):
                if _keep(t.replace("*", "").strip()):
                    keys.add("popup:" + t)
        for tag, _end in _opening_tags(src, "div"):
            if 'role="dialog"' in tag:
                v = _attr(tag, "aria-label")
                for t in _string_literals(v or ""):
                    if _keep(t.replace("*", "").strip()):
                        keys.add("popup:" + t)
    return keys


def steps() -> set[str]:
    keys: set[str] = set()
    for f in SRC.glob("*.jsx"):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\b(?:STEPS|[A-Z_]+_STEPS)\s*=\s*\[", src):
            for t in re.findall(r'"((?:[^"\\]|\\.)*)"', _balanced(src, m.end() - 1)):
                if _keep(norm(t)):
                    keys.add("step:" + norm(t))
    return keys


def fields() -> set[str]:
    keys: set[str] = set()
    for f in SRC.glob("*.jsx"):
        src = f.read_text(encoding="utf-8")
        for tag, end in _opening_tags(src, "label"):
            if _attr(tag, "title"):
                continue                                      # the label carries its own tooltip
            t = _leading_text(src, end) or _first_child_text(src, end)
            if _keep(t):
                keys.add("field:" + t)
        for tag, _end in _opening_tags(src, "Field"):        # ModelOps' <Field label=... tip=...>
            if _attr(tag, "tip"):
                continue
            for t in _string_literals(_attr(tag, "label") or ""):
                if _keep(t.replace("*", "").strip()):
                    keys.add("field:" + t)
        for name in ("input", "select", "textarea"):
            for tag, _end in _opening_tags(src, name):
                if _attr(tag, "title") or re.search(r'type="(hidden|checkbox|radio|file)"', tag):
                    continue
                for a in ("aria-label", "placeholder"):
                    v = _attr(tag, a)
                    lab = [x for x in _string_literals(v or "") if _keep(x.replace("*", "").strip())]
                    if lab:
                        keys.add("field:" + lab[0])
                        break
    return keys


def buttons() -> set[str]:
    keys: set[str] = set()
    for f in SRC.glob("*.jsx"):
        src = f.read_text(encoding="utf-8")
        for tag, end in _opening_tags(src, "button"):
            if _attr(tag, "title") or 'role="tab"' in tag:
                continue
            t = _leading_text(src, end)
            if not _keep(t):                                  # a symbol (✕, ▶...): its aria-label names it
                lab = _string_literals(_attr(tag, "aria-label") or "")
                t = lab[0] if lab else ""
            if _keep(t.replace("*", "").strip()) and len(t) <= 80:
                keys.add("button:" + t)
    return keys


def needed() -> dict[str, set[str]]:
    return {"page": routes(), "tab": tabs(), "popup": popups(), "step": steps(), "field": fields(), "button": buttons()}


def catalogue() -> dict:
    return json.loads(CATALOGUE.read_text(encoding="utf-8")) if CATALOGUE.exists() else {}


def covered(cat: dict) -> set[str]:
    """Every key the catalogue answers: its entries plus their aliases."""
    keys = set()
    for k, v in cat.items():
        if k.startswith("_"):
            continue
        keys.add(k)
        if isinstance(v, dict):
            keys.update(v.get("aliases", []))
    return keys


def missing() -> dict[str, list[str]]:
    have = covered(catalogue())
    return {kind: sorted(k for k in ks if k not in have) for kind, ks in needed().items()}


if __name__ == "__main__":
    only_missing = "--missing" in sys.argv
    need = needed()
    miss = missing()
    for kind, ks in need.items():
        print(f"{kind}: {len(ks)} needed, {len(miss[kind])} missing")
        for k in (miss[kind] if only_missing else sorted(ks)):
            print("  " + k)
