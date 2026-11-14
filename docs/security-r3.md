# Release 3: the security review (R3.12)

The owner, 13 Nov 2026: "Create a new story for R3 called security testing of Entire R3". Done on 13 Nov 2026 by reading
everything Release 3 adds as someone with each role would try to misuse it, then fixing what was found, each fix with a
test that fails without it (D599). The self-test's own security checks (the role and cross-user API matrix, the negative
tests, the database checks, the dependency audit, the image scan, the ZAP scan) run over all of it on the owner's next
full test.

## Found and fixed

| What | The risk | The fix | Tests |
| --- | --- | --- | --- |
| Discovery sources (the epic): the sign-in setting | Anyone who may change a model could name **any** setting (the database's password, say) as a source's sign-in and point the source at their own server, which would receive it | Only settings named `EAX_SOURCE_...` may be sent (and `EAX_AI_...` for the AI engine's key); checked when saved, when sent, and by the database (D671) | test_discovery.py: `test_a_source_may_not_send_another_setting_of_the_installation`, `test_the_ai_engine_may_only_send_its_own_key`, `test_the_database_holds_the_same_rule` |
| Discovery sources: the address | A feed, its next pages or a redirect could point inside: EA Explorer's own services (`http://db`, `http://ops:9000`), the machine, a private network or cloud metadata (server-side request forgery) | Every address, page and redirect is checked before it is read: its own services, the machine, private, link-local, reserved and multicast addresses are refused unless IT lists the host in `EAX_DISCOVERY_ALLOWED_HOSTS` (D671) | `test_internal_and_private_addresses_are_refused`, `test_it_lists_the_hosts_it_may_read_inside`, `test_reading_refuses_before_any_request_and_on_a_redirect` |
| Pushes | A push of any size | At most 50,000 records a push (and the front door's 100 MB) | `test_a_push_is_limited` |
| The screens | No Content-Security-Policy (R2.24 part 3, moved here) | Enforced on the screens: scripts only from this site (and Keycloak's one-line sign-in page, by its hash), no eval, no plugins, frames and forms only to this site; draw.io, the API's own pages, Keycloak, Reports and Documents keep their own; `EAX_CSP_HEADER=Content-Security-Policy-Report-Only` only reports (D672). The self-test now fails a page the policy breaks and fails a missing policy | test_csp.py |
| Images: findings that stayed after R2.24 | A clean rebuild kept building on the base image Docker first downloaded, so its fixes never arrived | `clean-restart`, `clean-run` and `clean-debug` fetch the current base images first and build on them, in every form of eax (D673); nginx moved from 1.27 (no longer fixed) to the 1.30 stable line | test_fresh_bases.py |

## Checked, nothing to fix

| What | Checked |
| --- | --- |
| The API test harness (R3.16) | IT and Super Admins only; writes only into test data (refused before sending otherwise); every call audited |
| Watching a run (R3.2), coverage (R3.10) | IT and Super Admins only; run files read only inside work/tests (a path that leaves it is refused: `test_the_api_reads_run_files_inside_work_tests_only`) |
| The file explorer (R3.5) | IT and Super Admins only; several at once are single writes, each checked and audited (D668); secrets never shown or zipped (`test_several_in_one_zip_without_secrets`); a read-only mount is read only |
| Users with projects (R3.3) | User Admins only, as before |
| Text indexes (R3.7) | Indexes only; queries still bound their values |
| Discovery (the rest) | Setting up, looking, running and confirming matches need a role that changes the model; a push needs the source's service account or that role; nothing reaches a model without a person accepting the delivery; documents are sent to the AI engine as data, and its answers are only proposals; values shown on screen are text, never markup |
| eax screen (R3.1) | Runs the same commands as typing them, as the person at the terminal |
| Negative tests (R3.9) | Write only into the run's test data or to ids that are never there |

## Left open, with the reason

| What | Why | Next |
| --- | --- | --- |
| Reports (Apache Superset 4.1.2): the image scan's findings | Most are in Superset itself and its Python packages; the fixed releases are Superset 5 and 6 (6.1.0 is current). Moving two major versions changes its configuration and the dashboards' import, which needs testing on an installation | R4.7: Superset 6.1, tested (the dashboards, the sign-in, reports-init). The Debian and Python fixes that apply to 4.1 are applied at build (R2.24) |
| Findings with no fix in the base images' current release | Nothing to install until the distribution ships one | The next clean rebuild fetches them when they come (D673); the self-test's image scan lists what remains |
