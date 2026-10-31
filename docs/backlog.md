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
| A1 | `WMS-POC` | Drop the hardcoded `ZONE_TECHNOLOGY` table in `poc/engine.py`; read the technology from the compiled artifact instead. | its Finding #8 |
| A2 | `OrderOrchestration-as-Code` | Point `split_rule.when.dimension_value` at Topology's `storage_technologies` catalog. | the vocabulary drift below |

A2 has a concrete symptom already visible: `b2c_standard` uses
`manual_warehouse` while `b2c_multi_system` uses `manual_pick` for
comparable areas — exactly what an unanchored vocabulary produces.

A1 is also the test for A2. Once the POC reads real technologies, `HBR`
resolves to `shuttle`, and `b2c_standard` has no rule claiming that value —
so running it should surface a genuine configuration gap rather than a
theoretical one.

## B. Correctness gaps

Real defects a runtime hits, not modelling preferences.

- **B1 — `completion_rule` re-fire / parent completion.** A top-level order
  with only a `spawn_order` rule never leaves `created`, and a rule can fire
  a second time once the spawned order reaches the watched status.
  `WMS-POC` works around it with a `_fired_rules` set that its own code
  labels "a POC workaround, not a fix". *Owner:*
  `OrderOrchestration-as-Code` README, top of Next Steps; `WMS-POC`
  Findings #2 and #6. **The last known correctness hole in the family.**
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
- **C1c — Topology follow-up: gross weight.** With `tare_weight` in the
  pinned carrier catalog, `Topology-as-Code`'s storage-envelope check
  could compare carrier `max_weight` + `tare_weight` against a storage
  point's `max_weight`; today it uses `max_weight` alone. Not changed yet
  because it may turn existing examples red.
- **C2 — Schema strictness is uneven.** `Topology-as-Code` closes every
  schema with `additionalProperties: false`; the others largely do not.
  Whether that is deliberate (younger repos, still moving) or drift is
  worth deciding rather than leaving implicit.

  | Repo | Closed schemas |
  |---|---|
  | `Topology-as-Code` | 22 / 22 |
  | `OrderOrchestration-as-Code` | 7 / 12 |
  | `MasterData-as-Code` | 4 / 9 |
  | `Allocation-as-Code` | 2 / 6 |

- **C3 — Test coverage is uneven.** `Topology-as-Code` has 7 test files.
  `Allocation-as-Code` and `MasterData-as-Code` now have unit tests for
  their newer rules (putaway, owners, tracking) and a CI test job, but not
  for their older checks; `OrderOrchestration-as-Code` has none.
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
  two entries.** *In progress:* `Allocation-as-Code` PR #3 adds
  `putaway_rule` as the inbound counterpart of `search_rule`.

## Suggested order

1. **A1, then A2** — small, they collect the payoff of work already merged,
   and A1 empirically tests A2.
2. **B1** — the last known correctness hole, and now verifiable against a
   running engine rather than on paper.
3. **C1** — the biggest remaining structural weakness, but start with the
   design decision, not with code.
4. **D-items** as they become blocking; **C2/C3/C4 and E** as deliberate
   investments rather than reactive fixes.
