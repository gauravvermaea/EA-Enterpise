# Security

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately, through GitHub's **Report a
vulnerability** (the repository's Security tab, private vulnerability reporting), with:

- the version (top left of the screens, or `eax status`) and how it is installed (laptop, server, cloud);
- what an attacker could do, and the steps that show it;
- anything that helps to reproduce it (requests, screenshots); never real secrets or other people's data.

You will hear back within a week. We agree a fix and a date to publish it with you, and credit you unless you would
rather not be named.

## Supported versions

The latest release receives security fixes. Each installation shows whether its version is still supported (System
Admin › Updates).

## What the project does itself

Every release is checked by the self-test's security suite: the headers and cookies at the front door, a baseline
web application scan, the images' and Python dependencies' known vulnerabilities. Secrets live only in the
installation's configuration file, never in the repository or its sample data.
