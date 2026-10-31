# WMS Implementation Guide

*For developers building a warehouse-management runtime (or an adapter for
an existing one) that reads and acts on the "Warehouse-as-Code" repo
family. This is the technical counterpart to
[`business-overview.md`](business-overview.md) — that page explains the
domain in plain language; this one describes the contract your code has
to satisfy.*

## 1. Mental model

The four sibling repos —
[`Topology-as-Code`](https://github.com/rhinos07/Topology-as-Code),
[`MasterData-as-Code`](https://github.com/rhinos07/MasterData-as-Code),
[`OrderOrchestration-as-Code`](https://github.com/rhinos07/OrderOrchestration-as-Code),
[`Allocation-as-Code`](https://github.com/rhinos07/Allocation-as-Code) —
are a **configuration layer**, not a running system. Nothing in them
executes. Every one of their READMEs says, in some form, "runtime state
doesn't live here." A WMS built against this family is the piece that
*does* live there: it reads their (compiled) output and owns everything
they explicitly declare out of scope — live inventory, live order status,
task assignment and execution, wave/batch planning.

[`WMS-POC`](https://github.com/rhinos07/WMS-POC) is the one existing
reference implementation of this pattern — deliberately small (an
in-memory order engine plus a toy inventory ledger), not production code,
but every pattern below is drawn from what it actually had to build to
make the four repos' example data run end to end. Where useful, this guide
points at the exact file in `WMS-POC` that demonstrates a pattern.

## 2. The five responsibilities

Building a conforming WMS means implementing all five of these:

1. Import and interpret `Topology-as-Code`'s **compiled** structure and movement rules.
2. Resolve `MasterData-as-Code` item references and apply its lifecycle/sourcing rules.
3. Drive `OrderOrchestration-as-Code`'s order/sub-order state machine — the core engine.
4. Execute `Allocation-as-Code`'s search configuration against your **own** live inventory.
5. Own everything none of the four repos model (§7) and check what none of them cross-validate (§8).

## 3. Topology-as-Code: importing structure

Don't parse the customer-facing YAML tree directly. Read the output of
`Topology-as-Code/tools/compile.py`, validated against
`schemas/compiled-topology-artifact.schema.json` — that artifact, not the
source YAML, is the actual WMS-facing contract.

The artifact gives you:

- `metadata.dataset_id` — the stable scope this dataset owns. Never reuse it for another building.
- `target.{wms_type, tenant, facility, building}` — where this applies.
- `import_policy.{mode, removal_policy, unmanaged_objects, require_plan_approval}` — how to apply it (see below).
- `artifact.content_hash` (`sha256:...`) — the idempotency key. Same hash in, no-op.
- `entities` — every building-owned entity (storage types/points, channels, sections, activity areas, work centers, doors, controllers, reporting points, equipment, telegram actions, `can_edge` connectivity, lanes/conveyor topology, movement rules, replenishment strategies, and - when configured - `bay`/`shelf` load groups and `route_aisle`s), each keyed by type, each item at least `{id: ...}`.

Import loop:

1. On each deploy, run `compile.py`, get a fresh artifact, and diff its
   `content_hash` against the last-applied one (`tools/plan.py` does this
   diff generically — creates, field-level updates, deactivations,
   conflicts).
2. Never physically delete. `removal_policy: deactivate` → deactivate the
   object; `removal_policy: reject` → surface a conflict and stop.
3. `unmanaged_objects` is always `preserve` — your importer must never
   touch a WMS object this `dataset_id` doesn't own, even implicitly.
4. If `require_plan_approval` is true, a human approves the plan output
   before `reconcile` mode applies it.

**Per storage point, when configured** (all optional, all static):

- `bay` / `shelf` — the field and shelf the point belongs to. The `bay`
  and `shelf` entities carry `max_weight` (field load, shelf load). Sum
  the **measured** (scale) weight of the load units on a bay or shelf and
  block further putaway when the limit would be exceeded. Do not compute
  the weight from item master data - the spec deliberately relies on the
  scale.
- `route_aisle` / `route_position` — the travel-path sort key. The
  `route_aisle` entity states its usable `entries` (`start`, `end` or
  both) and a default `sequence`. Your router picks the entry end per
  tour and sorts `route_position` ascending from `start`, descending from
  `end`. The level is not part of the key.
- `scan_code` — the check code on the location label; compare it with
  the scanned value to confirm the location.
- `storage_condition` (`ambient`/`chilled`/`frozen`) — matches the
  item's storage condition from MasterData.

Catalogs owned by `MasterData-as-Code` (load unit types, storage
conditions, UOM) appear in `Topology-as-Code/elements/` as pinned copies
(`elements/catalog_sources.yaml`); treat MasterData as their source.

What the artifact does **not** give you: current occupancy, current
equipment availability, the current operating mode of an aisle or
machine (inbound only / outbound only - a runtime switch), anything live. `storage_point` is a place goods
*may* go, not a record of what's there right now — that state is yours to
track in your own database from day one.

**Movement rules at runtime.** When routing a task, look up the
`movement_rule` for the relevant `from`/`to` pair and check `allowed`.
Respect `applies_to_policy`:

- `explicit_only` (typical for conveyor/automated areas): a route with no
  matching rule doesn't exist. Don't infer one just because both
  endpoints are physically connected — `Topology-as-Code`'s own README
  documents a real bug of exactly this shape (an `activity_area` id
  existed but no rule ever named it as a `to` endpoint under
  `explicit_only`, so it was unreachable despite existing — see §8).
- `default_allow` (typical for manual areas): allowed unless an explicit
  `allowed: false` rule says otherwise.

`movement_rule.trigger` references `elements/process_types.yaml` (e.g.
`putaway_task`, `pick_task`, `replenishment_task`, `cross_dock_task`).
That id is the hook your order engine uses to apply inventory side effects
(§5) — it's the same vocabulary `OrderOrchestration-as-Code`'s
`workflow_trigger.trigger` produces, so one enum serves both sides.

## 4. MasterData-as-Code: resolving items

Same pattern as topology: consume `MasterData-as-Code/tools/compile.py`'s
output, which already resolves `default_uom` inheritance (an item's own
value, falling back to its category's `default_attributes.default_uom`)
— don't re-derive that yourself.

Build an item resolver: `item_id -> {dimensions, weight, hazmat_classes,
default_uom, tracking, owner, storage_condition}`, plus the packaging
levels with their barcodes and load unit type.

- `tracking` (resolved field by field from the category) says what to
  capture: `lot` (`none`/`optional`/`required`), `expiry`
  (`tracked`, `min_remaining_at_receipt_days`, `total_shelf_life_days`),
  `serial.capture` (`none`/`outbound`/`always`). Enforce it at goods
  receipt and, for serials, at pick/pack.
- Barcodes are unique per owner across the company; a scan resolves to
  item **and** packaging level, so the quantity follows from the level.
- `owner` is set only in multi-owner warehouses (each item has exactly
  one owner); stock of different owners must stay distinguishable in
  your ledger. Use it twice: to validate `material_request.item_id` at
order intake (§8), and to interpret quantities/UOM at pick and putaway
time.

`sourcing.yaml` and `lifecycle.yaml` (season windows, active/discontinued,
substitution) are rules your WMS has to **apply**, not just store — e.g.
redirect an order line for a discontinued item to its declared substitute
at fulfillment time. The repo only declares that a substitution rule
exists; nothing in it executes the substitution.

## 5. OrderOrchestration-as-Code: the core engine

This is the heart of what you're building. Model it as an explicit state
machine per order/sub-order — `WMS-POC/poc/engine.py` is a working,
minimal example of exactly this engine; the description below follows its
shape.

**Get `target` vs. `order_target` right first — everything else depends
on it** (`order-header.schema.json`):

- `target` — the next reachable hop for *this* order/sub-order. Mutable,
  may legitimately differ per sub-order and from `order_target`.
- `order_target` — the immutable final business destination. Set once on
  the top-level order, inherited unchanged by every descendant unless a
  `split_rule.order_target_override` explicitly says otherwise.
- An order/sub-order is only **truly fulfilled** once its confirmed
  quantity is reached **and** `target == order_target`. Track both fields
  separately; don't collapse them.

**Status machine** (`structure/status.yaml`): `statuses[].{id, terminal}`
plus `transitions[].{from, to}`. Your engine's transition function must
reject any `(from, to)` pair not listed there — raise, don't silently
apply it.

**Splitting.** `split_rule.condition` (`split-rule.schema.json`) names a
*reason id* in `elements/split_reasons.yaml`; what selects and gates a
rule is `split_rule.when`: `when.dimension_value` is the value of
`split_by` the rule claims (e.g. a storage technology id from
Topology's `storage_technologies`), `when.status` the status the order
must have reached before the rule may fire (e.g. `receipt_confirmed` for
inbound putaway). What stays runtime is resolving each position's actual
value - which technology holds this stock is live inventory state - and
partitioning the quantity across the matched rules. `WMS-POC`'s
`Engine.split()` takes exactly that as input: `line_id ->
{dimension_value: quantity}`.

When you apply a matched `split_rule`, for each resulting sub-order:

- `target = rule.target_override or parent.target`
- `order_target = rule.order_target_override or parent.order_target`
  (the override is the documented exception to "`order_target` is
  immutable" — used for splits like inbound putaway where the split's
  destination genuinely *is* the new final destination, not an
  intermediate hop)
- positions carry `source_line_id` back to the parent; the parent's own
  positions are never mutated.

**Workflow trigger** (`workflow-trigger.schema.json`) maps
`split_rule.id -> trigger` (a `process_types` id). Use it to decide what
task your engine emits for the new sub-order, and to drive the inventory
side effect below.

**Completion.** On every terminal-status transition of a sub-order,
re-evaluate its parent's `completion_rule`s (`completion-rule.schema.json`):

1. If `when.source_split_rules` is set, scope to siblings created by
   those specific rules only — **always implement this filter.** Skipping
   it reproduces a real, previously-live bug: an unrelated sub-order that
   happens to also have `target != order_target` (e.g. because of an
   unrelated `target_override`) can spuriously satisfy a `target_gap`
   rule meant for a completely different split scenario.
2. Filter by `when.status`, then by `when.target_gap` if set (only
   children where `target != order_target` at that status — "confirmed
   but not actually there yet").
3. Apply `when.quantifier` (`all_children` / `any_child` / `n_of_m` + `n`)
   over the filtered set.
4. On a match, run exactly one `action`:
   - `update_parent_status` — drive the parent through your existing state machine.
   - `spawn_order` — create a new order whose positions are
     `suborder_output_request`s pointing at the completed children
     (typically a consolidation order, targeting `spawn_target`).
   - `reallocate_remainder` — re-split the shortfall into a new sub-order
     that inherits the gapped child's `order_target` unchanged; which
     system/route executes it is a fresh runtime allocation decision, not
     declared anywhere in this repo.
5. **A rule fires at most once per parent** - normative in
   `completion-rule.schema.json`. Record each `(parent_id, rule_id)` that
   has fired and never re-evaluate it (`WMS-POC`'s `_fired_rules`).
6. `spawn_order` with `supersedes_parent: true` also moves the parent to
   the reserved terminal status `superseded`: the parent is replaced, not
   fulfilled.

**Shortage.** When a line cannot be covered because no stock is available
anywhere (after any `reallocate_remainder`), apply the order type's
`strategies/shortage_policy.yaml`: `backorder`, `ship_partial`, `hold` or
`cancel_line`. An order may override the default in its header
(`shortage_policy`), but only with a value from `allowed_overrides` -
reject the order otherwise. `allow_substitution: true` lets you first
fill the shortage with the item's `lifecycle.substitute_item_id`.

**Known incompleteness to design around:**

- The quantity partition across sub-orders is runtime input; nothing
  declarative produces those numbers (by design).
- A top-level order with neither an `update_parent_status` rule nor a
  superseding `spawn_order` never advances past its initial status.
  Decide per order type whether that is acceptable.

## 6. Allocation-as-Code: executing the search and putaway

**Precedence.** Every rule kind with an `applies_to` scope uses the same
precedence (`schemas/applies-to.schema.json`, `tools/precedence.py`):
`item_id` > `owner` + `category` > `owner` > `category` > the default
rule without `applies_to`. Two rules with the same scope are rejected by
validation, so there is always exactly one winner.

**Search** (`search-rule.schema.json`): ordered `steps[]`, each
`{zone: {type, id}, selection_strategy, constraints}`. Given a
`material_request`, resolve the applicable rule, then execute the steps
in order against your **own live inventory ledger** until enough
quantity is found. Within a step, filter candidates by `constraints`
(`exclude_quality_hold`, `min_remaining_shelf_life_days`), then order
them by `selection_strategy` (`FIFO`, `FEFO`, `LIFO`,
`NEAREST_TO_TARGET`, `LOWEST_QUANTITY_FIRST`).

**Putaway** (`putaway-rule.schema.json`): the inbound counterpart. Ordered
steps, each a zone plus a `placement_strategy` (`NEXT_EMPTY`,
`ADD_TO_EXISTING`, `NEAREST_TO_SOURCE`, `NEAREST_TO_OUTFEED`,
`SPREAD_ACROSS_AISLES`, `LOWEST_LEVEL_FIRST`, `DELEGATE_TO_CONTROLLER`,
`FIXED_BIN_FIRST`) and step constraints (`load_unit_types`,
`allow_mixed_items`/`_lots`/`_owners`, `max_fill_percent`). Also honour:

- `structure/owner_zones.yaml` — zones reserved for listed owners;
- `strategies/fixed_bin_assignments.yaml` — item → fixed place with
  `min_qty`/`max_qty`/`max_pick_qty` and a `sequence`; these item-level
  thresholds win over Topology's area-level `replenishment_strategy`;
- `strategies/area_assignments.yaml` — item-level `min_qty`/`max_qty`
  (optional `planned_qty`) for a zone **without** fixed places; also wins
  over the area-level `replenishment_strategy`.

Whether quantity found across multiple steps becomes a single pick or
several sub-orders is `OrderOrchestration-as-Code`'s `split_rule`
concern, not Allocation's. Keep that boundary in your own architecture
too — don't let the search executor make splitting decisions.

## 7. What you own outright

None of the four repos model these; your WMS is the only place they can
live:

- The inventory/reservation ledger (on-hand, allocated, in-transit).
- Live order and sub-order status, and the task queue/assignment layer
  (`ExecutionTask`/`FulfillmentResult` — dispatch to a worker, vehicle, or
  controller, and its confirmed outcome).
- Wave/batch planning (bundling multiple orders for joint execution).
- Actual quantity partitioning on split (§5).
- Actual search and putaway execution against real stock (§6).
- Summing measured weights per bay and shelf, choosing the aisle entry
  end per tour, and the current operating mode of aisles and machines
  (§3).
- Executing the shortage policy (§5).
- Workforce and yard management, if your scope includes them at all.

## 8. Cross-repo referential integrity

Every repo's own `tools/validate.py` checks references *within* that
repo only. Across repos, `Warehouse-as-Code` now checks them per site:
a **site manifest** (`sites/<customer>/<facility>.yaml`) names the
Topology and Allocation facility, the MasterData company and the order
types with the buildings each serves; `tools/check_sites.py` checks the
composition and these ids, in CI on every change and daily:

| Reference | Must resolve in | Checked by `check_sites.py` |
|---|---|---|
| Order-type targets (`target_override`, `order_target_override`, `spawn_target`, …) | Topology door/work_center/activity_area of the buildings the order type serves | yes |
| `workflow_trigger.trigger` | Topology `elements/process_types.yaml` | yes |
| Allocation `zone.id`, `storage_point` | Topology storage_type/activity_area/storage_point of the same-named building | yes |
| Allocation `item_id`, `category`, `owner` | MasterData company | yes |
| `order-position.material_request.item_id` (live orders) | MasterData items | no - runtime data; check at order intake |
| Consistency rules R1–R12 (e.g. FEFO on an item without tracked expiry) | MasterData / Topology | not yet (Warehouse-as-Code backlog C1a) |

Your import/deploy pipeline should still run the same checks against the
exact revisions it imports, and add **reachability** where §3 says it
matters: an id can exist without any `movement_rule` routing to it under
`explicit_only`.

## 9. Suggested build order

1. Topology importer (idempotent, hash-based, respects `removal_policy`) plus a reachability-aware router.
2. MasterData resolver, including lifecycle-rule application.
3. Order engine: header/position shape, status machine, split (with your own classifier), workflow_trigger, completion_rule (with `source_split_rules` scoping and a re-fire guard).
4. Allocation search executor against your real inventory ledger.
5. A cross-repo validation gate wired into your deploy, reusing the
   site manifest and `Warehouse-as-Code/tools/check_sites.py`.

This mirrors what `WMS-POC` already demonstrates end to end: steps 1–3
fully (it does not yet read `putaway_rule`), step 4 only as a toy search
that does not reserve, step 5 as existence checks. Reading `poc/engine.py` and
`poc/cli.py` alongside this guide is the fastest way to see the pattern
actually running — it's explicitly a toy, not something to deploy, but
the shape is the same shape you need.

## 10. Source of truth

Where anything here conflicts with a `schemas/*.schema.json` file in one
of the four repos, **the schema wins** — this guide is a reading of it,
not a replacement for it. Each repo's `docs/entity-glossary.md`, and its
README's "Next Steps"/"Findings" sections, are the actively maintained
ground truth and will move past what's written here over time.
