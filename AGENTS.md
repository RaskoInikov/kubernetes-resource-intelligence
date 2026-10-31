# Development Workflow

## Source of truth

- docs/PRODUCT.md defines intended user behavior and scope.
- docs/ARCHITECTURE.md defines component responsibilities.
- docs/CONTRACTS.md defines data interfaces.
- docs/ROADMAP.md defines implementation order and acceptance criteria.
- docs/DECISIONS.md records architectural decisions.
- docs/PROGRESS.md records verified implementation status.

Read only the documents relevant to the current task.

## Working process

For each requested task:

1. Inspect relevant existing code and documentation.
2. Identify the desired behavior and affected component boundaries.
3. Implement the smallest complete change.
4. Add or update tests for successful and failure behavior.
5. Run relevant tests and static checks.
6. Update documentation when behavior or interfaces change.
7. Update docs/PROGRESS.md with verified results and remaining limitations.
8. Report changes, verification results, and unresolved issues.

Do not mark unfinished or unverified functionality as complete.

## Planning

Implement straightforward local tasks directly.

For cross-component design changes, update the relevant design documents
before implementation.

If the requested change conflicts with an accepted architectural
decision, explain the conflict rather than silently expanding scope.

## Scope

Implement only the requested milestone.

Do not introduce unrelated components, abstractions, infrastructure,
or features.

Preserve established interfaces unless their change is explicitly
part of the requested task.

## Data integrity

Keep raw observations, normalized data, calculated statistics,
retrieved evidence, and generated explanations distinguishable.

Never fabricate monitoring data or silently replace missing values
with zero.

Every analysis must have traceable source data and timestamps.

## Kubernetes safety

Read-only Kubernetes operations are the default.

Any persistent Kubernetes modification requires explicit approval
unless it is individually covered by a previously approved,
specific experiment operation.

Never apply an LLM-generated patch directly.

Keep experimental workloads restricted to explicitly disposable
resources.

## Verification

Use pytest, Ruff, mypy, and frontend checks where applicable.

Use fake or recorded external responses for offline tests.

Real-service verification must be clearly distinguished from
offline verification.

Never claim real integration success based only on mocks.

## Documentation

Keep documentation concise and current.

Record architectural decisions only when decisions actually change.

Do not duplicate lengthy implementation logs across documents.

## Completion

Every completed task must leave the repository in a reproducible,
documented, tested state.