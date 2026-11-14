"""Push CSV files to an EA Explorer model: a worked example of a discovery Push source.

What it does
------------
1. Reads every .csv file in a folder (one file per set of records, the file's name is the set's name: the sample
   "Application Component.csv" holds application components).
2. Sends them, in one call, to the model's Push source: HTTP POST of JSON shaped like an OData answer,
   {"<set>": [ {field: value, ...}, ... ], ...}.
3. EA Explorer turns what is new or changed into a **delivery** for the model: nothing changes in the model until a
   Committer, Model Sub Admin or Model Admin accepts it (Import and export > Deliveries).

Signing in (any one of these; see README.md)
--------------------------------------------
* user name and password    --user (and --password, or be asked): an EA Explorer account, or your directory (AD)
                             account when EA Explorer signs in against it
* token or API key          --token: a personal token (eaxt_...) or a service account's API key (eaxk_...) from
                             EA Explorer's Machine access; the way for single sign-on users and for systems
* client certificate        --cert (and --key): a certificate an administrator has trusted in Machine access, sent
                             to the machine-access port (https://<server>:9443/...)

How EA Explorer reads the records
---------------------------------
* The set's name (the CSV file's name) is matched to an entity type of the model by name.
* The column "id" is each record's key, "name" its name, "description" its description; other columns are matched to
  the type's attributes by name.
* A column whose values are the ids of another set is a relationship; the column's name says which relationship type
  (the sample's "Serving" column holds the ids of the elements each one serves).
* Push the same file again and only what changed is delivered.

Run it
------
    python push_to_eax.py --url <the Push address> --user <user name> [--password <password>] [--folder samples]
    python push_to_eax.py --url <the Push address> --token eaxt_...
    python push_to_eax.py --url <the Push address on port 9443> --cert client.pem --key client.key

Add --no-verify on a laptop whose certificate is self-signed. See README.md for setting up Python.
"""

import argparse
import getpass
from pathlib import Path

import pandas as pd
import requests


def push_dataframe(url, df, username=None, password=None, set_name="records", token=None, cert=None, verify=True):
    """Sends one DataFrame to EA Explorer as one set of records and returns EA Explorer's answer (a dict).

    url       the Push address, https://<server>/api/v1/import-sources/<source id>/push
    df        a pandas DataFrame: one row a record, one column a field
    username  your EA Explorer user name, with password (HTTP Basic)
    set_name  what the records are; matched to an entity type of the model by name
    token     instead of a user name: a personal token or an API key (sent as a Bearer token)
    cert      instead of either: a client certificate, "client.pem" or ("client.pem", "client.key")
    verify    False to accept a self-signed certificate (a laptop)
    """
    return push_dataframes(url, {set_name: df}, username, password, token=token, cert=cert, verify=verify)


def push_dataframes(url, frames, username=None, password=None, token=None, cert=None, verify=True):
    """Sends several DataFrames in one call: {set name: DataFrame}. Send related sets together, so a column holding
    another set's ids becomes a relationship. Signs in as push_dataframe does."""
    body = {name: df.fillna("").to_dict(orient="records") for name, df in frames.items()}
    response = requests.post(url, json=body, verify=verify, timeout=120, **sign_in(username, password, token, cert))
    print(f"EA Explorer answered {response.status_code}")
    return response.json()


def sign_in(username=None, password=None, token=None, cert=None):
    """How the call signs in, as arguments for requests: a token, a client certificate, or a user name and password."""
    if token:
        return {"headers": {"Authorization": f"Bearer {token}"}}
    if cert:
        return {"cert": cert}
    return {"auth": (username, password)}


def read_folder(folder):
    """Every .csv file in a folder as {file name without .csv: DataFrame}, every value read as text."""
    return {path.stem: pd.read_csv(path, dtype=str, keep_default_na=False) for path in sorted(Path(folder).glob("*.csv"))}


def main():
    parser = argparse.ArgumentParser(description="Push CSV files to an EA Explorer model's Push source.")
    parser.add_argument("--url", required=True, help="the Push address shown on the model's Discovery tab")
    parser.add_argument("--user", help="your EA Explorer user name (signing in with a password)")
    parser.add_argument("--password", help="your password (asked for when left out)")
    parser.add_argument("--token", help="a personal token (eaxt_...) or an API key (eaxk_...) instead of a user name")
    parser.add_argument("--cert", help="a client certificate file (PEM) instead of a user name")
    parser.add_argument("--key", help="the client certificate's private key file, when it is not in --cert")
    parser.add_argument("--folder", default="samples", help="the folder holding the CSV files (default: samples)")
    parser.add_argument("--no-verify", action="store_true", help="accept a self-signed certificate (a laptop)")
    args = parser.parse_args()

    password = args.password
    if args.user and not password:
        password = getpass.getpass(f"Password for {args.user}: ")
    cert = (args.cert, args.key) if args.cert and args.key else args.cert

    frames = read_folder(args.folder)
    for name, df in frames.items():
        print(f"{name}: {len(df)} records")

    answer = push_dataframes(args.url, frames, args.user, password, token=args.token, cert=cert,
                             verify=not args.no_verify)
    print(answer.get("message", answer))


if __name__ == "__main__":
    main()
