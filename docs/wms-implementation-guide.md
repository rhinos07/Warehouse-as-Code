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
- `entities` — every building-owned entity (storage types/points, sections, activity areas, work centers, doors, controllers, reporting points, equipment, telegram actions, `can_edge` connectivity, lanes/conveyor topology, movement rules, replenishment strategies), each keyed by type, each item at least `{id: ...}`.

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

What the artifact does **not** give you: current occupancy, current
equipment availability, anything live. `storage_point` is a place goods
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
default_uom}`. Use it twice: to validate `material_request.item_id` at
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

**Splitting — the one place this family deliberately leaves a gap for
you.** `split_rule.condition` (`split-rule.schema.json`) references a
*reason id* in `elements/split_reasons.yaml` — it is not an evaluable
predicate. No schema anywhere says which rule(s) apply to a *given*
order; that decision is explicitly runtime business logic, by design, not
an omission. `WMS-POC` sidesteps this by taking an explicit list of rule
ids as input to its `split()` call — a real engine needs an actual
classifier (e.g. "does this line's item live in a zone tagged
`AUTOSTORE_GRID`? → apply `SPLIT_TO_AUTOSTORE`").

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
5. **Guard against re-firing.** No schema field stops a rule from matching
   twice (e.g. a spawned consolidation order later reaching its own
   watched status). Keep a `(parent_id, rule_id)` fired-set until this is
   fixed upstream — `WMS-POC` does exactly this as a POC-level guard, not
   a schema fix.

**Known incompleteness to design around**, taken directly from the
sibling repos' own "Next Steps"/"Findings" sections — these are open
by design, not bugs you're expected to work around silently:

- No `split_rule` trigger-status concept yet. A split that can only be
  decided *after* some status (e.g. inbound putaway, only after
  `receipt_confirmed`) has no declarative way to express that gate — your
  engine has to enforce it itself for now.
- No declarative quantity-partitioning across sub-orders. Do **not** copy
  `WMS-POC`'s simplification of cloning the full parent quantity onto
  every child — a real engine must actually partition confirmed quantity
  across siblings.
- A top-level order with no matching `update_parent_status` rule simply
  never advances past its initial status. Decide deliberately, per
  order_type, whether that's acceptable or needs a default rule — it
  won't happen automatically.

## 6. Allocation-as-Code: executing the search

`search-rule.schema.json` gives you `applies_to` (item_id is more
specific than category, category more specific than the building's
default rule — the repo has **no declared tie-break** for two rules of
equal specificity, so decide and document your own precedence) and an
ordered `steps[]`, each `{zone: {type, id}, selection_strategy,
constraints}`.

Given a `material_request`, your engine:

1. Resolves the applicable `search_rule` (item → category → default).
2. Executes `steps` in order against your **own live inventory ledger**
   — nothing in this repo holds actual stock — until enough quantity is
   found.
3. Within each step: filter candidates in that `zone` by `constraints`
   (`exclude_quality_hold`, `min_remaining_shelf_life_days`), then order
   them by `selection_strategy` (`elements/selection_strategies.yaml`:
   `FIFO`, `FEFO`, `LIFO`, `NEAREST_TO_TARGET`,
   `LOWEST_QUANTITY_FIRST` — five concrete, directly implementable sort
   keys, not left open to interpretation).

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
- Actual search execution against real stock (§6).
- Workforce and yard management, if your scope includes them at all.

## 8. Cross-repo referential integrity — nobody else checks this for you

Every one of the four repos' own `tools/validate.py` checks references
*within* that repo only; each README says explicitly that cross-repo
references are unchecked. Your import/deploy pipeline is the only place
these can be caught before they become a runtime failure:

| Reference | Must resolve in | Note |
|---|---|---|
| `order-header.target.id` / `order_target.id` | `Topology-as-Code` compiled artifact (door/work_center/activity_area) | Check **reachability**, not just existence — an id can exist without any `movement_rule` ever routing to it under `explicit_only` (a real bug this family had, fixed upstream, see `Topology-as-Code`'s own "Next Steps"). |
| `order-position.material_request.item_id` | `MasterData-as-Code` compiled item index | |
| `order-position.load_unit_request.load_unit_type` | `Topology-as-Code`'s `elements/load_unit_types.yaml` | |
| `search_rule.steps[].zone.id` | `Topology-as-Code` compiled artifact (storage_type/activity_area) | |
| `search_rule.applies_to.{category,item_id}` | `MasterData-as-Code` compiled category/item ids | |

`WMS-POC/poc/topology_ref.py` and `poc/masterdata_ref.py` show a minimal,
working version of the existence checks (build an id index from the
compiled artifacts, flag anything an order references that isn't in it).
Treat that as the floor, not the ceiling — extend it to reachability
where §3 already told you it matters.

## 9. Suggested build order

1. Topology importer (idempotent, hash-based, respects `removal_policy`) plus a reachability-aware router.
2. MasterData resolver, including lifecycle-rule application.
3. Order engine: header/position shape, status machine, split (with your own classifier), workflow_trigger, completion_rule (with `source_split_rules` scoping and a re-fire guard).
4. Allocation search executor against your real inventory ledger.
5. A cross-repo validation gate wired into CI/deploy — not just local dev.

This mirrors what `WMS-POC` already demonstrates end to end: steps 1–3
fully, step 4 not attempted (it has no real search executor), step 5
partially (existence checks only). Reading `poc/engine.py` and
`poc/cli.py` alongside this guide is the fastest way to see the pattern
actually running — it's explicitly a toy, not something to deploy, but
the shape is the same shape you need.

## 10. Source of truth

Where anything here conflicts with a `schemas/*.schema.json` file in one
of the four repos, **the schema wins** — this guide is a reading of it,
not a replacement for it. Each repo's `docs/entity-glossary.md`, and its
README's "Next Steps"/"Findings" sections, are the actively maintained
ground truth and will move past what's written here over time.
