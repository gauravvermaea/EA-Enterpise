# Key questions and placeholder views

Owner, 9 Nov 2026 (D341, D342). Accepted as a bug fix in release 0.15.1 (D343); closed 9 Nov 2026 (D356). Every piece of a project's work answers a stakeholder's question. The project records
those questions, what we expect the answer to be (or how we will answer it), the views that answer each one, the
answer itself, and whether the stakeholder accepted it.

## What a project holds

| | |
|---|---|
| **Key question** | The question (for example *What is the impact of removing an application?*), who asks it, and the answer we expect or the approach |
| **Its views** | The views that answer it. Many to many: a question may need several views (an application cooperation view *and* a process-to-application map), and one view may answer several questions |
| **Placeholder view** | Stands in where no view fits. Either **a text** (a name and what it will show) or **an empty file**: Word (.docx), PowerPoint (.pptx), Excel (.xlsx), PDF, draw.io, Markdown or text, made in the project's files (`00_Project/Project files`, named `PH-01 <name>.<type>`) to fill in later. Placeholders stay in the project (PH-01, PH-02 ...); they never join the organisation's view library |
| **The answer** | Rich text: a summary of the answer, pointing to the artifacts that hold it: documents of the project, links (https://…, or #/… for a page of EA Explorer) and the question's views (which link by themselves). At least one of them |
| **Status** | **open** → **answered** (waiting for acceptance) → **accepted** by the stakeholder |
| **History** | Every step: asked, changed, answered, accepted, not accepted, opened again; who and when, with the note |

## Answering and acceptance

* **Answer it** (anyone who contributes): the answer in rich text, the documents (find one by name) and links. The
  project's stakeholders are told in their bell.
* **The stakeholder accepts in the application**: a project member with the **Stakeholder** role sees *✓ Accept* and
  *Not accepted…* on an answered question (the tab says how many wait for them). Not accepting needs a reason; the
  question is open again, its last answer kept to be changed.
* **A contributor records a decision given outside** (*Record the stakeholder's decision…*): accepted or not, the
  stakeholder's name, the date, a note and an optional evidence file (kept in `00_Project/Sign-off evidence`).
* **Open it again** (a contributor, with a reason), for an answered or accepted question.
* Changing the question or the answer of an accepted one takes the acceptance away: it needs accepting again.

## Where they are

* **The project's Key questions tab** (its count shows the answers waiting for acceptance): filter by status; per
  question the answer and what it points to, the acceptance, the actions and the history; add, edit and remove
  questions; link and unlink views; add placeholders and download their files; *Make the missing files*.
* **The project wizard** (new project and ✎ Edit): a **Key questions** step before **Views**; the Views step
  starts with *Answering the key questions* (map views, or *+ No view fits: a placeholder*). Taking a view
  out of the project unlinks it from the questions. Answering and acceptance happen on the tab.
* **The Views tab** shows each view with the questions it answers (Q1, Q2 …, linking to the Key questions tab).
* A derived project starts with its parent's questions (open again) and placeholders. Project backups carry all of it.
* **Sample data** (laptop): every sample project has the key questions its kind of work answers, in every state: open,
  answered, accepted in the application (user_stakeholder), accepted as recorded by user_project_admin, not accepted
  and open again, accepted then opened again; some with placeholders (text, and empty .xlsx and .docx files).
* MCP: `get_project` part `questions`, `save_key_question`, `answer_key_question`, `key_question_decision`,
  `add_placeholder_view`.

## API

| | |
|---|---|
| `GET/POST /api/v1/projects/<id>/key-questions` | list; add `{question, asked_by, approach, views: [codes]}` |
| `PUT/DELETE /api/v1/projects/<id>/key-questions/<qid>` | change any of `question, asked_by, approach, answer, views, documents, links`; remove |
| `POST …/key-questions/<qid>/answer` | `{answer (rich text), documents: [ids], links: [{url, label}], views}` |
| `POST …/key-questions/<qid>/decide` | the stakeholder: `{decision: accepted \| rejected, note}` |
| `POST …/key-questions/<qid>/record` | a contributor: `by, on, decision, note` and an optional `file` (multipart) |
| `POST …/key-questions/<qid>/reopen` | `{note}` |
| `POST /api/v1/projects/<id>/placeholder-views` | add `{name, description, kind: text \| file, file_type, questions: [ids]}` |
| `PUT/DELETE /api/v1/projects/<id>/placeholder-views/<code>` | rename or describe; remove (its file stays) |
| `POST /api/v1/projects/<id>/placeholder-views/files` | make the empty file of each file placeholder that has none |

Tables (in migration 0032, release 0.15.1): `proj.key_questions`, `proj.question_views`, `proj.question_links`,
`proj.question_events`, `proj.placeholder_views`. Rules in `eax/key_questions.py`, `eax/blank_files.py` (D248);
sample data in `eax/seed/sample_questions.py`.

## To test

1. After a clean restart, open a sample project (for example Protea Claims Transformation 2028) › **Key questions**:
   six questions in every state; the filter counts them.
2. As user_lead_architect: answer an open question in rich text with a link and a document; record the stakeholder's
   acceptance of an answered one with an evidence file; open an accepted one again; edit and add a question.
3. As user_stakeholder: the tab says which answers wait; accept one, and reject one with a reason (it is open again).
   The bell shows the answers to accept; the architect's bell shows the decision.
4. ✎ Edit › **Key questions** and **Views**: add a question with a placeholder (an empty .pptx); save; the file is
   in Project files and opens in PowerPoint.
5. Back the project up and restore it: questions, answers, acceptances and history come back.
