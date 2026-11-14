# Data discovery and ingestion

The Release 3 epic (D670). The owner, 13 Nov 2026: "what I want for Data ingestion is a reverse OData feed: it discovers
and then writes to a model". EA Explorer already publishes each model as an OData feed (phase 24, D365); discovery is the
same in reverse: EA Explorer reads what your organisation already has and proposes it for a model.

## Where

A model's **Import and export › Discovery**. Anyone who may change the model's content (Architect, Committer, Model Sub
Admin, Model Admin) sets sources up and runs them. What a run finds arrives in **Import and export › Deliveries** as a
delivery: previewed (new, changed, kept, problems), then accepted (committed as that person's load, undone as any load)
or declined by a Committer, Model Sub Admin or Model Admin. Nothing reaches the model without that.

## Kinds of source

| Kind | What EA Explorer does |
| --- | --- |
| **OData feed** | Reads a feed's service document (each entity set) or one entity set, as JSON, following its pages. |
| **Push** | Takes what a system sends: `POST /api/v1/import-sources/<source>/push` with `{"<set>": [records]}` (or `{"value": [...], "set": "<set>"}`), as the model's service account or anyone who may load into it, signed in with a token, an API key, a client certificate or a user name and password. The Python kit shows how. |
| **Documents read by AI** | Sends the text of the documents dropped in the source's folder (`.txt`, `.md`, `.csv`, `.json`, `.html`, `.xml`, `.docx`), or of a page at its address, to the AI engine, which names the elements and relationships it finds. Read documents move to `done/`. |
| Folder | Files in the published formats dropped in its folder (phase 34, as before: Deliveries). |

Sign-in: give the **name** of a setting in the config file made for it, `EAX_SOURCE_` and a name (for example
`EAX_SOURCE_INVENTORY=Bearer ...`); its value is sent as the Authorization header. Secrets are never stored in the
database, and no other setting of the installation can ever be sent (R3.12, D671).

Addresses: a feed, a page or a redirect on this installation's own network (its services, such as `db` or `api`), on
the machine itself, or on a private or link-local network (cloud metadata included) is not read, unless IT lists its
host in `EAX_DISCOVERY_ALLOWED_HOSTS` in the config file (comma-separated; `*` for every host). A configuration database
inside your network is read once it is listed there.

## The Python kit (push sources)

A push source's panel on the Discovery tab has **Push with Python** (D674): the code to read and copy, the command, and
**Download the Python kit (zip)**:

| In the zip | What it is |
| --- | --- |
| `push_to_eax.py` | Reads the CSV files in a folder with pandas and sends them in one call; `push_dataframe(url, df, username, password)` sends one DataFrame, `push_dataframes` several (related sets go together, so their links become relationships) |
| `requirements.txt` | pandas and requests |
| `README.md` | Setting up Python in a venv (Windows, macOS, Linux), the command with this source's address, signing in, what happens next |
| `samples/*.csv` | A file for every entity type of the model, two records each, each with a relationship column the metamodel allows; the README lists the relationships they publish |

The script has no checks on purpose: it shows the call. Signing in, any of: a user name and password (an EA Explorer
account, or an Active Directory account when EA Explorer signs in against the directory), sent as HTTP Basic as the
OData feed takes it; a **personal token** (System admin › Machine access; the way for single sign-on users) or a service
account's **API key**, sent as a Bearer token; a **client certificate** trusted in Machine access, on the
machine-access port (9443).

## Deleting a source

**Delete** beside a source (after a confirm), by anyone who may set it up (D675). A source with a delivery still waiting
for review is not deleted: accept or decline it in Deliveries first. What it delivered stays (in the model and in Loads);
what it has seen and the matches confirmed go with it, so a new source starts from nothing.

## A run

1. **Look** reads the source and shows its sets, their fields, the key and name fields it guessed, and which fields hold
   another set's keys. It suggests the mapping: each set to an entity type (by name: "Applications" to Application
   Component), each field to an attribute, each key field to a relationship type. Change what is wrong and **Save the
   mapping**; it is kept for the source.
2. **Run now** (or daily or weekly on its own) reads it again and makes a delivery of what is **new or changed since the
   last delivery** (*Run in full* sends everything). Elements are matched by type and name, relationships by the names
   of their two ends.
3. A found name that is not in the model but close to an element of its type (85% alike or more) is listed: **Same
   element** (the next deliveries use the element's own name, so it is updated) or **It is new**.
4. A record renamed at the source is listed as renamed: it arrives as a new element and the old one stays, since a
   delivery never deletes (D370): merge or retire it.

## The AI engine

Import and export › Discovery shows it to Super Admins, below the sources: **off** until chosen; **cloud**, with the organisation's own key
(named by a setting in the config file, `EAX_AI_` and a name); or **local**, run on your own servers. Any engine with the common
chat-completions interface. The documents are sent as data, never as instructions, and what comes back is only ever a
delivery for a person to review.

## Tests

`tests/test_discovery.py` and `tests/test_discovery_kit.py` (the kit: its samples map themselves, the script's call and sign-in, the zip; reading, discovering, mapping, only what changed, renames, matches, the CSV format, the AI
answer), and the self-test's black-box check in the run's own test model (`discovery: ...` results: a push source, a
delivery, only what changed, a near name suggested, refused without the right).
