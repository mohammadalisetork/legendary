# Release 2.4 — Catalogue and Department Scaling

Parent: `release/2.3-priority-capacity-approval-engine` at `5d3b32283bed66dd5d0cd101f23eda306b2f142a`. Release 2.4 builds on the existing Django application, scoped Department policies, and 2.3 governance. It does not implement 2.5 analytics or PDF reporting.

## Department setup and lifecycle

Super Admin creates a Department in draft from `/control/departments/new/`. The Department workspace acts as a guided setup: edit its public description and optional cover image, add operational members, create Service Families and Services, define each service form, review the Department preview, and publish when the minimum catalogue exists. Department Leads can manage only their assigned Departments. Publishing requires at least one active family and one active service.

Department states are `DRAFT`, `PUBLISHED`, `DISABLED`, `TEMPORARILY_DISABLED`, and `ARCHIVED`. Only `PUBLISHED` accepts new requests. Temporary disable and disable preserve existing requests and assignments. Archive is terminal in the application flow. Families and Services use `ACTIVE`, `DISABLED`, and terminal `ARCHIVED` lifecycle values alongside their existing active flags for compatibility. Hard deletion is not part of catalogue management.

An optional cover accepts PNG, JPEG, WebP, or GIF up to 3 MiB and is stored through Django's configured default storage. The upload extension and file signature are checked. The short name remains the fallback visual mark.

## Catalogue and OLA

The canonical catalogue stays `Department → Service Family (Category) → Service → Request Form`. Family and Service management keeps Department scope server-side. Existing Service data remains editable, including purpose, scope, deliverables, required inputs, requirements, exclusions, acceptance criteria, owner, response target, review target, delivery range, maximum duration, and desired-date support. The manager workspace provides server-side search through the existing requester catalogue and numeric display ordering in management forms.

New requests require a published Department and active family and service. Disable or archive removes catalogue entry for new submissions while historical requests remain addressable. The existing owner eligibility policy still validates the owner against the owning Department. Timing values continue to feed the existing OLA/SLA timing code.

## Dynamic Form Builder and snapshots

Use **فرم پویا** from the Service row in Department management. Fields can be added, edited, ordered with `display_order`, previewed in a non-submitting manager-only form, and deactivated without deletion. Types are short text, long text, number, select, radio, multiselect, checkbox, date/Jalali, email, phone, and file. Choice fields require a JSON array of options; field keys remain unique per Service. Dates use the existing Jalali widget. Files retain the current request upload validation and storage behavior.

Each Request stores the Department, Family, Service summary, OLA values, and dynamic field definitions/options at first save. Request detail, brief labels, and historic data rendering use these snapshots where applicable. Migration `0010` backfills existing requests using the catalogue values present at upgrade time. It cannot infer historical labels or descriptions that were changed before Release 2.4; those values are therefore a point-in-time baseline, not reconstructed history.

## XLSX import and export

Download a department-specific workbook template from `/control/departments/<id>/catalogue/template.xlsx`. The `Services` sheet columns are:

`action`, `family_slug`, `service_code`, `name`, `domain`, `short_description`, `full_description`, `purpose`, `scope`, `deliverables`, `required_inputs`, `request_requirements`, `process_information`, `excluded`, `service_role`, `acceptance_criteria`, `legacy_sla`, `initial_response_days`, `review_target_days`, `delivery_min_days`, `delivery_max_days`, `maximum_duration_days`, `supports_desired_date`, `default_owner_username`, `active`.

`CREATE` requires a previously unused code, `UPDATE` requires an exact existing code in the same Department, and `SKIP` explicitly leaves the row unchanged. Matching is exact and no fuzzy matching occurs. Validation checks exact headers, duplicate row codes, service code conflicts across Departments, selected family state, manager eligibility, active booleans, required data, OLA ranges, formulas, `.xlsx` structure, 5 MiB upload limit, and a 10,000-row limit. No file is persisted. The preview creates a metadata/audit batch but does not write Service rows. Confirmation is explicit and applies all valid rows in one database transaction; a failed row rolls back the whole confirmation. Preview, file size/hash, uploader, confirmer, row counts, status, and errors are stored on `CatalogueImportBatch`.

The Export action at the Department workspace supports Department scope; `/control/catalogue/export.xlsx` also accepts `department`, `family`, and `active` filters. It is available to Super Admin and in-scope Department Leads only. Export events are audited. Excel text is handled as data by openpyxl; workbook formulas in uploads are rejected.

## Permissions and audit

The existing centralized policy remains authoritative. Every field-management, import, template, and export view checks `CATALOGUE_MANAGE` on the target Department. Request-manager and read-only supervisor/executive roles do not receive catalogue write/export access. Foreign Department family, Service, owner, and batch IDs are scoped again at lookup/confirmation time. Catalogue updates, lifecycle changes, field changes, import preview/confirmation, and export write `ActivityLog` entries. There is no new role or global permission bypass.

## Migrations and data safety

Migrations `0010`–`0012` are additive: lifecycle and visual fields, import audit batches, request snapshots, constraints, and form field type choices. `0010` maps legacy `active=False` values to the new `DISABLED` lifecycle value and snapshots existing requests. No Department, family, Service, form field, request, Program/Project, credit, approval, SLA, history, or attachment row is deleted. Migration history remains intact. The Market Development seed catalogue is not edited by these migrations.

Before production upgrade, take database and media backups, apply `manage.py migrate`, and verify the migrated request/catalogue totals. Department image files use the configured storage backend and should be backed up with request attachments.

## Known limitations and 2.5 handoff

- The Department onboarding is a guided workspace checklist with a preview and publish gate; it is not a multi-page stateful wizard.
- XLSX import supports the service catalogue and OLA fields. It does not import Department membership, families, dynamic form definitions, credit allocations, Programs, or Projects. Families and form definitions are managed in the application workspace.
- Field order uses a numeric order field rather than drag-and-drop. Complex conditional logic, calculated fields, and arbitrary scripts are not supported.
- Form snapshots preserve the definitions at request creation. Existing records are backfilled from current definitions, so earlier unlogged catalogue edits cannot be reconstructed.
- OLA snapshot values are recorded for history; later operational timing continues to use the already stored request timing fields and does not recompute old requests.
- Live PostgreSQL concurrency, Docker image build, external object storage, browser/E2E, and production reverse-proxy operation must be verified in CI/staging if the current execution environment does not provide those services.

Release 2.5 remains responsible for executive BI, analytical fact/dimension read models, Program × Department reporting, KPI analytics, PDF report composition, and analytics drill-down. The 2.3 credit allocation key remains `Program × Department × Priority × Allocation Period`.
