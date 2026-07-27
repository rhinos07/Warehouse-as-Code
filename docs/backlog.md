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
- **B2 — `applies_to` has no tie-break.** `item_id` beats `category` beats
  the building default, but two rules of *equal* specificity are undefined;
  `tools/validate.py` only rejects two rules both omitting `applies_to`.
  Same shape as the sibling-distinctness gap `split_rule.when` closed.
  *Owner:* `Allocation-as-Code`; confirmed at runtime as `WMS-POC` Finding #12.
- **B3 — `SEARCH_DEFAULT` cannot produce a technology split.** It searches
  only `PICK_ZONE_A` and `HBR` although the same building has
  `AUTOSTORE_A`, so a search-driven allocation always resolves to one
  technology. *Owner:* `Allocation-as-Code` example data; `WMS-POC`
  Finding #9.

## C. Structural, cross-cutting

- **C1 — Cross-repo referential integrity is enforced nowhere.** Five
  reference classes cross repo boundaries (`target.id`, `item_id`,
  `zone.id`, `load_unit_type`, `applies_to.category`/`item_id`) and no
  repo's `tools/validate.py` checks any of them. `WMS-POC` does existence
  checks as a demo, not as a gate. **The largest remaining structural
  weakness** — today this is the only thing that could let a broken
  configuration reach a WMS. Needs a design decision before work starts:
  shared tool, per-repo duplication, or CI-only.
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

- **C3 — Test coverage is uneven.** `Topology-as-Code` has 7 test files;
  the other three sibling repos have none. `Allocation-as-Code` is the
  least-covered of all: no tests, and until recently nothing had ever
  executed its model.
- **C4 — ADR-0001's L3 layer is only half built.** Extension sidecars
  exist in `Topology-as-Code` only, and their `entity_type` is itself a
  fixed 17-value enum — so even the escape hatch cannot take a new entity
  kind. Generalising the mechanism and opening that enum follows from
  ADR-0001 but was never scheduled.

## D. Open decisions

Not work yet — each needs a call before anything is built.

- **D1 — Shared-vocabulary extraction**, long deferred for `process_types`
  and `load_unit_types`. `storage_technologies` was just settled a
  different way: give it an owner rather than extract it. That precedent
  may well settle the other two without a shared repo.
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
  suppliers) — `MasterData-as-Code` or its own repo?

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
  two entries.**

## Suggested order

1. **A1, then A2** — small, they collect the payoff of work already merged,
   and A1 empirically tests A2.
2. **B1** — the last known correctness hole, and now verifiable against a
   running engine rather than on paper.
3. **B2 and B3** — small, both in `Allocation-as-Code`, both already
   confirmed at runtime.
4. **C1** — the biggest remaining structural weakness, but start with the
   design decision, not with code.
5. **D-items** as they become blocking; **C2/C3/C4 and E** as deliberate
   investments rather than reactive fixes.
