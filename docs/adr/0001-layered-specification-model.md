# ADR-0001: Layered specification model — intent, contract, extension

- **Status:** Accepted
- **Date:** 2026-07-26
- **Scope:** All four "-as-Code" sibling repos
- **Supersedes:** nothing

## Context

The four sibling repos set out to be a *formal* specification of warehouse
structure and configuration that still leaves room for functionality
nobody has thought of yet. Reviewing them against that goal shows both
halves are currently under strain — but not because there is too much
formality. The formality sits in the wrong layer.

**Where the specification is over-specified**, at direct cost to human
legibility:

- `schemas/storage-type.schema.json` is **424 lines for a single entity
  type**, carrying more than ten conditional invariants (`if`/`then`).
- Physical geometry is stated per building in millimetres, together with
  fit checks including 90-degree horizontal rotation and volume
  normalisation to kg/m/m³/m/s. This is CAD-grade data expressed as
  configuration.
- Authors have to state *how* rather than *what*: `coordinate_pattern`,
  `positions_per_bay`, `selector: {aisles: {from, to}}` — instead of
  "12 aisles of euro-pallet rack, fast movers up front".

**Where it is under-specified**, at direct cost to formality:

- `split_rule.condition` (`OrderOrchestration-as-Code`) references a
  *reason id*, not an evaluable predicate. Nothing declares when a rule
  applies to a given order — `WMS-POC` had to be handed the rule list
  from outside to run the config at all.
- Five classes of cross-repo reference exist (`target.id`, `item_id`,
  `zone.id`, `load_unit_type`, `applies_to.category`) and **none** are
  checked by any repo's `tools/validate.py`.
- `api_version` exists **only in `Topology-as-Code`**. Three of four repos
  carry no version marker at all, so there is no defined way to evolve
  them without breaking existing data.

**The decisive piece of evidence** is in
`Topology-as-Code/elements/rack_templates.yaml`, which records that a
`rack_templates` catalog once existed and was deleted because *"no schema
field anywhere ever let a storage_type reference a rack template id"*. The
human-facing abstraction layer existed and was removed as dead code — its
deadness was the symptom, not the cause. In the same file,
`lane_templates` and `workstation_templates` work exactly as intended,
because something does reference them. The pattern is proven in-house and
was simply never wired up for the one domain where it would have paid most.

**On extensibility**, both patterns are already present side by side:
catalog-plus-string-id (`process_types`, `split_reasons`,
`selection_strategies`) extends without a schema change; closed `enum`
(41 occurrences across 21 schema files) does not. The wall is already
being hit — `customers/example_customer`'s AutoStore grid is declared
`automation_level: "conveyor_automated"` although no conveyor is
involved, because the enum is named after a technology rather than a
property. The designated escape hatch is closed too:
`extension.schema.json` accepts an open `payload`, but its `entity_type`
is itself a fixed 17-value enum, and the sidecar mechanism exists in only
one of the four repos.

## Decision

Adopt an explicit **three-layer model** across all four repos. Formality
and openness are not traded off against each other at a single altitude;
they are separated by layer.

### L1 — Intent (human-authored)

Archetype- and template-based. States *what* is wanted, with dimensions
and derived detail inherited from a referenced template rather than
restated per building. This is the layer humans write, read and review.
Deliberately small and approximate; it is not required to be sufficient
for machine execution on its own.

### L2 — Compiled contract (machine-facing)

What `tools/compile.py` already emits and
`compiled-topology-artifact.schema.json` already validates: closed,
exhaustive, deterministic, content-hashed, never hand-edited. **This
layer is explicitly not being changed by this ADR** — hash-based
idempotency, generic `plan.py` diffing and `removal_policy` instead of
deletion are working as designed and are the strongest part of the
current system.

### L3 — Vendor extension

Namespaced sidecars carrying data the core schemas deliberately do not
model, preserved losslessly by generic tooling.

Consequently:

1. **Restore the template reference for storage types.** Re-introduce the
   `rack_templates` catalog and add the `storage_type.template` field that
   was missing when it was deleted. Template supplies defaults;
   `default_attributes` and `exceptions` override them.
2. **Introduce `api_version` in all four repos.** This is the
   precondition for every later change: without it there is no way to
   introduce unexpected functionality without breaking existing data.
3. **Convert open-domain enums to catalogs**, specifically
   `automation_level` and `split_by`. Structural enums stay closed —
   `access_model`, `movement_policy`, `quantifier` and the completion
   `action.type` are grammar, not vocabulary, and the distinction is
   correct as it stands.
4. **Give `split_rule.condition` real semantics.** This is the one place
   where *more* formality is called for rather than less.

Generalising the L3 sidecar mechanism to the other three repos, and
opening its `entity_type` from a fixed enum to a string validated against
the artifact's actual entity types, follows from the same decision but is
not scheduled here.

## Consequences

**Positive**

- The layer humans work in shrinks substantially; describing a storage
  area becomes roughly ten lines instead of fifty, without any loss of
  precision downstream, because the precision moves into the template and
  the compiled artifact.
- New functionality arrives by adding a catalog entry rather than by
  changing a schema, for every domain that is genuinely open-ended.
- Versioned schemas give unexpected requirements a migration path instead
  of a breaking change.
- L2 remains a strict, closed, machine-checkable contract — the formality
  goal is met where it actually matters, at the WMS boundary.

**Negative / accepted costs**

- Three layers is more moving parts than two, and template inheritance
  adds an indirection when debugging a compiled result. Mitigated by the
  compiled artifact remaining fully explicit — the resolved values are
  always inspectable there.
- Converting an enum to a catalog moves a class of error from schema
  validation to `tools/validate.py`. Accepted: the same trade already
  applies to every existing `elements/` catalog.
- Existing customer data has to keep working unchanged. All new fields
  are therefore optional and additive; nothing in this ADR requires a
  migration of `customers/` data.

## Alternatives considered

- **Relax the existing schemas** (open `additionalProperties`, drop the
  geometric invariants). Rejected: this would give up the strictness at
  the WMS boundary, which is the part currently working well, and would
  not make the authoring surface any smaller.
- **Leave it as is and document it better.** Rejected: the guides added
  in `docs/` help a reader understand the model but do not reduce what an
  author has to write; the legibility problem is structural, not
  editorial.
- **One ADR per measure.** Rejected for now: the four measures follow
  from a single architectural insight and are easier to judge together.
  Separate ADRs remain appropriate for later, independent decisions.
