# Warehouse-as-Code (Overview)

This repo is a **map, not a model**: it gives an overview of the whole
"declarative WMS-as-concept" domain and says which sibling repo (if
any) currently owns which part of it. It defines no schemas, has no
CI, and is not itself validated - it exists purely so that someone
new to this project family doesn't have to open every sibling repo's
README to understand the overall shape.

None of the sibling repos implement a real WMS. Each describes, as
version-controlled YAML validated by JSON Schema, the **desired
structure/rules** of one concern - analogous to Terraform: the code
describes a design, not a running system, and none of it is meant to
become production software.

## Why a separate repo for this

Each sibling repo already documents itself well, but nothing documents
the *landscape* - which WMS capability areas exist at all, which of
them are modeled somewhere, and which are deliberately still blank.
That question doesn't belong to any single sibling repo (least of all
one that doesn't exist yet), so it gets its own home here.

## Domain Map

| Domain | Status | Owner |
|---|---|---|
| Physical warehouse structure (storage points, lanes, WCS, movement/replenishment rules) | Modeled | [`Topology-as-Code`](https://github.com/rhinos07/Topology-as-Code) |
| Order splitting & fulfillment orchestration (order/sub-order lineage, split/completion rules, order-target vs. movement-target) | Modeled | [`OrderOrchestration-as-Code`](https://github.com/rhinos07/OrderOrchestration-as-Code) |
| Item/article master data (item master, packaging/UOM hierarchy, sourcing & lifecycle) | Referenced, not yet built | `MasterData-as-Code` (planned, doesn't exist yet) |
| Inventory / stock (on-hand, reservations, allocation state) | Not modeled | - |
| Wave / batch planning | Not modeled | - |
| Task execution (`ExecutionTask`/`FulfillmentResult` - the runtime instantiation of a `process_type`/`movement_rule.trigger`) | Deliberately out of scope everywhere | Runtime WMS/WES system, not a "-as-Code" repo |
| Slotting optimization | Deliberately excluded (analytics/runtime territory) | - |
| Labor management | Deliberately excluded | - |
| Yard management | Deliberately excluded | - |

"Not modeled" = nobody has started; "deliberately excluded" = a
sibling repo's own README explicitly rules it out as runtime state,
not structure.

## Shared Principles Across Sibling Repos

Every sibling repo follows the same pattern, established first in
`Topology-as-Code`:

- **Structure vs. strategies vs. runtime**: physical/structural shape
  changes rarely and gets strict review; process rules/strategies
  change frequently and get lenient review; live/runtime state (actual
  inventory, live orders, warehouse tasks) is deliberately **not**
  modeled here at all - it lives in the real WMS/OMS runtime database.
- **`elements/`**: small reusable catalogs (rack templates, split
  reasons, process types, ...) referenced by ID from the structure/
  strategy files, not duplicated inline.
- **JSON Schema validation** of every YAML file, plus a `tools/validate.py`
  that also checks cross-file references within the repo.
- **`docs/entity-glossary.md`** per repo as the canonical definition of
  that repo's vocabulary.

## Shared Vocabulary Across Repos

A few IDs are meant to mean the same thing across repos but are
currently duplicated rather than centrally owned, by deliberate choice
(see each repo's own README "Shared Vocabulary" section) - only worth
extracting into a real shared-catalog repo once duplication actually
causes drift:

- `process_types` (`Topology-as-Code`) - referenced by
  `movement_rule.trigger` there and `workflow_trigger.trigger` in
  `OrderOrchestration-as-Code`.
- `load_unit_types` (`Topology-as-Code`) - referenced by
  `order-position.schema.json`'s `load_unit_request.load_unit_type` in
  `OrderOrchestration-as-Code`; candidate to move to `MasterData-as-Code`
  once that exists.
- `item_id` (`MasterData-as-Code`, once it exists) - referenced by
  `order-position.schema.json`'s `material_request.item_id`.

## Open Questions

- Whether to extract a shared-vocabulary repo (see above) - deliberately
  deferred until duplication causes real pain.
- Everything under "Not modeled" above.

## Non-Goals

This repo will not gain schemas, CI, or its own `elements/`/`customers/`
structure. If a new domain gets modeled, it gets its own sibling repo
(or an existing one is extended) and this file's Domain Map table is
updated to link to it - the map stays a map.
