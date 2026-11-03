# Crosswalk to ISA-95 and SAP EWM

Status: **draft for discussion**. Shows how the terms of the as-code repo
family relate to ISA-95 (IEC 62264) and SAP EWM, so integrators who know
one of these can find their way. The crosswalk maps terms; it does not
replace any schema, and no repo adopts ISA-95 or EWM names as identifiers.

It lives here rather than in one repo's glossary for the same reason the
Domain Map and the ADRs do: it spans all repos. The repo glossaries stay
the canonical definition of each term.

## Reliability of the columns

- **As-code term**: taken from each repo's `docs/entity-glossary.md`
  (state 2026-11-03), checked against the schemas.
- **ISA-95**: the role-based equipment hierarchy (Enterprise, Site, Area,
  Work Center, Work Unit; Storage Zone is a kind of Work Center, Storage
  Unit a kind of Work Unit) and the four operations categories of part 3
  (production, maintenance, quality, **inventory**) are publicly
  documented. The part 2 object models were not read in the standard
  itself. **Every mapping is an interpretation.** The B2MML XML schemas
  (MESA) implement the part 2/4 models and are the cheapest way to check
  object names without buying the standard.
- **SAP EWM**: from memory, **not verified**, except where a repo glossary
  itself names the EWM equivalent (marked *glossary*). Topology-as-Code's
  glossary states its terms are modeled after SAP EWM/MFS.
- Fit, rated separately per standard: **good** (same meaning),
  **partial** (overlap, different scope), **loose** (analogy only),
  **none**. **False friend** = same or similar name, different meaning.

## 1. Structure (Topology-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| `company` | Tenant / organization | Enterprise | good | Client; owner of the warehouse | partial | |
| `facility` | Physical site | Site | good | Warehouse number | partial | EWM's top organizational unit; usually one site |
| `warehouse` (building) | One building / hall | Area | partial | – (warehouse number or a group of storage types) | loose | ISA-95 Area is freely defined; a building is one possible choice. EWM has no building level |
| `storage_type` | Kind of storage area with technology and policy | Storage Zone | partial | Storage type | good | ISA-95 describes a zone as a place for material, not its technology |
| `section` | Subdivision of a storage type | Storage Zone (nested) | loose | Storage section | good | |
| `storage_point` | Bookable place | Storage Unit | partial | Storage bin | good | An ISA-95 Storage Unit can be a place or a piece of equipment |
| `activity_area` | Functional grouping across the physical hierarchy | – | none | Activity area | good | Orthogonal to the hierarchy in both models |
| `work_center` | Operator / workstation side of a place | Work Unit (Work Cell) | loose | Work center | good | **False friend in ISA-95:** there, Work Center is the *level* that contains Storage Zones and Process Cells, not a single station |
| `door` | Goods receipt / dispatch point | Storage Zone (type) | loose | Warehouse door | good | |
| `staging_area` | Buffer before dispatch / after receipt | Storage Zone (type) | loose | Staging area (group / bay) | good | |

## 2. Control and equipment (Topology-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| `controller_definition` | Installation / control system with channels | Level 2 control system | loose | MFS PLC with communication channel | good | ISA-95 levels place it below the WMS |
| `reporting_point` | Communication point toward a controller; also a storage_point | – | none | MFS communication point | good | "Reporting point" is close to the German *Meldepunkt* |
| `equipment` | Executing element (shuttle, forklift, AGV, robot) | Equipment / Work Unit; Physical Asset for the hardware | partial | Resource (*glossary*, for `wms_controlled`) | partial | Glossary distinguishes `wms_controlled` and `controller_autonomous` |
| `equipment_type` | Class with capabilities | Equipment Class | partial | Resource type (*glossary*) | good | |
| `lane` / `conveyor_segment` | Physical connection ("can") | – | none | MFS conveyor segment | good | Not part of the ISA-95 equipment model in this form |

## 3. Rules and catalogs (Topology-as-Code, MasterData-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| `movement_rule` | Which movements are allowed ("may") | Inventory operations: process segment | loose | Layout-oriented storage control | partial | The allowed paths via intermediate places are layout-oriented; process-oriented storage control is closer to OrderOrchestration's workflow steps |
| `movement_policy` | Default allow / explicit only | – | none | – | none | Specific to this model |
| `replenishment_strategy` | Replenishment rule | Inventory operations scheduling | loose | Replenishment control | good | |
| `process_type` | Movement-triggering process | Inventory operations: process segment / work master | partial | Warehouse process type | good | |
| `load_unit_type` (MasterData) | Carrier (pallet, bin, carton) | Physical Asset Class or Material Class | loose | Packaging material / HU type | partial | Owned by MasterData-as-Code; Topology keeps a pinned copy |
| `storage_condition` (MasterData) | Ambient / chilled / frozen | Property of material or storage zone | loose | Storage condition | good | |
| `blocking_reason` | Why a place is blocked | – | none | Blocking reason (*glossary*) | good | |
| `hazmat_class` | Compliance classification | Material Class property | loose | Hazardous substance data | partial | |

## 4. Master data (MasterData-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| `category` | Group of items with inherited defaults | Material Class | partial | Product group | partial | |
| `item` | Article with physical attributes | Material Definition | good | Product | good | Definition, not instance - matches both |
| `packaging` | Packaging / UOM hierarchy | Material Definition properties | loose | Packaging specification; alternative UOMs | partial | |
| `tracking` | Lot / expiry / serial tracking | Material Lot / Sublot (the instances) | partial | Batch management, shelf-life data | partial | The repo defines *whether* an item is tracked; lots themselves are runtime |
| `owner` | Stock owner in a multi-client warehouse | – | none | Owner; party entitled to dispose | good | |

## 5. Orders (OrderOrchestration-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| `order` (header) | Order or sub-order with lineage (`parent_order_id`) and status | Operations Request (inventory) | loose | Warehouse request (e.g. outbound delivery order) | partial | |
| `position` | One request: exactly one of `load_unit_request`, `material_request`, `suborder_output_request`; lineage via `source_line_id` | Segment Requirement / Material Requirement | loose | Warehouse request item | partial | **Not composite:** a split creates sub-*orders*, not sub-positions |
| `target` / `order_target` | Next reachable hop vs. final business destination | – | none | – | none | No direct equivalent in either |
| `split_rule`, `split_dimension` | How an order is split, and by which dimension | – | none | Warehouse order creation rules; delivery split | loose | |
| `workflow_trigger` | Which process a split piece hands off to | Work Master selection | loose | Warehouse process type determination | partial | |
| `completion_rule` | What happens when children reach a status | – | none | Status management / PPF actions | loose | |
| `shortage_policy` | Short-pick / substitution behaviour | – | none | – (configured per process) | loose | |
| Warehouse task (runtime) | Atomic physical movement | Job Order / Job Response (inventory operations, part 4) | partial | Warehouse task | good | Runtime, not modeled in any repo |
| Stock / lot (runtime) | Current inventory | Material Lot / Sublot | good | Quant; HU stock | good | Deliberately not modeled in any repo |

## 6. Allocation (Allocation-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| `search_rule` | Stock search sequence and selection | – | none | Stock removal strategy + storage type search sequence | good | |
| `selection_strategy` | FIFO / FEFO / LIFO, ... | – | none | Stock removal rule | good | |
| `putaway_rule` | Where arriving stock goes, step by step | – | none | Putaway strategy + storage type search sequence (putaway) | good | |
| `placement_strategy` | How a place is chosen inside a zone (`NEXT_EMPTY`, `ADD_TO_EXISTING`, `FIXED_BIN_FIRST`, ...) | – | none | Putaway rules (empty bin, addition to existing stock, fixed bin) | good | |
| `fixed_bin_assignment` | Item fixed to a place with min / max | – | none | Fixed bin assignment | good | |
| `owner_zones` | Zones reserved for a stock owner | – | none | – (bin / storage type restrictions per owner) | loose | |

## 7. Composition (Warehouse-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | Note |
|---|---|---|---|---|---|---|
| Site manifest (`sites/`) | Which repos' configuration belongs to one facility | Site (as a scope) | loose | Warehouse number customizing as a whole | loose | No equivalent in either - both are single systems, the repo family is several |

## What could be adopted

1. **Vocabulary only.** Repo glossaries can link here; no glossary or schema
   changes its own names. Low effort, helps integrators.
2. **Class / definition / instance as an explicit principle.** ISA-95
   separates classes, definitions and instances (Material Class →
   Material Definition → Material Lot). The repos already have the same
   three layers: catalogs in `elements/` (≈ class), the configuration in
   `customers/` (≈ definition - it is still desired state, not an
   instance), and runtime state (≈ instance), which no repo models by
   design. Naming the mapping gives a standards-based reason for the
   existing "structure vs. runtime" principle.
3. **Role vs. physical asset.** ISA-95 separates what a unit does
   (equipment, role-based) from the hardware that does it (physical
   asset). The model has something similar with `work_center` and
   `reporting_point` on the same physical place. An idea to examine, not a
   decision.
4. **Export instead of adoption.** If a partner needs ISA-95-shaped data,
   generate B2MML from the compiled contract (ADR-0001's L2 layer) rather
   than from the authored YAML, and never change the schemas for it.

## What should not be adopted

- **The level pyramid and the production operations models.** They target
  manufacturing. The order model with splits, lineage and completion rules
  is finer and warehouse-specific; ISA-95's inventory operations cover
  the activity, not this decision logic.
- **ISA-95 names as identifiers.** "Storage Unit" vs. `storage_point` and
  especially Work Center vs. `work_center` are not clean matches. Keep
  own names, map only.
- **B2MML as internal format.** It is an XML exchange format, not a good
  way to maintain configuration.
- **ISA-95 as the only reference.** For warehouse logistics, SAP EWM terms
  are usually the more familiar ones - the EWM column above has far more
  good fits. Other relevant standards: VDA 5050 with the VDMA Layout
  Interchange Format (mobile robots), the VDMA 40xxx OPC UA companion
  specifications (machines and controllers), GS1 (GTIN for articles, SSCC
  for load units; not checked).

## Open points

- Who should accept the model: customers and integrators, other plant
  vendors, or the own company first? This decides which column matters
  most.
- The EWM column needs a check by someone with EWM knowledge before it is
  relied on.
- The ISA-95 part 2 object models were not read; check the object names
  in sections 4-5 against the B2MML schemas.

## Sources

- Symestic, ISA-95 overview: https://www.symestic.com/en-us/what-is/isa-95
- TEEPTRAK, ISA-95 equipment hierarchy and B2MML: https://teeptrak.com/en/mes-architecture-isa-95-implementation-2026/
- ServiceNow documentation on the ISA-95 equipment model (storage zone, storage unit): https://www.servicenow.com/docs/r/B3SMebN4ZjjOiPxesW27LQ/QHh3DyEYXMtXFeWi~8ojtQ
- The `docs/entity-glossary.md` of Topology-as-Code, MasterData-as-Code, OrderOrchestration-as-Code and Allocation-as-Code
