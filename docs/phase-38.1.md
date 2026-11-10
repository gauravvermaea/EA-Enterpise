# Phase 38.1: surveys (D375, D446 to D449)

Release 0.17.0, migration 0037 (with phase 40). Version 1.0 itself (phase 38) is not built here: it is released once the
release candidate (37) passes.

## Status: built (10 Nov 2026, batch 1, D421), waiting for the owner's test

## What it delivers
- **Surveys** (Everything else › Surveys, `#/surveys`): tabs To answer, Answered, I run, and Every survey for a Super Admin.
- **A designer** while a survey is a draft: sections and questions; kinds one choice, several choices, yes or no, rating
  (with words for low and high), number, date, short text and long text; options with an optional score and an "Other"
  with its own text; required answers; **conditions**: a section or a question shown only when an earlier answer is, is
  not, includes or is answered. Preview it before sending.
- **Who it is for**: people by name, everyone with a global role, everyone on a model (or with one role on it), everyone
  on a project; worked out when it is sent; more may be added while it is open (nobody is taken off). Optionally anyone
  signed in who has the link may answer.
- **Delivery through the task list and a link, never email**: each person gets a notification that needs action ("Please
  answer…"), resolved when they answer or the survey closes, and the link `#/surveys/<id>/answer`.
- **Running it**: send, remind those who have not answered, close, reopen, copy, delete a draft; a closing date closes it
  on its own and automatic reminders go every N days (the hourly job `eax.surveys`).
- **Answering**: shows only the questions that apply; saved as you go and changeable until it closes. **Anonymous**: no
  name kept with the answers, sent once, the draft kept only in the person's browser.
- **Results** for the person who made it and Super Admins: progress, results by question (counts and shares, mean and
  median, every text answer, with names unless anonymous), the people asked and when they answered; an anonymous
  survey's results show once three have answered. **Excel**: About, By question, Responses.
- **Nothing in any model is changed by answers** (D375).
- Who makes surveys: Super Admins, Model Creators and Library Admins (`surveys.create`).
- API: `/api/v1/surveys…` (eax/api/surveys.py); rules in eax/surveys.py; tables core.surveys, core.survey_recipients,
  core.survey_responses (rows only, D248); carried in the organisation part of application backups (D410); actions in the
  change log (who did what, never what anyone answered).

## Sample data (laptop, D449)
A draft (Drawing tools and training) with sections and conditions; an open survey (How do you use the architecture
repository?: four answered, one started, the rest asked and reminded, closes in 14 days, reminders every 7 days); a
closed one (Architecture board meeting feedback, October); an anonymous one (Architecture practice pulse) with five
answers.

## Test steps
1. `.\eax clean-restart`, Ctrl+F5. Sign in as user_model_creator: Everything else › Surveys › I run shows the four.
2. Open the draft: change a question, add a condition ("Ask only when"), Save questions; Preview; Send.
3. Sign in as user_global_architect: the bell shows "Please answer…"; open it: the answer page keeps the started answers.
   Answer "No" to the first question: the second section disappears. Send.
4. Back as user_model_creator: Results shows progress, bars, text answers and who answered; ⬇ Excel downloads three sheets.
5. The anonymous survey: results show (five answered); the Responses sheet has no names.
6. Close and reopen a survey: open tasks are resolved, then come back for those who had not answered.

## Not in this phase
Email (never); surveys inside a project's own pages; answers written into a model (never, D375).
