# Phase 40: EA capability maturity (D377, D381, D450 to D453, D456)

Release 0.17.0, migration 0037 (with phase 38.1).

## Status: built (10 Nov 2026, batch 1, D421), waiting for the owner's test

## What it delivers
- **EA capability maturity** (`#/maturity`, from Architecture repository › Architecture capability and from Surveys),
  for Super Admins (`maturity.manage`): every assessment, the **trend** over closed ones (overall and per element), and
  the **evidence EA Explorer measures now**.
- **An assessment is a survey** (38.1) of kind maturity, sent to the people chosen. Its starting questions follow the
  shape of the US Department of Commerce ACMM 1.2 (D381): **six levels** (0 None, 1 Initial, 2 Under development,
  3 Defined, 4 Managed, 5 Measured) and **nine elements** (architecture process, architecture development, business
  linkage, senior management involvement, operating unit participation, architecture communication, IT security,
  architecture governance, IT investment and acquisition strategy): per element "which description fits best today?"
  with a description for each level, and a comment. **The descriptions are EA Explorer's own wording**; no text was
  taken from any guide. They can be changed in the survey designer while an assessment is a draft. The TOGAF maturity
  guide is not used (D379).
- **Scores** (D452): per element the mean level, the target (default 3) and the gap, and the share of answers at or above
  each level (the ACMM's second method); overall the mean weighted by the elements' weights (its first method). The
  previous assessment's scores are shown beside them.
- **Evidence**: models in use, data quality, governance log use, projects following the ADM, sign-offs, people taking part,
  each tied to the elements it speaks to; live while open, kept with the scores when it closes.
- New assessment: title, people, closing date, reminders, anonymous or not, a target and a weight per element; make a
  draft (to change the questions) or make it and send it.
- Excel: the survey's workbook with a Maturity scores sheet.
- Rules in eax/maturity.py (Python, D248).

## One table, with examples and live bars (owner, 10 Nov 2026, D456)
- Every level of every element (0 to 5) has a **description and examples** of what you typically see, in our own words;
  editable in the designer (Description, Examples one a line) while an assessment is a draft.
- **Answering** is one table, a row per element: the element; "Levels and examples" (opened per row; the chosen one
  shown); the response: the **value** 0 to 5, a **comment** and **evidence** links (as Link attributes: any text, clickable
  only when safe), comment and evidence optional unless marked required; and a **bar** on a 0 to 5 scale with ticks
  that fills as the level is picked. Colours by level, always with the number and name written beside.
- **Results (Super Admins only)**: the same table with the mean bar, a target marker, the previous assessment as a
  dashed marker, the spread of answers per level and the overall weighted bar at the bottom; who has answered and who
  has not; **each person's answers** (values, comments, evidence; "Respondent n" when anonymous). Respondents only see
  their own answers.
- **Excel**: Maturity scores, Levels and examples, By question and Responses (every respondent's value, comment and
  evidence).

## Sample data (laptop, D453)
EA capability maturity May 2026 and October 2026 (closed: the trend), November 2026 (open, two of five answered); respondents give different values, and three of them comments and evidence links (one a shared-drive path, shown as text).

## Test steps
1. Sign in as user_super_admin: Architecture repository › Architecture capability › EA capability maturity.
2. The trend shows two points; open October 2026: mean, target marker and gap per element, the shares at each level,
   the May scores beside, the evidence kept when it closed.
3. ＋ New assessment: choose people and targets, Make it and send it; sign in as one of them and answer from the bell:
   pick levels and watch each row's bar fill; open Levels and examples; add a comment and an evidence link; Save.
   As Super Admin, open the scores: choose a person under Each person's answers.
4. Close it from Run it: it joins the trend.

## Not in this phase
The DoC document's own wording (the owner may paste it into the designer); scoring of anything but single-choice
questions with scores.
