# Open Work Across the Repo Family

A map of what is still open across the four "-as-Code" repos and `WMS-POC`,
and in what order it makes sense to do it. It lives here for the same
reason the Domain Map and the ADRs do: sequencing and dependencies between
repos belong to no single repo.

**This is not a second source of truth.** Each repo's own README "Next
Steps" and `WMS-POC`'s "Findings" stay authoritative for the detail of an
item; this page says what exists, what blocks what, and why an item
matters. Where the two disagree, the owning repo wins.

Status as of the last pass: ADR-0001's four measures are all merged, and
`storage_type.technology` has landed in `Topology-as-Code`.

## A. Unlocked by the technology anchor

`Topology-as-Code` now owns the zone → technology vocabulary
(`storage_type.technology`, derived onto `activity_area` by the compiler).
Both consumers can now stop improvising. These two are the immediate
follow-ups.

| # | Repo | Work | Closes |
|---|---|---|---|
| A1 | `WMS-POC` | ~~Drop the hardcoded `ZONE_TECHNOLOGY` table in `poc/engine.py`; read the technology from the compiled artifact instead.~~ *Done:* `ZONE_TECHNOLOGY` is gone; the POC reads the compiled technology (its Finding #8, which surfaced #9). | its Finding #8 |
| A2 | `OrderOrchestration-as-Code` | ~~Point `split_rule.when.dimension_value` at Topology's `storage_technologies` catalog.~~ *Done in the data:* every `dimension_value` (`autostore`, `shuttle`, `manual_warehouse`) is a catalog id; `manual_pick` is gone. Not enforced by a check - that is a cross-repo reference (C1). | the vocabulary drift below |

A2's former symptom (`b2c_multi_system` used `manual_pick` where
`b2c_standard` used `manual_warehouse`) is gone; both use `manual_warehouse`.

A1 is also the test for A2. Once the POC reads real technologies, `HBR`
resolves to `shuttle`, and `b2c_standard` has no rule claiming that value —
so running it should surface a genuine configuration gap rather than a
theoretical one.

## B. Correctness gaps

Real defects a runtime hits, not modelling preferences.

- **B1 — `completion_rule` re-fire / parent completion.** *Closed in
  `OrderOrchestration-as-Code`:* `action.supersedes_parent` moves the parent
  to a reserved terminal `superseded` status, and
  `completion-rule.schema.json` states normatively that a rule fires at
  most once per parent. `WMS-POC` implements both (its `_fired_rules` set
  is now the normative guard, no longer a workaround). Confirmed on
  2026-10-31 by running `python -m poc.cli` against current `main` of all
  four repos: `b2c_standard-001` ends `superseded`, the consolidation
  order is spawned once.
- **B2 — `applies_to` has no tie-break.** *Closed in `Allocation-as-Code`
  (stock-owner PR):* precedence is now item_id > owner + category > owner >
  category > default; since an item has exactly one id, owner and
  category, identical scopes are the only possible tie, and
  `tools/validate.py` rejects them. `tools/precedence.py` is the reference
  selection. `WMS-POC` Finding #12 should be re-checked against it.
- **B3 — `SEARCH_DEFAULT` cannot produce a technology split.** *Closed in
  `Allocation-as-Code` #2:* `SEARCH_DEFAULT` now searches `PICK_ZONE_A`,
  then `AUTOSTORE_A`, then `HBR`, so a search-driven allocation can
  resolve to the `autostore` technology. `WMS-POC` Finding #9.

## C. Structural, cross-cutting

- **C1 — Cross-repo referential integrity is enforced nowhere.** Six
  reference classes cross repo boundaries (`target.id`, `item_id`,
  `zone.id`, `load_unit_type`, `applies_to.category`/`item_id`, and since
  the stock-owner work `applies_to.owner` → `MasterData-as-Code`
  `company.yaml` owners) and no
  repo's `tools/validate.py` checks any of them - except `load_unit_type`
  data, which `Topology-as-Code` now checks through pinned copies (C1b).
  `WMS-POC` does existence
  checks as a demo, not as a gate. **The largest remaining structural
  weakness** — today this is the only thing that could let a broken
  configuration reach a WMS. Needs a design decision before work starts:
  shared tool, per-repo duplication, or CI-only.
- **C1 — first step done:** site manifests (`sites/`) bind the repos per
  facility, checked by `tools/check_sites.py` in CI. Next: resolve ids
  across repos through the manifest (order-type targets against the
  listed buildings, item ids, zone ids), then R1–R12. Known finding: the
  example OrderOrchestration order types use targets from Topology's
  `autostore_customer` (`EXIT`, `PUTAWAY_ZONE_GRID`) and items unknown to
  MasterData, so they will fail once targets are checked. Also: the
  facility id differs between Topology (`PA11`) and Allocation
  (`facility_pa11`); the manifest maps by path, so it does not matter
  yet, but the ids should be aligned.
- **C1a — Cross-repo consistency rules waiting on C1.** Beyond plain id
  existence, the putaway and tracking work adds rules that compare
  *values* across repos. Each is defined, none is implemented, and all
  wait for the same C1 design decision (where cross-repo checks run, and
  against which version of each repo).

  | # | Rule | Repos | Severity | Origin |
  |---|---|---|---|---|
  | R1 | A `search_rule` with `FEFO` or `min_remaining_shelf_life_days` scopes an item whose `tracking.expiry.tracked` is false. | Allocation ↔ MasterData | error | MasterData-as-Code PR #3 |
  | R2 | A `search_rule`'s `min_remaining_shelf_life_days` is above the item's `tracking.expiry.min_remaining_at_receipt_days`: stock can be received that this rule can never ship. | Allocation ↔ MasterData | warning | MasterData-as-Code PR #3 |
  | R3 | A `putaway_rule` step sets `allow_mixed_lots` for an item with `tracking.lot: none` (has no effect). | Allocation ↔ MasterData | warning | MasterData-as-Code PR #3 |
  | R4 | A `putaway_rule` step's `load_unit_types` contains an id that is not a Topology `load_unit_type`, or not in the zone's `allowed_load_unit_types`. | Allocation ↔ Topology | error | Allocation-as-Code PR #3 |
  | R5 | A `putaway_rule` step sets `allow_mixed_items: true` on a zone whose `homogeneity_required` is true. | Allocation ↔ Topology | error | Allocation-as-Code PR #3 |
  | R6 | A `putaway_rule` scoped by `item_id` places into a zone of `owner_zones` that is not reserved for the item's owner. | Allocation ↔ MasterData | error | stock-owner PRs |
  | R7 | `applies_to.owner` is set although the company declares no owners, or names an owner that the company does not declare. | Allocation ↔ MasterData | error | stock-owner PRs |
  | R8 | A `fixed_bin_assignment.storage_point` is not a compiled Topology `storage_point`, or its storage type does not allow the load unit the item is stored in. | Allocation ↔ Topology | error | fixed-bin PR |
  | R9 | A `fixed_bin_assignment` names an item or `uom` that MasterData does not define. | Allocation ↔ MasterData | error | fixed-bin PR |
  | R10 | A fixed place lies in an `owner_zones` zone not reserved for the item's owner. | Allocation ↔ MasterData ↔ Topology | error | fixed-bin PR |
  | R11 | A `putaway_rule` places an item into a zone whose `storage_condition` differs from the item's `storage_condition` (MasterData). | Allocation ↔ MasterData ↔ Topology | error | catalog-pinning PRs |
  | R12 | An order_type sets `shortage_policy.allow_substitution: true`, but none of the items it can order has `lifecycle.substitute_item_id` - or a substitute id does not exist (MasterData). | OrderOrchestration ↔ MasterData | warning | shortage-policy PR |

  R1–R3 and R6 resolve item properties (tracking, owner) through `MasterData-as-Code`'s
  `tools/tracking.py` (category inheritance), so a cross-repo check must
  use the compiled MasterData artifact, not the raw `items.yaml`.

- **C1b — First cross-repo mechanism in use: pinned catalog copies (way
  A).** `Topology-as-Code` copies `load_unit_types.yaml` and
  `storage_conditions.yaml` byte-identically from `MasterData-as-Code`;
  `elements/catalog_sources.yaml` pins the source commit and hash,
  `tools/sync_catalogs.py` checks and re-pins, and a CI job compares the
  copies with the source at the pinned commit. A change in the source
  repo never turns the consumer red; taking it over is a deliberate
  re-pin. Candidate pattern for the rest of C1 where the consumer needs
  the *data*, not only the ids.
- **C1c — Topology follow-up: gross weight.** *Closed, not pursued:*
  adding `tare_weight` to the static storage-envelope check would only
  improve a design-time plausibility check. At runtime the weight of a
  load unit is measured by a scale; a calculated weight is too risky to
  rely on. Topology's bay and shelf load limits (`load_limits`) follow the
  same rule: Topology states the limits, the runtime compares the measured
  weight.
- **C2 — Schema strictness is uneven.** `Topology-as-Code` closes almost
  every schema with `additionalProperties: false`; the others close about
  half. Whether that is deliberate (younger repos, still moving) or drift is
  worth deciding rather than leaving implicit. Counted on 2026-10-31 as
  schemas with a top-level `additionalProperties: false`:

  | Repo | Closed schemas | Open |
  |---|---|---|
  | `Topology-as-Code` | 23 / 25 | `quantity` (definitions only, no top-level object), `uom-type` (pinned copy, must accept every source field) - both by design |
  | `OrderOrchestration-as-Code` | 7 / 13 | `channel`, `company`, `order-header` (open on purpose, `fields.yaml` extends it), `order-type`, `split-dimension`, `split-reason` |
  | `MasterData-as-Code` | 7 / 12 | `category`, `company`, `hazmat-class`, `packaging-material`, `uom-type` |
  | `Allocation-as-Code` | 6 / 11 | `allocation`, `company`, `facility`, `placement-strategy`, `selection-strategy` |

- **C3 — Test coverage is uneven.** Counted on 2026-10-31:

  | Repo | Test files | CI test job |
  |---|---|---|
  | `Topology-as-Code` | 11 | yes |
  | `MasterData-as-Code` | 4 | yes |
  | `Allocation-as-Code` | 3 | yes |
  | `OrderOrchestration-as-Code` | 0 | no |

  `Allocation-as-Code` and `MasterData-as-Code` test their newer rules
  (putaway, owners, fixed bins, tracking, barcodes, load units) but not
  their older checks. `OrderOrchestration-as-Code` has no unit tests at
  all, and its CI does not run `tools/validate_examples.py`, so the
  shortage-policy check on example orders runs only locally.
- **C4 — ADR-0001's L3 layer is only half built.** Extension sidecars
  exist in `Topology-as-Code` only, and their `entity_type` is itself a
  fixed 17-value enum — so even the escape hatch cannot take a new entity
  kind. Generalising the mechanism and opening that enum follows from
  ADR-0001 but was never scheduled.

## D. Open decisions

Not work yet — each needs a call before anything is built.

- **D1 — Shared-vocabulary extraction**, long deferred for `process_types`
  and `load_unit_types`. `storage_technologies` was settled by giving it
  an owner rather than extracting it. *Decided for `load_unit_types`:*
  owned by `MasterData-as-Code` (with `tare_weight`), together with the
  new `storage_conditions` catalog; `Topology-as-Code` keeps pinned
  copies (see C1, way A). `process_types` stays owned by
  `Topology-as-Code`.
- **D1a — UOM vocabulary drift.** *Closed:* `Topology-as-Code` now keeps
  a pinned copy of `MasterData-as-Code`'s `uom_types.yaml` (C1b) and
  checks `replenishment_strategy.unit_conversion` against it;
  `REPL_PICKFACE_A` converts to `each` instead of `piece`.
- **D2 — `Allocation-as-Code`'s `zone.type` excludes `work_center`**,
  although Topology's `work_center` can carry `storage_point_ref: true`
  (bookable WIP) and Orchestration's `target.type` already includes it. So
  a search cannot currently consider a packing station. Deliberate or
  oversight?
- **D3 — `channel.schema.json` is titled "Sales Channel"** but the inbound
  channel is not one. Its README already suggests renaming once a second
  non-sales case appears.
- **D4 — Does `search_rule` need an `order_type`/`channel` scope**, in
  addition to item/category?
- **D5 — Where does trading-partner master data live** (customers,
  suppliers) — `MasterData-as-Code` or its own repo? *Partly decided:*
  stock owners live in `MasterData-as-Code` as `company.yaml` `owners`,
  each item belongs to exactly one owner. Suppliers and customers remain
  open.
- **D6 — Operating mode per direction** (inbound and outbound / inbound
  only / outbound only). *Deferred.* The mode is a runtime state per
  aisle or machine: an aisle served by a machine (e.g. a stacker crane)
  must be switchable during operation, so it is not a fixed topology
  value. `Topology-as-Code` will later only state which modes an aisle
  or machine allows (e.g. `allowed_operating_modes` on `route_aisle` or
  `equipment`); the current mode is set at runtime.
- **D7 — Inventory procedure.** *Deferred.* Close to topology but not
  topology itself: the procedure depends on the storage type (a channel
  is in practice only countable at zero crossing), yet it is process
  configuration, not structure. Approval of count differences is a
  process (`OrderOrchestration-as-Code`). Legal basis in Germany: HGB
  § 240 (duty to take inventory) and § 241 (simplifications: sample,
  permanent, advanced or postponed key-date inventory); the exact time
  limits of § 241 have not been checked here.

  Inventory types to cover:

  | Type | Trigger | Typical use |
  |---|---|---|
  | Key-date (`key_date`) | Fixed date, whole area | Manual storage, block storage |
  | Permanent / cycle (`cycle`) | Interval; every point at least once per period | Rack storage, high-bay rack |
  | Zero crossing (`zero_crossing`) | A point or channel becomes empty | Channel storage, automated storage |
  | Putaway count (`putaway_count`) | First putaway onto an empty point | AS/RS, shuttle |
  | Statistical sample (`sample`) | Statistical selection | Large warehouses; needs auditor approval - leave out at first |
  | Controller count (`delegate_to_controller`) | The controller counts itself (camera, weighing) | AutoStore, AS/RS - analogous to the `DELEGATE_TO_CONTROLLER` placement strategy |

  Proposal (draft, not decided): a `strategies/inventory.yaml` next to
  `replenishment.yaml`, referencing the existing `activity_area`s with
  `activity: physical_inventory`:

  ```yaml
  inventory_procedures:
    - id: INV_HBR
      activity_area: INV_AREA_HBR
      procedures:
        - type: zero_crossing
        - type: cycle
          interval: { value: 12, unit: "month" }   # every point at least once
      count:
        blind: true                  # counter does not see the book quantity
        recount_tolerance_percent: 2 # deviation above this triggers a recount
  ```

  Open questions:
  1. Owner repo: `Topology-as-Code` (strategies/), `Allocation-as-Code`,
     or a repo of its own?
  2. Which procedures are needed first; is `sample` needed now?
  3. Do count rules (blind count, recount tolerance) belong here, or
     only procedure and area?
  4. Is `delegate_to_controller` a procedure of its own?
- **D8 — ABC (velocity) classification.** *Deferred, proposal only.*
  Today Topology `section.criteria.access_frequency` (e.g. `SEC_FAST`) is
  a free attribute nothing reads, and no item carries a class. Proposal:

  | What | Where | Why |
  |---|---|---|
  | ABC class per item | `Allocation-as-Code`, per building (e.g. `strategies/item_classes.yaml`), written by a script | The class is per warehouse, not global: the same item can be A in one hall and C in another, so not in MasterData's item master |
  | Class catalog (A/B/C, maybe X/Y/Z) | `Allocation-as-Code` `elements/` | Fixed vocabulary |
  | Rules by class | `applies_to: { abc_class: "A" }` on `putaway_rule` / `search_rule`, ranked between owner and category | e.g. put A items into the fast area first |
  | Storage area by class | Topology `section.abc_classes: ["A"]` instead of free `access_frequency` | The area states which classes it is meant for |

  Open: ABC only, or XYZ (demand variability) too? Is the class per
  warehouse or per client/item in KCC? Precedence position? Related:
  `area_assignments` (Allocation) and D7 (cycle counting often uses the
  ABC class for the count interval).
- **D9 — Bills of material / kits.** *Deferred until a kitting or VAS
  case exists.* Reference: myWMS `LOSBom` (parent item, child item,
  quantity, `pickable`). Not modeled anywhere. If needed it belongs in
  `MasterData-as-Code`: a kit item lists its components with quantity
  and uom, and states whether the kit is picked as a whole (pre-built
  and stocked) or assembled from its components at a work center.
  Open: pre-built vs. built-to-order (or both); does the kit carry its
  own stock, barcodes and tracking, or only its components; does
  OrderOrchestration explode a kit line into component lines, and if so
  as a split rule or a new position kind?

## E. Unmodeled domains

From the Domain Map, plus one gap the Map does not currently name.

- **E1 — Inventory / stock state** (on-hand, reservations). `WMS-POC`
  Finding #11 makes the reservation half concrete: its search reads the
  ledger without decrementing it, so two orders would both "find" the same
  stock.
- **E2 — Wave / batch planning.** Untouched.
- **E3 — Putaway destination determination.** No repo models it:
  `Allocation-as-Code` covers stock *search* (where existing stock is), not
  where arriving stock should go. `WMS-POC` Finding #10 — its inbound split
  is the one decision it still hardcodes. Note the Domain Map excludes
  *slotting optimization* as analytics, which is a different thing: a
  putaway destination has to be decided on every inbound. **Worth adding to
  the Domain Map as its own row rather than leaving it in the gap between
  two entries.** *Closed as configuration:* `Allocation-as-Code` models
  it with `putaway_rule` (#3, the inbound counterpart of `search_rule`,
  with a placement-strategy catalog), owner zones (#4) and fixed-bin
  assignments (#5); the Domain Map has its own row now. Still open on the
  runtime side: `WMS-POC` Finding #10 - the POC does not read
  `putaway_rule` yet and keeps its hardcoded inbound split.

## Suggested order

A1, A2, B1, B2, B3 and C1c are done or closed (2026-10-31). No known correctness hole
remains open.

1. **C1** — the biggest remaining structural weakness: decide where the
   cross-repo rules R1–R12 run, then build. Start with the design
   decision, not with code.
2. **D-items** as they become blocking; **C2/C3/C4 and E** as deliberate
   investments rather than reactive fixes.
