"""The OData feed (phase 24, D365, D433): Power BI, Excel and other OData clients read a model's entity types as tables.

Read only, OData version 4 (JSON), one feed per model:

    /api/v1/odata/models/<model>/                  the service document: the tables
    /api/v1/odata/models/<model>/$metadata         their columns (CSDL XML)
    /api/v1/odata/models/<model>/<Table>           the rows (?$select, $filter, $orderby, $top, $skip, $count)

Tables: one per entity type of the model (named after its code, e.g. ApplicationComponent), with the standard columns
and one column per attribute; plus Entities (every entity) and Relationships (every relationship, its two ends by id and
name). Only committed content, never anyone's uncommitted changes. Rows come in pages of PAGE with a next link.

Signed in, with the person's own permissions: the rows are read as the person, so row-level security gives them only the
models they may read (repository rules, D138). How a client signs in (odata_auth.user()): the usual Keycloak access token
(Bearer), or Basic (user name and password, which Keycloak checks; what Power BI and Excel offer). Machine access (phase
25) adds its credentials through odata_auth.CHECKS without changing this module.

$filter understands the common forms: eq, ne, gt, ge, lt, le, and, or, not, parentheses, contains(), startswith(),
endswith(), null, true and false. Anything else is refused with a clear message.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import text

from . import repository as repo
from .metamodel_edit import EditError

PAGE = 5000
NS = "EAExplorer"
EDM = {"text": "Edm.String", "long_text": "Edm.String", "list": "Edm.String", "url": "Edm.String", "email": "Edm.String",
       "integer": "Edm.Int64", "decimal": "Edm.Decimal", "currency": "Edm.Decimal", "percent": "Edm.Decimal",
       "date": "Edm.Date", "boolean": "Edm.Boolean", "entity_ref": "Edm.String"}
STANDARD = [("Id", "Edm.Guid"), ("DisplayId", "Edm.String"), ("Name", "Edm.String"), ("Description", "Edm.String"),
            ("EntityType", "Edm.String"), ("Domain", "Edm.String"), ("ParentId", "Edm.Guid"), ("Parent", "Edm.String"),
            ("Status", "Edm.String"), ("CreatedAt", "Edm.DateTimeOffset"), ("CreatedBy", "Edm.String"),
            ("ModifiedAt", "Edm.DateTimeOffset"), ("ModifiedBy", "Edm.String"), ("Link", "Edm.String")]
REL_COLUMNS = [("Id", "Edm.Guid"), ("RelationshipType", "Edm.String"), ("Verb", "Edm.String"), ("Name", "Edm.String"),
               ("SourceId", "Edm.Guid"), ("Source", "Edm.String"), ("SourceType", "Edm.String"),
               ("TargetId", "Edm.Guid"), ("Target", "Edm.String"), ("TargetType", "Edm.String")]


class ODataError(EditError):
    pass


def pascal(code: str) -> str:
    """An OData name: letters, digits and underscores, starting with a letter (ApplicationComponent, Annual_cost -> AnnualCost)."""
    parts = re.split(r"[^A-Za-z0-9]+", code or "")
    s = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if not s or not s[0].isalpha():
        s = "X" + s
    return s


# ---------------------------------------------------------------- the model's tables
def schema(conn, m: dict) -> dict[str, dict]:
    """{table name: {"type": entity type code or None, "columns": [(name, edm, source)]}}; source is a standard field
    or an attribute code."""
    types = conn.execute(text("""
        SELECT t.id, t.code, t.name FROM core.entity_types t
         WHERE t.model_id = :m AND NOT t.is_deleted AND NOT t.is_connector ORDER BY t.code"""), {"m": m["_id"]}).mappings().all()
    attrs: dict[int, list[dict]] = {}
    for r in conn.execute(text("""
            SELECT i.entity_type_id, a.code, a.data_type_code FROM core.item_attributes i
              JOIN core.attribute_types a ON a.id = i.attribute_type_id
             WHERE i.model_id = :m AND NOT i.is_deleted AND NOT a.is_deleted ORDER BY i.sort_order, a.code"""), {"m": m["_id"]}).mappings():
        attrs.setdefault(r["entity_type_id"], []).append({"code": r["code"], "data_type": r["data_type_code"]})
    out: dict[str, dict] = {"Entities": {"type": None, "name": "Every entity",
                                         "columns": [(n, e, n) for n, e in STANDARD]},
                            "Relationships": {"type": "#rel", "name": "Every relationship",
                                              "columns": [(n, e, n) for n, e in REL_COLUMNS]}}
    for t in types:
        name = pascal(t["code"])
        while name in out:
            name += "_"
        cols = [(n, e, n) for n, e in STANDARD]
        used = {n for n, _e in STANDARD}
        for a in attrs.get(t["id"], []):
            cname = pascal(a["code"])
            while cname in used:
                cname += "_"
            used.add(cname)
            cols.append((cname, EDM.get(a["data_type"], "Edm.String"), "attr:" + a["code"].lower()))
        out[name] = {"type": t["code"], "name": t["name"], "columns": cols}
    return out


def service_document(conn, model: Any, base: str) -> dict:
    m = repo.get_model(conn, model)
    tables = schema(conn, m)
    return {"@odata.context": f"{base}$metadata",
            "value": [{"name": n, "kind": "EntitySet", "url": n, "title": t["name"]} for n, t in tables.items()]}


def metadata(conn, model: Any) -> str:
    m = repo.get_model(conn, model)
    tables = schema(conn, m)
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">',
           '<edmx:DataServices>', f'<Schema Namespace="{NS}" xmlns="http://docs.oasis-open.org/odata/ns/edm">']
    for name, t in tables.items():
        out.append(f'<EntityType Name="{name}"><Key><PropertyRef Name="Id"/></Key>')
        for c, edm, _src in t["columns"]:
            extra = ' Nullable="false"' if c == "Id" else (' Scale="variable"' if edm == "Edm.Decimal" else "")
            out.append(f'<Property Name="{c}" Type="{edm}"{extra}/>')
        out.append("</EntityType>")
    out.append('<EntityContainer Name="Model">')
    for name, t in tables.items():
        out.append(f'<EntitySet Name="{name}" EntityType="{NS}.{name}">'
                   f'<Annotation Term="Org.OData.Core.V1.Description" String="{escape(t["name"], {chr(34): "&quot;"})}"/>'
                   "</EntitySet>")
    out += ["</EntityContainer>", "</Schema>", "</edmx:DataServices>", "</edmx:Edmx>"]
    return "\n".join(out)


# ---------------------------------------------------------------- reading rows (as the person)
def _value(v: dict, edm: str):
    if v.get("value_number") is not None:
        n = Decimal(str(v["value_number"]))
        return int(n) if edm == "Edm.Int64" else n
    if v.get("value_date") is not None:
        return v["value_date"]
    if v.get("value_bool") is not None:
        return bool(v["value_bool"])
    if v.get("value_ref_name") is not None:
        return v["value_ref_name"]
    return v.get("value_text")


def rows(conn, m: dict, table: dict) -> list[dict]:
    """Every row of a table, as plain values (filtered, ordered and paged afterwards)."""
    if table["type"] == "#rel":
        res = conn.execute(text("""
            SELECT r.guid::text AS "Id", rt.name AS "RelationshipType", coalesce(rt.verb, '') AS "Verb", r.name AS "Name",
                   s.guid::text AS "SourceId", s.name AS "Source", st.name AS "SourceType",
                   t.guid::text AS "TargetId", t.name AS "Target", tt.name AS "TargetType"
              FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
              JOIN core.entities s ON s.id = r.source_entity_id AND NOT s.is_deleted JOIN core.entity_types st ON st.id = s.entity_type_id
              JOIN core.entities t ON t.id = r.target_entity_id AND NOT t.is_deleted JOIN core.entity_types tt ON tt.id = t.entity_type_id
             WHERE r.model_id = :m AND NOT r.is_deleted ORDER BY rt.name, s.name, t.name"""), {"m": m["_id"]}).mappings().all()
        return [dict(r) for r in res]
    where = "" if table["type"] is None else "AND t.code = :t"
    ents = conn.execute(text(f"""
        SELECT e.id, e.guid::text AS "Id", e.display_id AS "DisplayId", e.name AS "Name", e.description AS "Description",
               t.name AS "EntityType", l.name AS "Domain", p.guid::text AS "ParentId", p.name AS "Parent", e.status_code AS "Status",
               e.created_at AS "CreatedAt", e.created_by AS "CreatedBy", e.modified_at AS "ModifiedAt", e.modified_by AS "ModifiedBy"
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id AND NOT t.is_connector
          JOIN core.layers l ON l.id = t.layer_id
          LEFT JOIN core.entities p ON p.id = e.parent_entity_id
         WHERE e.model_id = :m AND NOT e.is_deleted {where} ORDER BY e.display_id, e.name"""),
        {"m": m["_id"], "t": table["type"]}).mappings().all()
    out = []
    by_id: dict[int, dict] = {}
    for e in ents:
        r = dict(e)
        r["Link"] = f"#/metamodel/{m['id']}/entity/{r['Id']}"
        by_id[r.pop("id")] = r
        out.append(r)
    attr_cols = [(c, edm, src[5:]) for c, edm, src in table["columns"] if src.startswith("attr:")]
    if attr_cols and out:
        wanted = {code: (c, edm) for c, edm, code in attr_cols}
        for v in conn.execute(text(f"""
                SELECT v.entity_id, lower(a.code) AS code, v.value_text, v.value_number, v.value_date, v.value_bool,
                       rf.name AS value_ref_name
                  FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
                  JOIN core.entities e ON e.id = v.entity_id JOIN core.entity_types t ON t.id = e.entity_type_id
                  LEFT JOIN core.entities rf ON rf.id = v.value_ref
                 WHERE v.model_id = :m AND NOT v.is_deleted AND v.entity_id IS NOT NULL {where}"""),
                {"m": m["_id"], "t": table["type"]}).mappings():
            if v["code"] in wanted and v["entity_id"] in by_id:
                c, edm = wanted[v["code"]]
                by_id[v["entity_id"]][c] = _value(dict(v), edm)
        for r in out:
            for c, _edm, _code in attr_cols:
                r.setdefault(c, None)
    return out


# ---------------------------------------------------------------- $filter
_TOKEN = re.compile(r"""\s*(?:
    (?P<str>'(?:[^']|'')*') |
    (?P<num>-?\d+(?:\.\d+)?(?![\w-])) |
    (?P<date>\d{4}-\d{2}-\d{2}(?:T[0-9:.]+(?:Z|[+-]\d{2}:\d{2})?)?) |
    (?P<guid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}) |
    (?P<word>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<punct>[(),])
)""", re.X)


def _tokens(s: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    s = s.strip()
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m or m.end() == pos:
            raise ODataError(f"$filter: cannot read '{s[pos:pos + 20]}'.", 400)
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
        while pos < len(s) and s[pos] == " ":
            pos += 1
    return out


class _Parser:
    COMPARE = {"eq", "ne", "gt", "ge", "lt", "le"}
    FUNCS = {"contains", "startswith", "endswith"}

    def __init__(self, tokens, columns: set[str]):
        self.t, self.i, self.columns = tokens, 0, columns

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1].lower() != value):
            raise ODataError(f"$filter: expected {value or 'more'} near '{tok[1] or 'the end'}'.", 400)
        self.i += 1
        return tok

    def parse(self):
        node = self.or_()
        if self.peek()[0] is not None:
            raise ODataError(f"$filter: unexpected '{self.peek()[1]}'.", 400)
        return node

    def or_(self):
        node = self.and_()
        while self.peek()[0] == "word" and self.peek()[1].lower() == "or":
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self):
        node = self.not_()
        while self.peek()[0] == "word" and self.peek()[1].lower() == "and":
            self.take()
            node = ("and", node, self.not_())
        return node

    def not_(self):
        if self.peek()[0] == "word" and self.peek()[1].lower() == "not":
            self.take()
            return ("not", self.not_())
        return self.compare()

    def operand(self):
        kind, value = self.take()
        if kind == "str":
            return ("lit", value[1:-1].replace("''", "'"))
        if kind == "num":
            return ("lit", Decimal(value))
        if kind == "date":
            return ("lit", value)
        if kind == "guid":
            return ("lit", value.lower())
        if kind == "word":
            low = value.lower()
            if low == "null":
                return ("lit", None)
            if low in ("true", "false"):
                return ("lit", low == "true")
            if value not in self.columns:
                raise ODataError(f"$filter: there is no column '{value}'.", 400)
            return ("col", value)
        raise ODataError(f"$filter: unexpected '{value}'.", 400)

    def compare(self):
        kind, value = self.peek()
        if kind == "punct" and value == "(":
            self.take("(")
            node = self.or_()
            self.take(")")
            return node
        if kind == "word" and value.lower() in self.FUNCS:
            self.take()
            self.take("(")
            a = self.operand()
            self.take(",")
            b = self.operand()
            self.take(")")
            return ("fn", value.lower(), a, b)
        left = self.operand()
        kind, op = self.peek()
        if kind != "word" or op.lower() not in self.COMPARE:
            raise ODataError(f"$filter: expected eq, ne, gt, ge, lt or le after {left[1]}.", 400)
        self.take()
        return ("cmp", op.lower(), left, self.operand())


def _val(node, row):
    return row.get(node[1]) if node[0] == "col" else node[1]


def _norm(a, b):
    """Make two values comparable: dates and times with their text, numbers with numbers, text without case."""
    if isinstance(a, (datetime, date)) and isinstance(b, str):
        return a.isoformat()[:len(b)], b
    if isinstance(b, (datetime, date)) and isinstance(a, str):
        return a, b.isoformat()[:len(a)]
    if isinstance(a, (int, float, Decimal)) and not isinstance(a, bool) and isinstance(b, (int, float, Decimal)):
        return Decimal(str(a)), Decimal(str(b))
    if isinstance(a, str) and isinstance(b, str):
        return a.lower(), b.lower()
    return a, b


def evaluate(node, row) -> bool:
    kind = node[0]
    if kind == "and":
        return evaluate(node[1], row) and evaluate(node[2], row)
    if kind == "or":
        return evaluate(node[1], row) or evaluate(node[2], row)
    if kind == "not":
        return not evaluate(node[1], row)
    if kind == "fn":
        a, b = _val(node[2], row), _val(node[3], row)
        if a is None or b is None:
            return False
        a, b = str(a).lower(), str(b).lower()
        return {"contains": b in a, "startswith": a.startswith(b), "endswith": a.endswith(b)}[node[1]]
    op, a, b = node[1], _val(node[2], row), _val(node[3], row)
    if op in ("eq", "ne"):
        if a is None or b is None:
            same = a is None and b is None
        else:
            x, y = _norm(a, b)
            try:
                same = x == y
            except TypeError:
                same = False
        return same if op == "eq" else not same
    if a is None or b is None:
        return False
    x, y = _norm(a, b)
    try:
        return {"gt": x > y, "ge": x >= y, "lt": x < y, "le": x <= y}[op]
    except TypeError:
        return False


def parse_filter(expr: str, columns: set[str]):
    return _Parser(_tokens(expr), columns).parse() if (expr or "").strip() else None


# ---------------------------------------------------------------- one request
def _json(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v) if v != v.to_integral() else int(v)
    return v


def _sort_key(v):
    """Empty values last; numbers, dates and text each in their own order (no mixing errors)."""
    if v is None:
        return (2, 0, "")
    if isinstance(v, bool):
        return (0, 0, int(v))
    if isinstance(v, (int, float, Decimal)):
        return (0, 1, Decimal(str(v)))
    if isinstance(v, (datetime, date)):
        return (0, 2, v.isoformat())
    return (0, 3, str(v).lower())


def query(conn, model: Any, table_name: str, args: dict[str, str], base: str) -> dict:
    """One page of a table, with $select, $filter, $orderby, $top, $skip and $count (and $skiptoken, our next-page link)."""
    m = repo.get_model(conn, model)
    tables = schema(conn, m)
    table = tables.get(table_name)
    if table is None:
        raise ODataError(f"There is no table {table_name} in {m['name']}; the service document lists them.", 404)
    columns = [c for c, _e, _s in table["columns"]]
    sel = [s.strip() for s in (args.get("$select") or "").split(",") if s.strip()]
    for s in sel:
        if s != "*" and s not in columns:
            raise ODataError(f"$select: there is no column '{s}'.", 400)
    data = rows(conn, m, table)
    flt = parse_filter(args.get("$filter") or "", set(columns))
    if flt is not None:
        data = [r for r in data if evaluate(flt, r)]
    order = args.get("$orderby") or ""
    for part in reversed([p.strip() for p in order.split(",") if p.strip()]):
        bits = part.split()
        col, desc = bits[0], len(bits) > 1 and bits[1].lower() == "desc"
        if col not in columns:
            raise ODataError(f"$orderby: there is no column '{col}'.", 400)
        data.sort(key=lambda r, c=col: _sort_key(r.get(c)), reverse=desc)
    total = len(data)

    def _int(name: str, default: int | None) -> int | None:
        raw = args.get(name)
        if raw in (None, ""):
            return default
        if not str(raw).isdigit():
            raise ODataError(f"{name} must be a whole number.", 400)
        return int(raw)
    skip = _int("$skip", 0) + _int("$skiptoken", 0)
    top = _int("$top", None)
    end = len(data) if top is None else min(len(data), skip + top)
    page_end = min(end, skip + PAGE)
    page = data[skip:page_end]
    keep = columns if not sel or "*" in sel else ["Id", *[c for c in sel if c != "Id"]]
    out: dict[str, Any] = {"@odata.context": f"{base}$metadata#{table_name}"
                                             + (f"({','.join(keep)})" if sel and "*" not in sel else "")}
    if args.get("$count", "").lower() == "true":
        out["@odata.count"] = total
    out["value"] = [{c: _json(r.get(c)) for c in keep} for r in page]
    if page_end < end:
        from urllib.parse import urlencode
        nxt = {k: v for k, v in args.items() if k not in ("$skiptoken", "$skip")}
        nxt["$skip"] = str(_int("$skip", 0))
        nxt["$skiptoken"] = str(page_end - _int("$skip", 0))
        if top is not None:
            nxt["$top"] = str(top)
        out["@odata.nextLink"] = f"{base}{table_name}?{urlencode(nxt, safe='$,')}"
    return out


def feed_url(base_url: str, model_guid: str) -> str:
    """The address a person pastes into Power BI or Excel (Get data > OData feed)."""
    return f"{base_url.rstrip('/')}/api/v1/odata/models/{model_guid}/"
