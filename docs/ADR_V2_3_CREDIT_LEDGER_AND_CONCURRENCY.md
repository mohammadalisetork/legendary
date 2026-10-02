# ADR — Credit ledger and concurrent reservation

Status: Accepted for Release 2.3.

## Decision

A wallet is one `CreditAllocation` identified by **Program × Department × PriorityPolicy × AllocationPeriod**. A unique database constraint prevents duplicate exact keys. Active overlapping period ranges for the same Program/Department/Priority are rejected by model validation while locking the Program row for administrative writes. The matching active wallet for the current date must be unique. Each request has at most one `CreditReservation`. `CreditLedgerEntry` records a unique RESERVE, CONSUME, and/or RELEASE event per reservation. Capacity is `allocation.quantity - RESERVED count - CONSUMED count`; RELEASED does not reduce capacity. The ledger and history retain their actors/timestamps. The application never edits or deletes a ledger entry.

Submission locks the request with `select_for_update`, resolves its current wallet, locks the allocation row with `select_for_update`, recalculates capacity, then writes reservation, ledger, request submission, and initial approval case inside one `transaction.atomic`. At the final approval decision, the request, case, and step are locked; the reserved transaction is resolved with the allocation lock. The reservation and ledger unique constraints prevent duplicate effects. Repeated final decisions fail before changing state. Post-decision notification and request history write within the same transaction. A rollback leaves the credit count unchanged.

Admin allocation writes lock the parent Program and allocation row before revalidating overlapping periods and minimum committed quantity. Period edits lock all currently associated Programs before overlap validation. Deployment must use PostgreSQL for the row locks; SQLite is supported for development and tests but does not provide equivalent concurrent `SELECT FOR UPDATE` behavior. A `TransactionTestCase` with two simultaneous submissions for one credit is enabled only on PostgreSQL. Run it against a staging PostgreSQL service before rollout. The production database's default READ COMMITTED isolation is assumed for fresh capacity reads after waiting on the allocation lock. Do not bypass model/domain services with bulk SQL updates to wallet, reservation, or period rows.

An already consumed credit remains consumed through later provider cancellation/rejection. Pending priority cancellation or rejection releases only a RESERVED credit. Resolution never silently reverses CONSUMED. A future refund would need a new audited event and explicit approval policy; no such operation is shipped here.

## Alternatives and consequences

A mutable balance counter alone makes retries and audits difficult. Counting reserved/consumed rows under the allocation lock keeps one durable source of truth and makes each transition traceable. A single Program-wide wallet was rejected because different provider Departments must not share capacity. Preexisting historical requests are excluded from the ledger so an upgrade does not fabricate consumption. If an administrator deactivates an allocation with reservations, existing decisions can still resolve the linked wallet, while new submissions cannot reserve it.
