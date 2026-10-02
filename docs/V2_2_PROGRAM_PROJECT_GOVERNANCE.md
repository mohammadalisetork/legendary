# Release 2.2 — Program and Project Governance

## Scope

Release 2.2 adds demand-side Program/Project governance to the existing V1 request system. It does not add department hubs, approvals, priority credits, analytics exports, or other 2.3 work.

## Data model

- `Program` has a stable unique code, name, description, and lifecycle (`DRAFT → ACTIVE → DISABLED/ARCHIVED`; a disabled item can return to active; archived is terminal).
- `Project` belongs to one Program. Its parent cannot be changed after creation. A Project can accept new requests only while both it and its Program are active.
- `RoleAssignment` now represents Program Manager assignments at Program scope and Project Manager assignments at Project scope. Existing global and Department-scoped assignments remain supported. Deactivation is soft and timestamped.
- `Request.program` and `Request.project_entity` are nullable protected foreign keys. The legacy `Request.project` free-text field remains intact. Submitted canonical requests store Program/Project name and code snapshots plus the submitter's selected role; submission history records those values.

Migration `0008_program_project_governance` only adds nullable request links and new governance tables/role scopes. It does not infer or rewrite legacy free-text values, delete rows, reset migrations, or backfill ambiguous relationships.

## Request entry and visibility

- A Program Manager chooses one of their active Programs, may select an active child Project, and chooses the Program Manager role context.
- A Project Manager sees only assigned active Projects; the server derives Program from that Project. A client-submitted Program/Project mismatch is rejected.
- Existing requesters without demand-side assignments retain the V1 free-text field and request workflow. Deprecation is staged: keep `Request.project` readable and writable on the legacy requester path in this release; use Program/Project foreign keys as canonical context only for assigned demand managers; after a reviewed legacy mapping and client transition in a later release, make the text field historical/read-only before considering removal.
- A Program Manager can read submitted requests for their Programs across provider Departments. A Project Manager can read submitted requests for assigned Projects. Managers can also see their own drafts. Other managers' drafts are hidden.
- Demand-side detail is read-only. It exposes requester-visible conversation and authorized attachments, but no internal notes. Existing provider queue and Department mutation checks remain separate and unchanged.
- Program and Project lifecycle and assignments are checked again when a draft is submitted, so stale or deactivated selections cannot be submitted.

## Administration and dashboard

Super Admin can create/edit Programs and Projects, inspect counts and assignments, and add or deactivate scoped managers. Assignment and lifecycle actions produce ActivityLog records. The Program dashboard summarizes visible requests by Program, Project, provider Department, status, and overdue timing. It does not change provider queue behavior.

## Legacy-data and future V2 considerations

Existing requests stay unlinked unless an administrator later maps them using approved business data. Their original `project` and `requesting_unit` text remains available. A future migration must preserve those columns and request history, derive provider Department from the linked Service, and use an explicit reviewed mapping for Program/Project; string matching is not a safe automatic mapping.

The eventual relationship can evolve as `Request → Program / Project → Department → Service Family → Service` without deleting V1 requests. Department membership and demand-side Program/Project scope are distinct dimensions. Provider queue authorization must continue to intersect the provider's Department scope even when that user also holds a demand-side role.

Future priority allocation must be keyed by exactly `Program × Department × Priority × Allocation Period`, with transactional reservation/ledger handling. Program-only quotas would incorrectly couple Departments. The current schema does not implement quotas, multi-level approvals, Department hubs, or analytics exports; these remain later-release architecture work. No PostgreSQL server, Docker engine, or interactive browser is available in this execution environment, so those runtime/build and visual checks are not verified here.

## Verification added

`portal/test_release_2_2.py` covers model lifecycle and scope constraints, Program/Project request visibility, read-only behavior, internal-note privacy, attachment authorization, draft privacy, provider-scope isolation, submission snapshots, stale assignment rejection, selector scoping, Super Admin management, and dashboard aggregation.
