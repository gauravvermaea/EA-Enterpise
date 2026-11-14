# Pushing data to {model} with Python

This kit sends records to the model **{model}** through its Push source **{source}**. It is an example to read and
adapt: one short Python file, `push_to_eax.py`, with no checks, so the call to EA Explorer is easy to follow.

| File | What it is |
| --- | --- |
| `push_to_eax.py` | Reads the CSV files and sends them to EA Explorer (`push_dataframe` and `push_dataframes` do the call) |
| `requirements.txt` | The two packages it needs: pandas and requests |
| `samples/*.csv` | Sample records, one file per set; each file's name is an entity type of this model |

The Push address of this source:

    {push_url}

## 1. Set up Python (once)

You need Python 3.10 or later (`python --version`). In the folder where you unzipped this kit:

**Windows (PowerShell)**

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

**macOS and Linux**

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Next time, activate the environment again (the second line) before running the script.

## 2. Push the samples

    python push_to_eax.py --url {push_url} --user <your user name>

It asks for your password (or give it with `--password`). On a laptop with a self-signed certificate add
`--no-verify`. Other ways of signing in are below.

It prints how many records each file holds and EA Explorer's answer, such as
"5 new or changed found, 0 unchanged: a delivery waits for review".

## Signing in

Use whichever your organisation uses; each acts as its owner, with that owner's rights on the model (someone who may
load into it), and every call is in EA Explorer's change log.

| How | Command line | From Python |
| --- | --- | --- |
| **User name and password**: an EA Explorer account, or your **Active Directory** (LDAP) account when EA Explorer signs in against the directory | `--user <name>` (and `--password`, or be asked) | `push_dataframe(url, df, "name", "password")` |
| **Personal token**: for people who sign in with **single sign-on** (Entra ID, Google and the like), whose password EA Explorer never sees. Sign in to EA Explorer in the browser, then System admin > Machine access > New token (everyone may make their own), with read-write on *Models and content* | `--token eaxt_...` | `push_dataframe(url, df, token="eaxt_...")` |
| **API key** of a service account: for a system that pushes on its own (a nightly job). Made by a Super Admin or IT Admin in System admin > Machine access | `--token eaxk_...` | `push_dataframe(url, df, token="eaxk_...")` |
| **Client certificate** (mutual TLS): a certificate a Super Admin or IT Admin has trusted in System admin > Machine access. Use the same address on the machine-access port, `https://<server>:9443/api/v1/...` (or the port set as `EAX_MTLS_PORT`) | `--cert client.pem --key client.key` | `push_dataframe(url, df, cert=("client.pem", "client.key"))` |

`sign_in()` in the script shows how each one is sent: a token as `Authorization: Bearer ...`, a certificate in the TLS
connection, a user name and password as HTTP Basic.

## 3. Review the delivery

In EA Explorer open the model, then **Import and export > Deliveries**: the delivery shows what is new, changed and
kept. A Committer, Model Sub Admin or Model Admin accepts it (it is committed, and can be undone like any load) or
declines it. Nothing reaches the model before that.

Push the same files again and only what changed is delivered. Rename a record and it arrives as a new element (the
old one stays: a delivery never deletes).

## 4. Use your own data

* **One CSV file per set** of records; name the file after the entity type it holds (`Application Component.csv`).
* Columns: `id` (a key of your own, unique in the file), `name`, `description`, then any attribute of the type by its
  name. Leave a cell empty when you have no value.
* **Relationships**: a column named after a relationship type (such as `Serving`) holding the `id` of a record in
  another file. Push the related files together (the script sends the whole folder at once).
* From your own Python code: build a pandas DataFrame and call

      from push_to_eax import push_dataframe
      answer = push_dataframe("{push_url}", df, "user", "password", set_name="Application Component")
      answer = push_dataframe("{push_url}", df, token="eaxt_...", set_name="Application Component")

What EA Explorer does with the records is described on the model's Discovery tab and in the help (Discovery).
