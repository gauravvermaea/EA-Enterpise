# TOGAF template deliverables (not in git)

**One-time admin task.** Download **The TOGAF Standard, 10th Edition: Template Deliverables** (The Open Group
publication **I094**) from <https://publications.opengroup.org/i094>, unzip it here keeping its phase folders, then, as a
Super Admin, open **Administration > Project library** and press **Load templates from the folder**. `eax up` and the
Project library page remind you until it is done. To keep the files somewhere else, set `EAX_LIBRARY_DIR` in
`work/eaexplorer.env` to a folder that holds `templates/togaf`, and run `eax up`.

Put your licensed copies of **The TOGAF Standard, 10th Edition template deliverables** here, in their phase folders,
exactly as The Open Group publishes them, for example:

```
library/templates/togaf/Preliminary Phase/TOGAF® Template - Architecture Principles.docx
library/templates/togaf/Phase A - Architecture Vision/TOGAF® Template - Statement of Architecture Work.docx
...
```

Everything in this folder except this README is ignored by git (`.gitignore`): the files are The Open Group's copyright
and their licence does not allow them to be redistributed, so they must never be pushed to GitHub, even when bought.

EA Explorer reads this folder (mounted read only into the api container at `/data/library`). On **Administration >
Project library**, a Super Admin presses **Load templates from the library folder**: each file whose name matches a
TOGAF template in the library is stored in Mayan exactly as it is, unchanged and unbranded, and projects get copies of
it. A Super Admin can also upload a file there one at a time.
