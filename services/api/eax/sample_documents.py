"""Other views and documents (D358 as kept simple by D415, D422): sample document templates for views and documents
outside TOGAF and ArchiMate, to download and use. Our own wording, no branding, invented examples only.

They are made here when downloaded (Word and PowerPoint written as the few XML parts they need; Excel with openpyxl), so
no template file is kept in the repository. They do nothing in a project or a model: nothing is copied into a
repository and nothing is stored.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from . import blank_files as bf
from .gaps import _p, _table, docx_from
from .metamodel_edit import EditError

WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
POWERPOINT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# code: (name, file type, what it is for, when to use it)
CATALOGUE: dict[str, tuple[str, str, str, str]] = {
    "swot": ("SWOT analysis", "pptx", "Strengths, weaknesses, opportunities and threats on one slide, in four boxes.",
             "Early in a piece of work, to agree where an organisation or a capability stands."),
    "swot-doc": ("SWOT analysis (document)", "docx", "The same four headings as a document, with questions to prompt each and room "
                 "for the actions that follow.", "When the SWOT needs explaining, not only listing."),
    "journey": ("Customer journey map", "pptx", "A customer's steps from left to right, with what they do, think and feel, the "
                "touchpoints and the pain points under each.", "When a change is about how customers experience a service."),
    "value-proposition": ("Value proposition canvas", "pptx", "What a customer segment is trying to get done, its pains and gains, "
                          "beside the products, pain relievers and gain creators that answer them.",
                          "When shaping a product or service around what customers need."),
    "one-page-plan": ("One-page business plan", "pptx", "Problem, customer segments, solution, unique value, channels, costs, revenue, "
                    "measures and the unfair advantage on one slide.", "For a new venture or product idea, before a full business case."),
    "interview": ("Stakeholder interview guide", "docx", "Questions to ask a stakeholder about their goals, concerns, pain points and "
                  "what success looks like, with room for notes.", "Before and during stakeholder interviews."),
    "decision-record": ("Decision record", "docx", "One decision: the context, the options looked at, the decision, why, and what "
                        "follows from it.", "Whenever a decision should be written down so it is not taken again."),
    "business-case": ("Business case outline", "docx", "The headings of a short business case: the problem, options, costs, benefits, "
                      "risks and the recommendation.", "When a change needs funding or approval."),
    "raid-log": ("Risks, assumptions, issues and dependencies log", "xlsx", "Four sheets with the usual columns, owners and dates, "
                 "ready to fill in.", "To keep track of what could stop a piece of work."),
    "lessons": ("Lessons learned", "docx", "What went well, what did not, and what to do differently, by topic.",
                "At the end of a phase or a project."),
}


def listing() -> dict:
    return {"templates": [{"code": c, "name": n, "type": t, "type_name": bf.TYPES[t], "purpose": p, "when": w}
                          for c, (n, t, p, w) in CATALOGUE.items()],
            "note": "Sample templates in our own wording, to download and use. They are not copied into a project or a model."}


def make(code: str) -> tuple[bytes, str, str]:
    if code not in CATALOGUE:
        raise EditError(f"No sample template {code!r}.", 404)
    name, kind, _p_, _w = CATALOGUE[code]
    data = {"swot": _swot_pptx, "swot-doc": _swot_docx, "journey": _journey, "value-proposition": _value_prop,
            "one-page-plan": _lean, "interview": _interview, "decision-record": _decision, "business-case": _business_case,
            "raid-log": _raid, "lessons": _lessons}[code]()
    return data, f"{name}.{kind}", {"docx": WORD, "pptx": POWERPOINT, "xlsx": EXCEL}[kind]


# ---------------------------------------------------------------- PowerPoint: boxes on one 16:9 slide
EMU = 12700          # one point


class _Slide:
    def __init__(self):
        self.shapes: list[str] = []
        self.n = 2

    def box(self, x: float, y: float, w: float, h: float, title: str, hint: str = "", fill: str = "F6F8FA", size: int = 12,
            title_size: int = 14) -> None:
        """A box (points from the slide's top left, 960 x 540) with a bold title and a grey hint under it."""
        paras = f'<a:p><a:r><a:rPr lang="en-GB" sz="{title_size * 100}" b="1"/><a:t>{escape(title)}</a:t></a:r></a:p>'
        for line in [ln for ln in hint.split("\n") if ln] if hint else []:
            paras += (f'<a:p><a:r><a:rPr lang="en-GB" sz="{size * 100}"><a:solidFill><a:srgbClr val="5B6775"/></a:solidFill></a:rPr>'
                      f"<a:t>{escape(line)}</a:t></a:r></a:p>")
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{self.n}" name="Box {self.n}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{int(x * EMU)}" y="{int(y * EMU)}"/><a:ext cx="{int(w * EMU)}" cy="{int(h * EMU)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
            '<a:ln w="9525"><a:solidFill><a:srgbClr val="8A96A3"/></a:solidFill></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="91440" tIns="91440" rIns="91440" bIns="91440" anchor="t"/><a:lstStyle/>{paras}</p:txBody></p:sp>')
        self.n += 1

    def text(self, x: float, y: float, w: float, h: float, s: str, size: int = 24, bold: bool = True) -> None:
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{self.n}" name="Text {self.n}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{int(x * EMU)}" y="{int(y * EMU)}"/><a:ext cx="{int(w * EMU)}" cy="{int(h * EMU)}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:rPr lang="en-GB" sz="{size * 100}" b="{1 if bold else 0}"/>'
            f"<a:t>{escape(s)}</a:t></a:r></a:p></p:txBody></p:sp>")
        self.n += 1

    def save(self, name: str) -> bytes:
        return bf.pptx_slide(name, "".join(self.shapes))


def _head(s: _Slide, title: str, sub: str) -> None:
    s.text(24, 12, 900, 34, title, 24)
    s.text(24, 44, 900, 22, sub, 11, bold=False)


def _swot_pptx() -> bytes:
    s = _Slide()
    _head(s, "SWOT analysis: [what is being looked at]", "Inside the organisation on top, outside it below. Two to five points a box; "
          "say what each means, not only what it is.")
    s.box(24, 76, 450, 220, "Strengths", "What do we do well?\nWhat do others see as our strengths?\nWhat do we have that others lack?", "E8F5E9")
    s.box(486, 76, 450, 220, "Weaknesses", "Where do we fall short?\nWhat do customers complain about?\nWhat do we avoid doing?", "FFF3E0")
    s.box(24, 306, 450, 220, "Opportunities", "What is changing that we could use?\nWhich needs are not met?\nWhat could we do with partners?", "E3F2FD")
    s.box(486, 306, 450, 220, "Threats", "What could hurt us?\nWhat are others doing?\nWhich rules, costs or technology are changing?", "FFEBEE")
    return s.save("SWOT analysis")


def _journey() -> bytes:
    s = _Slide()
    _head(s, "Customer journey map: [customer] wants to [goal]", "One column per step, left to right. Fill in what the customer does, "
          "thinks and feels at each step, where they meet us, and what goes wrong.")
    steps = ["Becomes aware", "Compares", "Signs up", "Uses", "Gets help", "Renews or leaves"]
    rows = ["Doing", "Thinking and feeling", "Touchpoints", "Pain points", "Ideas"]
    w = (912 - 120) / len(steps)
    for i, st in enumerate(steps):
        s.box(144 + i * w, 76, w - 6, 36, st, fill="DDE6F0", title_size=11)
    for j, r in enumerate(rows):
        y = 118 + j * 82
        s.box(24, y, 114, 76, r, fill="EEF1F4", title_size=11)
        for i in range(len(steps)):
            s.box(144 + i * w, y, w - 6, 76, "", fill="FFFFFF")
    return s.save("Customer journey map")


def _value_prop() -> bytes:
    s = _Slide()
    _head(s, "Value proposition canvas: [product] for [customer segment]", "Start on the right with the customer; then, on the left, "
          "say how the product answers each pain and gain. A good fit leaves nothing important unanswered.")
    s.box(24, 76, 450, 450, "", fill="F6F8FA")
    s.text(36, 80, 420, 24, "The product", 14)
    s.box(36, 108, 200, 410, "Products and services", "What we offer.\nList them; mark the essential ones.", "FFFFFF", 11, 12)
    s.box(244, 108, 222, 200, "Gain creators", "How it brings the gains the customer wants.", "E8F5E9", 11, 12)
    s.box(244, 318, 222, 200, "Pain relievers", "How it takes away the customer's pains.", "FFF3E0", 11, 12)
    s.box(486, 76, 450, 450, "", fill="F6F8FA")
    s.text(498, 80, 420, 24, "The customer", 14)
    s.box(498, 108, 200, 200, "Gains", "Outcomes and benefits they want.", "E8F5E9", 11, 12)
    s.box(498, 318, 200, 200, "Pains", "What annoys them, the risks and obstacles.", "FFF3E0", 11, 12)
    s.box(706, 108, 222, 410, "Customer jobs", "What they are trying to get done: tasks, problems to solve, needs to meet.", "FFFFFF", 11, 12)
    return s.save("Value proposition canvas")


def _lean() -> bytes:
    s = _Slide()
    _head(s, "One-page business plan: [idea]", "Fill in the problem and customer segments first; the riskiest assumptions are the "
          "ones to test first.")
    w = 912 / 5
    top, h1, h2 = 76, 300, 146
    s.box(24, top, w - 6, h1, "Problem", "The top three problems.\nHow are they solved today?", "FFFFFF", 10, 12)
    s.box(24 + w, top, w - 6, h1 / 2 - 3, "Solution", "The top three features.", "FFFFFF", 10, 12)
    s.box(24 + w, top + h1 / 2 + 3, w - 6, h1 / 2 - 3, "Key measures", "What shows it is working.", "FFFFFF", 10, 12)
    s.box(24 + 2 * w, top, w - 6, h1, "Unique value", "One clear message: why it is different and worth having.", "E3F2FD", 10, 12)
    s.box(24 + 3 * w, top, w - 6, h1 / 2 - 3, "Unfair advantage", "What cannot easily be copied or bought.", "FFFFFF", 10, 12)
    s.box(24 + 3 * w, top + h1 / 2 + 3, w - 6, h1 / 2 - 3, "Channels", "How customers are reached.", "FFFFFF", 10, 12)
    s.box(24 + 4 * w, top, w - 6, h1, "Customer segments", "Who it is for.\nThe early adopters.", "FFFFFF", 10, 12)
    s.box(24, top + h1 + 6, 453, h2, "Costs", "What it costs to build, run and sell.", "FFF3E0", 10, 12)
    s.box(483, top + h1 + 6, 453, h2, "Revenue", "How it makes money, and how much.", "E8F5E9", 10, 12)
    return s.save("One-page business plan")


# ---------------------------------------------------------------- Word
def _blank_rows(head: list[str], n: int) -> str:
    return _table([head] + [[""] * len(head) for _ in range(n)])


def _swot_docx() -> bytes:
    body = [_p("SWOT analysis: [what is being looked at]", "Title"),
            _table([["", ""], ["Prepared by", ""], ["Date", ""], ["Scope", ""]]),
            _p("How to use this", "Heading1"),
            _p("Inside the organisation: strengths and weaknesses. Outside it: opportunities and threats. Write two to five points "
               "under each heading and say what each one means for the work, then agree the actions that follow.")]
    for head, prompts in (("Strengths", "What do we do well? What do others see as our strengths?"),
                          ("Weaknesses", "Where do we fall short? What do customers complain about?"),
                          ("Opportunities", "What is changing that we could use? Which needs are not met?"),
                          ("Threats", "What could hurt us? Which rules, costs or technology are changing?")):
        body += [_p(head, "Heading1"), _p(prompts), _blank_rows(["Point", "What it means for us"], 4)]
    body += [_p("Actions", "Heading1"), _blank_rows(["Action", "From which point", "Owner", "By when"], 5)]
    return docx_from(body)


def _interview() -> bytes:
    body = [_p("Stakeholder interview guide", "Title"),
            _table([["", ""], ["Stakeholder", ""], ["Role", ""], ["Interviewer", ""], ["Date", ""]]),
            _p("Before the interview", "Heading1"),
            _p("Send the purpose and the topics a few days ahead. Allow 45 to 60 minutes. Ask open questions and let the "
               "stakeholder do most of the talking.")]
    for topic, qs in (("Their role and goals", ["What are you responsible for?", "What are you trying to achieve this year?"]),
                      ("How things work today", ["Walk me through a typical week.", "Where do things slow down or go wrong?"]),
                      ("Concerns", ["What worries you about the change?", "What must not be lost?"]),
                      ("Success", ["How will you know the change has worked?", "What would you measure?"]),
                      ("Others to talk to", ["Who else should we speak to?", "Who decides?"])):
        body += [_p(topic, "Heading1"), _table([["Question", "Notes"]] + [[q, ""] for q in qs])]
    body += [_p("Actions agreed", "Heading1"), _blank_rows(["Action", "Owner", "By when"], 3)]
    return docx_from(body)


def _decision() -> bytes:
    body = [_p("Decision record: [short title]", "Title"),
            _table([["", ""], ["Number", ""], ["Status", "Proposed / Agreed / Replaced"], ["Decided by", ""], ["Date", ""]])]
    for head, hint in (("Context", "What is the situation, and why does a decision have to be made now?"),
                       ("Options considered", "Each option, with what speaks for and against it."),
                       ("Decision", "What was decided, in one or two sentences."),
                       ("Why", "The reasons, and what mattered most."),
                       ("What follows", "What changes because of it, what must now be done, and what is no longer possible.")):
        body += [_p(head, "Heading1"), _p(hint)]
        if head == "Options considered":
            body.append(_blank_rows(["Option", "For", "Against"], 3))
    return docx_from(body)


def _business_case() -> bytes:
    body = [_p("Business case: [name of the change]", "Title"),
            _table([["", ""], ["Sponsor", ""], ["Prepared by", ""], ["Date", ""], ["Version", ""]])]
    for head, hint in (("Summary", "The problem, the recommended option and what it costs and brings, in half a page."),
                       ("The problem or opportunity", "What is wrong or possible today, and what it costs not to act."),
                       ("Outcomes wanted", "What will be different, and how it will be measured."),
                       ("Options", "Including doing nothing.")):
        body += [_p(head, "Heading1"), _p(hint)]
    body.append(_blank_rows(["Option", "Cost", "Benefits", "Risks"], 3))
    for head, hint in (("Costs and benefits", "Of the recommended option, by year."),):
        body += [_p(head, "Heading1"), _p(hint), _blank_rows(["", "Year 1", "Year 2", "Year 3"], 4)]
    body += [_p("Risks", "Heading1"), _blank_rows(["Risk", "Likelihood", "Impact", "What we will do"], 3),
             _p("Recommendation", "Heading1"), _p("The option recommended, and the decision asked for.")]
    return docx_from(body)


def _lessons() -> bytes:
    body = [_p("Lessons learned: [phase or project]", "Title"),
            _table([["", ""], ["Facilitated by", ""], ["Date", ""], ["People there", ""]]),
            _p("How to use this", "Heading1"),
            _p("Go topic by topic: planning, people, stakeholders, the architecture work, tools, governance. Agree what to keep "
               "doing and what to change, and give each change an owner.")]
    body += [_p("What went well", "Heading1"), _blank_rows(["Topic", "What went well", "Keep doing"], 4),
             _p("What did not go well", "Heading1"), _blank_rows(["Topic", "What happened", "Why"], 4),
             _p("What to do differently", "Heading1"), _blank_rows(["Change", "Owner", "By when"], 4)]
    return docx_from(body)


# ---------------------------------------------------------------- Excel
def _raid() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    sheets = {"Risks": ["ID", "Risk", "Cause", "Likelihood", "Impact", "Owner", "What we will do", "Review by", "Status"],
              "Assumptions": ["ID", "Assumption", "Why we assume it", "How we will check it", "Owner", "Check by", "Status"],
              "Issues": ["ID", "Issue", "Impact", "Priority", "Owner", "What we are doing", "Due", "Status"],
              "Dependencies": ["ID", "We depend on", "For", "Who provides it", "Needed by", "Owner", "Status"]}
    first = True
    for title, cols in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = title
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DDE6F0")
        for i, col in enumerate(cols, start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = 14 if len(col) < 10 else 28
        prefix = title[0]
        for n in range(1, 21):
            ws.cell(n + 1, 1, f"{prefix}-{n:02d}")
        dv = DataValidation(type="list", formula1='"Open,In hand,Closed"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{ws.cell(2, len(cols)).column_letter}2:{ws.cell(2, len(cols)).column_letter}200")
        if title == "Risks":
            lv = DataValidation(type="list", formula1='"Low,Medium,High"', allow_blank=True)
            ws.add_data_validation(lv)
            lv.add("D2:E200")
        ws.freeze_panes = "B2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
