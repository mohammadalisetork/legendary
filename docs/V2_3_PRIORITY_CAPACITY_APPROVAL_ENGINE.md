# Release 2.3 — Priority Capacity and Approval Engine

Parent: `release/2.2-program-project-governance` (`19be044e3207777c1b7cd8ab090a4e961bd4a244`). This release adds governance without changing historical request contexts or replacing V1 status/history.

The remote 2.2 tree contained four truncated blobs: its 2.2 architecture note, migration `0008`, release test, and Program dashboard template. Their complete audited 2.2 workspace versions are restored verbatim in the 2.3 commit. This is a source-delivery repair, not a 2.2 behavior change. All other unchanged parent files were byte-identical to the 2.2 workspace snapshot.

## Deployment and migration

Apply `portal.0009_priority_capacity_approval_engine` after 2.2 with `python manage.py migrate`. It adds new tables, extends the request priority column, adds `provider_hold=False`, and expands the global role constraint for `SENIOR_APPROVAL_AUTHORITY`. Existing requests, priorities (`LOW`, `URGENT`), status, free-text projects, attachments, and audit rows stay as they are. No old requests receive credit transactions or inferred Program/Department mappings. The migration seeds four active priority policies (`NORMAL`, `HIGH`, `VERY_URGENT`, `EMERGENCY`), two project-manager priority rules, two provider referral rules, and the generic senior authority configuration. It does not allocate credits or assign approvers. Take the usual database and media backups before applying.

A super admin configures allocation periods, credit allocations, priority metadata, approval rules, senior title/status, and active senior members at **اعتبار و تأیید** (`/capacity/`). A Program/Project Manager can see only capacity of assigned Programs there. Enter dates as Gregorian ISO in the administrative period form; other user-facing request dates remain Jalali. For a credit-governed priority, create a current active allocation for each required **Program × provider Department × Priority × Period** before users submit. The application rejects absent, inactive, expired, overlapping, or exhausted wallets; it does not downgrade the priority. Period kinds are labels; start/end dates determine applicability.

## Request and credit lifecycle

| Event | Request | Credit | Approval |
|---|---|---|---|
| Draft | DRAFT | None | None |
| Project Manager submits Very Urgent/Emergency | SUBMITTED, provider hold | Reserve one atomically | Program Manager step pending |
| Program Manager approves final step | SUBMITTED, provider hold cleared | Consume reserved credit | Approved |
| Program Manager rejects | REJECTED | Release reserved credit | Rejected |
| Requester cancels before decision | CANCELLED | Release reserved credit | Cancelled |
| Program Manager submits own credit-governed request | SUBMITTED | Reserve then consume in one transaction | Audited automatic approval |
| Normal/High request | SUBMITTED | None | None by default |

A consumed credit is **not** automatically refunded if a request later becomes cancelled or rejected in provider processing. This initial cancellation policy is centralized in `portal/governance.py`; an explicit reversal policy would require a future audited operation. An approved request does not enter the provider queue before the final required step. Existing noncredit and historical requests retain prior behavior. An administrative change to future allocation or policy does not rewrite existing reservation or approval history.

The request form queries the server for remaining capacity in the selected authorized Program/Project and the service's Department. It warns and asks for explicit confirmation for the last credit, blocks final submit at zero, and retains draft capability. Final submission repeats all context, policy, capacity, and last-credit checks inside a transaction. A Program/Project Manager shares the Program wallet within the same Department; other Departments have separate wallets.

## Approval workspaces

Active Program Manager assignments approve only their Program. A separate active global senior authority assignment and enabled senior configuration govern senior decisions. Requesters and provider referrers cannot approve their own requests/referrals even if they hold another role. The Program Manager's own priority request takes the documented automatic path with audit. Cross-Program and cross-Department access are checked at each read or mutation, including downloads.

An authorized provider can request Program Manager or senior approval from the request detail, recording a reason, assessment, estimated time/cost, conditions, recommendation, risks, and a private optional file. The inbox (`/approvals/`) and decision screen display pending, approved, and rejected cases. Steps can be approved, rejected, or marked as needing clarification. The original referrer sends a recorded explanation and optional private attachment before the pending step resumes. Clarification does not consume/release credit. Multiple ordered policy steps are supported. Decisions append `ApprovalDecision` rows and request history, create notifications, and are idempotent against a repeated final decision. Provider referral rejection does not change the original request's status or credit. Provider assessment files use a separate private attachment model and route; the requester cannot retrieve or see the private assessment, while public request comments/attachments and internal notes keep their existing rules.

The request journey shows credit reservation/consumption/release, approval requests/decisions, and pause/resume events. The requester sees approval type/status without provider-private assessment. Admin inspection of ledger and decisions is read-only in Django Admin; app-level settings are at `/capacity/`.

## Timing

Each approval rule carries `pauses_sla`. Pending approval steps preserve started/decided timestamps even when SLA pause is disabled. Operational elapsed time removes the union of existing request-status pauses and configured approval pauses, so overlapping intervals are not double-counted. Effective initial-response and maximum-delivery deadlines include elapsed working time paused for approval; the original stored estimates remain untouched. End-to-end elapsed time, provider operational time, Program wait, senior wait, and total approval wait are available on `Request`. Approval wait durations are elapsed wall time; operational deadlines use the current working calendar. Existing historical request SLA data is not backfilled or rewritten.

## Verification in this environment

`manage.py check`, `makemigrations --check --dry-run`, the full Django suite (98 tests; 97 passed, PostgreSQL-only race test skipped), and the upgrade test from 2.2 were executed. Fresh migration, production settings check, static collection, WSGI bootstrap, and `/health` passed with an isolated local SQLite database. The PostgreSQL simultaneous-last-credit test is defined in `portal/test_release_2_3.py` but requires a PostgreSQL test service; SQLite cannot establish row-lock semantics. See `ADR_V2_3_CREDIT_LEDGER_AND_CONCURRENCY.md` for lock order and production verification. Docker and live PostgreSQL were unavailable; socket binding for Gunicorn was denied by the agent environment although `gunicorn --preload --check-config` succeeded. Browser visual review was unavailable.

## Operational limitations and later releases

- An allocation period and credit policy must be configured before use. No automatic recurring allocation or rollover runs in this release.
- The approval inbox loads scoped cases into application memory; pagination/index tuning is a later scaling concern. There is no BPMN designer or general rule expression language.
- The local database test proves transaction transitions and upgrade preservation; live PostgreSQL concurrency must be verified in CI/staging.
- No 2.4 catalogue import or 2.5 reporting/PDF/BI work is included.
