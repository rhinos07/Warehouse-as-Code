# Crosswalk to ISA-95, SAP EWM and AutomationML

Status: **draft for discussion**. Shows how the terms of the as-code repo
family relate to ISA-95 (IEC 62264), SAP EWM and AutomationML (IEC 62714),
so integrators who know one of these can find their way. The crosswalk
maps terms; it does not replace any schema, and no repo adopts ISA-95, EWM
or AutomationML names as identifiers.

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
- **AutomationML**: role classes from the base, DMI (discrete
  manufacturing) and extended role class libraries, as listed in IEC
  62714-2 previews and the OPC UA mapping OPC 30040; CAEX concepts
  (InstanceHierarchy, SystemUnitClass, RoleClass, InterfaceClass,
  InternalLink, mirror objects) from IEC 62714-1 / IEC 62424. Read via
  search results, **not in the standards or on automationml.org** (not
  reachable at the time). The application recommendation "Modelling of
  Material Handling in AutomationML", which covers material handling
  systems and transport units, was **not read**; it may refine the
  mappings for doors, carriers and load units. AutomationML exchanges
  plant engineering data, so the rules, master data strategies, orders
  and allocation have no counterpart in it by design.
- Fit, rated separately per standard: **good** (same meaning),
  **partial** (overlap, different scope), **loose** (analogy only),
  **none**. **False friend** = same or similar name, different meaning.

## 1. Structure (Topology-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| `company` | Tenant / organization | Enterprise | good | Client; owner of the warehouse | partial | Role Enterprise (extended library, after IEC 62264-1) | good | |
| `facility` | Physical site | Site | good | Warehouse number | partial | Role Site (extended library) | good | EWM's top organizational unit; usually one site |
| `warehouse` (building) | One building / hall | Area | partial | – (warehouse number or a group of storage types) | loose | Role Area - "production buildings and their subdivisions (structure/hall)" | good | ISA-95 Area is freely defined; a building is one possible choice. EWM has no building level |
| `storage_type` | Kind of storage area with technology and policy | Storage Zone | partial | Storage type | good | Role Storage (DMI library); technology and policy as attributes or a SystemUnitClass | partial | ISA-95 describes a zone as a place for material, not its technology |
| `section` | Subdivision of a storage type | Storage Zone (nested) | loose | Storage section | good | Role Group (base library) | loose | |
| `storage_point` | Bookable place | Storage Unit | partial | Storage bin | good | Role StorageUnit (extended library, after IEC 62264) | partial | An ISA-95 Storage Unit can be a place or a piece of equipment |
| `activity_area` | Functional grouping across the physical hierarchy | – | none | Activity area | good | Group with mirror objects (one element in several hierarchies) | partial | Orthogonal to the hierarchy in both models |
| `work_center` | Operator / workstation side of a place | Work Unit (Work Cell) | loose | Work center | good | Role WorkCenter (extended library) | false friend | **False friend in ISA-95:** there, Work Center is the *level* that contains Storage Zones and Process Cells, not a single station |
| `door` | Goods receipt / dispatch point | Storage Zone (type) | loose | Warehouse door | good | – (DMI role Gate exists; meaning not verified) | none | |
| `staging_area` | Buffer before dispatch / after receipt | Storage Zone (type) | loose | Staging area (group / bay) | good | Role Storage (DMI library) | loose | |

## 2. Control and equipment (Topology-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| `controller_definition` | Installation / control system with channels | Level 2 control system | loose | MFS PLC with communication channel | good | InternalElement with communication interfaces; its logic as PLCopen XML | loose | ISA-95 levels place it below the WMS |
| `reporting_point` | Communication point toward a controller; also a storage_point | – | none | MFS communication point | good | Port (base role) with an interface on the conveyor element | partial | "Reporting point" is close to the German *Meldepunkt* |
| `equipment` | Executing element (shuttle, forklift, AGV, robot) | Equipment / Work Unit; Physical Asset for the hardware | partial | Resource (*glossary*, for `wms_controlled`) | partial | Roles Transport, Carrier, Robot (DMI library) | partial | Glossary distinguishes `wms_controlled` and `controller_autonomous` |
| `equipment_type` | Class with capabilities | Equipment Class | partial | Resource type (*glossary*) | good | SystemUnitClass | good | |
| `lane` / `conveyor_segment` | Physical connection ("can") | – | none | MFS conveyor segment | good | Role Conveyor (extended library) as element, or an InternalLink between two ports | partial | Not part of the ISA-95 equipment model in this form |

## 3. Rules and catalogs (Topology-as-Code, MasterData-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| `movement_rule` | Which movements are allowed ("may") | Inventory operations: process segment | loose | Layout-oriented storage control | partial | – | none | The allowed paths via intermediate places are layout-oriented; process-oriented storage control is closer to OrderOrchestration's workflow steps |
| `movement_policy` | Default allow / explicit only | – | none | – | none | – | none | Specific to this model |
| `replenishment_strategy` | Replenishment rule | Inventory operations scheduling | loose | Replenishment control | good | – | none | |
| `process_type` | Movement-triggering process | Inventory operations: process segment / work master | partial | Warehouse process type | good | Role Process (base library) | loose | |
| `load_unit_type` (MasterData) | Carrier (pallet, bin, carton) | Physical Asset Class or Material Class | loose | Packaging material / HU type | partial | Transport unit of the Material Handling recommendation (not read) | loose | Owned by MasterData-as-Code; Topology keeps a pinned copy |
| `storage_condition` (MasterData) | Ambient / chilled / frozen | Property of material or storage zone | loose | Storage condition | good | Attribute | loose | |
| `blocking_reason` | Why a place is blocked | – | none | Blocking reason (*glossary*) | good | – | none | |
| `hazmat_class` | Compliance classification | Material Class property | loose | Hazardous substance data | partial | Attribute, e.g. with ECLASS semantics | loose | |

## 4. Master data (MasterData-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| `category` | Group of items with inherited defaults | Material Class | partial | Product group | partial | SystemUnitClassLib / product structure | loose | |
| `item` | Article with physical attributes | Material Definition | good | Product | good | Role Product (base library) | partial | Definition, not instance - matches both |
| `packaging` | Packaging / UOM hierarchy | Material Definition properties | loose | Packaging specification; alternative UOMs | partial | – | none | |
| `tracking` | Lot / expiry / serial tracking | Material Lot / Sublot (the instances) | partial | Batch management, shelf-life data | partial | – | none | The repo defines *whether* an item is tracked; lots themselves are runtime |
| `owner` | Stock owner in a multi-client warehouse | – | none | Owner; party entitled to dispose | good | – | none | |

## 5. Orders (OrderOrchestration-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| `order` (header) | Order or sub-order with lineage (`parent_order_id`) and status | Operations Request (inventory) | loose | Warehouse request (e.g. outbound delivery order) | partial | – (the interface class Order means a sequence of steps) | false friend | |
| `position` | One request: exactly one of `load_unit_request`, `material_request`, `suborder_output_request`; lineage via `source_line_id` | Segment Requirement / Material Requirement | loose | Warehouse request item | partial | – | none | **Not composite:** a split creates sub-*orders*, not sub-positions |
| `target` / `order_target` | Next reachable hop vs. final business destination | – | none | – | none | – | none | No direct equivalent in either |
| `split_rule`, `split_dimension` | How an order is split, and by which dimension | – | none | Warehouse order creation rules; delivery split | loose | – | none | |
| `workflow_trigger` | Which process a split piece hands off to | Work Master selection | loose | Warehouse process type determination | partial | – | none | |
| `completion_rule` | What happens when children reach a status | – | none | Status management / PPF actions | loose | – | none | |
| `shortage_policy` | Short-pick / substitution behaviour | – | none | – (configured per process) | loose | – | none | |
| Warehouse task (runtime) | Atomic physical movement | Job Order / Job Response (inventory operations, part 4) | partial | Warehouse task | good | – (runtime: OPC UA) | none | Runtime, not modeled in any repo |
| Stock / lot (runtime) | Current inventory | Material Lot / Sublot | good | Quant; HU stock | good | – | none | Deliberately not modeled in any repo |

## 6. Allocation (Allocation-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| `search_rule` | Stock search sequence and selection | – | none | Stock removal strategy + storage type search sequence | good | – | none | |
| `selection_strategy` | FIFO / FEFO / LIFO, ... | – | none | Stock removal rule | good | – | none | |
| `putaway_rule` | Where arriving stock goes, step by step | – | none | Putaway strategy + storage type search sequence (putaway) | good | – | none | |
| `placement_strategy` | How a place is chosen inside a zone (`NEXT_EMPTY`, `ADD_TO_EXISTING`, `FIXED_BIN_FIRST`, ...) | – | none | Putaway rules (empty bin, addition to existing stock, fixed bin) | good | – | none | |
| `fixed_bin_assignment` | Item fixed to a place with min / max | – | none | Fixed bin assignment | good | – | none | |
| `owner_zones` | Zones reserved for a stock owner | – | none | – (bin / storage type restrictions per owner) | loose | – | none | |

## 7. Composition (Warehouse-as-Code)

| As-code | Meaning | ISA-95 | Fit | SAP EWM | Fit | AutomationML | Fit | Note |
|---|---|---|---|---|---|---|---|---|
| Site manifest (`sites/`) | Which repos' configuration belongs to one facility | Site (as a scope) | loose | Warehouse number customizing as a whole | loose | An AutomationML project of several documents with external references | loose | No equivalent in either - both are single systems, the repo family is several |

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
5. **AutomationML as a bridge to plant engineering.** The same applies to
   AutomationML, in both directions:
   - export the compiled topology as an InstanceHierarchy - Site, Area,
     Storage, StorageUnit and Conveyor roles, with the can-edges as
     InternalLinks between ports - for planning and simulation tools;
   - import a layout planner's AutomationML file as the skeleton of a new
     Topology building, including its geometry (COLLADA), which the
     authored YAML does not have today.
6. **Ports instead of node-to-node edges** - an AutomationML idea worth
   examining. Connections attach to ports of an element (InterfaceClass +
   InternalLink), not to the element as a whole. Conveyors with several
   in- and outlets would need this; reporting points cover part of it
   today.
7. **Role, template and instance kept apart.** AutomationML separates what
   an element is (RoleClass), how it is built (SystemUnitClass) and where
   it is (InstanceHierarchy). The repos have templates
   (`elements/rack_templates.yaml`) and instances, but the role is implicit
   in the list key. An explicit, vendor-neutral role per element would
   ease such an export.

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
- **AutomationML as internal format**, for the same reason. AutomationML
  files are XML with generated GUIDs as ids. They diff poorly, and merging
  them needs dedicated tools. AutomationML has no place for the WMS rules
  (movement rules, allocation, orchestration). PLCopen XML describes
  control logic, not warehouse business rules.
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
- The AutomationML column needs a check against IEC 62714-2 and the
  "Modelling of Material Handling" recommendation, in particular doors
  (Gate?), load units and which library each role class belongs to.

## Sources

- Symestic, ISA-95 overview: https://www.symestic.com/en-us/what-is/isa-95
- TEEPTRAK, ISA-95 equipment hierarchy and B2MML: https://teeptrak.com/en/mes-architecture-isa-95-implementation-2026/
- ServiceNow documentation on the ISA-95 equipment model (storage zone, storage unit): https://www.servicenow.com/docs/r/B3SMebN4ZjjOiPxesW27LQ/QHh3DyEYXMtXFeWi~8ojtQ
- OPC 30040 (OPC UA for AutomationML), model overview: https://reference.opcfoundation.org/specs/OPC-30040/5
- OPC 30040, AutomationMLDMIRoleClassLib (Transport, Storage, Carrier, ...): https://reference.opcfoundation.org/specs/OPC-30040/7.4
- OPC 30040, AutomationMLExtendedRoleClassLib (Enterprise, Site, Area, ...): https://reference.opcfoundation.org/specs/OPC-30040/7.8
- IEC 62714-2 preview: https://vde-verlag.de/iec-normen/preview-pdf/info_iec62714-2{ed1.0}b.pdf
- AutomationML e.V., application recommendation "Modelling of Material Handling in AutomationML": https://www.automationml.org/news/application-recommendation-modelling-of-material-handling-in-automationml-is-available/
- AutomationML e.V., position paper on the Asset Administration Shell and AutomationML: https://www.automationml.org/wp-content/uploads/2021/07/PosPapier_Interrelation-of-AAS-and-AML.pdf
- The `docs/entity-glossary.md` of Topology-as-Code, MasterData-as-Code, OrderOrchestration-as-Code and Allocation-as-Code
