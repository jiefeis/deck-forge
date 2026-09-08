# Consulting diagrams: from evidence to editable exhibits

Read when a new or authorized redesigned page needs a relationship diagram.
Use `visual-evidence.md` for asset sourcing and factual boundaries. Preserve
native-edit scope, template geometry, and package rules; this guide does not
authorize redesign during translation or minimal edits.

## Contents

- Choose the relationship before the layout
- When quantities determine geometry
- Write a compact drawing brief
- Construct the exhibit
- Diagram recipes
- Tools and editable output
- Acceptance and repair

## Choose the relationship before the layout

First name what the marks must mean. An arrow can mean sequence, transfer,
influence, or feedback; containment can mean ownership or membership; a branch
can mean decomposition or a decision. These are not interchangeable.

| Audience question | Suitable exhibit | Evidence needed / common mistake |
| --- | --- | --- |
| What happens next? | process or value chain | ordered stages; a row of unrelated topics is not a process |
| Who acts and where is the handoff? | swimlanes | actors, steps, transfers and exception ownership; lanes are not decorative sections |
| What drives this outcome? | driver tree or causal map | decomposition rules or supported causal links; association does not establish causality |
| What belongs to what? | hierarchy or nested groups | parent/member relation; nesting does not imply sequence or data flow |
| How does the system work together? | architecture/system map | components, boundaries, actual exchanges; proximity alone does not establish a connection |
| What changes after observing a result? | feedback loop/state flow | return target, observation and next action; no closed loop without a real return relation |
| Where do options differ? | comparison matrix | common dimensions and comparable evidence; do not invent rankings to fill quadrants |
| Where does time/value accumulate? | value chain plus measure track | units and stage values; equal-width stages must not imply equal duration |

Use a chart or table when the question is primarily quantitative. A diagram
with numbers beside boxes is not a substitute for plotting the relationship.
For a physical subject, a photo or concept illustration plus vector annotations
may explain more than an abstract system map. Select the medium from the question.

## When quantities determine geometry

If values determine position, length or area, treat the exhibit as a chart and
calculate those marks before decorating it. If row/column labels identify an
exact fact, use a table. Choose an encoding that answers the actual question:

| Question | Starting point | Data check |
| --- | --- | --- |
| Which is larger, by how much? | aligned bars or dots | common unit and zero baseline for bars |
| How did comparable items change? | dumbbell or paired bars | same items and comparable periods |
| What explains the net change? | waterfall/bridge | ordered signed contributions reconcile to the final total |
| How does it evolve over time? | line chart | real time positions, gaps and observed/estimated distinction |
| How is a whole composed? | stacked bars or simple part-to-whole | exhaustive parts, shared denominator; no double counting |
| How does a population vary? | histogram, dot distribution or box plot | actual observations and explicit bin/summary rules |
| Where does a measured flow go? | Sankey only if helpful | flow quantities reconcile at each represented junction |
| How should options be prioritized? | sorted measures or a decision table | use a two-axis plot only when both dimensions are supported |

Record the domain, baseline and units; calculate mark coordinates from values.
After rendering, reverse-check key positions, segment heights, endpoints and
totals against the data. Keep comparable panels on the same scale and category
order. Missing data is a gap, not a zero. Do not use area/3D effects that obscure
the intended measure or give illustrative values the appearance of measurement.

## Write a compact drawing brief

Add these facts to the existing page outline or an HTML comment; a separate
schema or planning file is unnecessary for a small diagram:

- **Claim:** the one conclusion this page supports, or the question it explains.
- **Objects:** exact labels, roles, grouping and source; one identity per object.
  Use stable IDs when objects appear across multiple views or need text editing.
- **Relations:** `from → to : meaning`, with direction, condition, evidence and
  uncertainty where relevant. Record a common junction only if it really exists.
- **Encoding:** what position, length, area, containment, line style and color
  mean. Mark unmeasured schematic spacing as schematic.
- **Reading path:** primary entry, main argument, exception/feedback side paths,
  and the detail the audience must notice.

Example: `low-confidence result → engineer review : request confirmation` is
an exception handoff, not evidence that engineers own every execution step.
Keep unknown participants, timings, thresholds and causal claims unresolved.

## Construct the exhibit

1. Build the semantic skeleton with native text, boxes and connectors before
   polishing. Check every object and relation against the brief. Do not add
   symmetry, reciprocal arrows, closure, or duplicated nodes for visual balance.
2. Assign the main reading direction and group boundaries. Reserve a separate
   corridor for exceptions and returns. Space from actual label bounds, not
   only node centers; long labels need room before they need smaller type.
3. Draw containers and routes behind node fills, then labels and annotations.
   Keep text independent of raster artwork and shape paths. Use the deck's
   existing title/body/caption tokens, stroke weights and color meanings.
4. Attach each connector to an intentional boundary/port. End arrows at the
   destination boundary; never beneath a node or on unrelated text. Distinct
   inbound/outbound exchanges use separate ports or visibly separated routes.
5. Route orthogonally when that clarifies groups and lanes; use curves for
   purposeful return paths. A shared trunk denotes a real junction. Separate
   unrelated crossings visually, and never let a line run through another node.
6. Add emphasis to the evidence-bearing stage or relationship. Keep the rest
   quiet. Place short implications beside the relevant evidence rather than
   appending a second grid of explanatory cards.
7. Render at the final slide size and in the static export state. Follow
   "Acceptance and repair" below before treating the exhibit as finished.

## Diagram recipes

### Process and value chain

Put stages in sequence with visible start/end and a verb at each action.
Keep support capabilities in a separate band; they do not become sequential
stages merely because they are drawn underneath. For stage time/cost, use a
separate proportional track or accurately scaled segments. Label units and
totals, and identify the bottleneck from evidence. A larger colored stage alone
does not prove it constrains throughput.

### Swimlanes and handoffs

Choose lanes for stable actors/functions and columns for ordered stages.
Place an action in the lane of the actor performing it. Cross-lane connectors
name the artifact, decision or request transferred. Keep conditional outcomes
separate and show supplied exception owners and exits; mark missing ones as
unresolved rather than assigning them. A line ending in blank space is not an
escalation route. Duplicate a shared actor only as an explicit
visual alias, not as a new participant.

### Driver tree and causal map

A driver tree may express additive parts, multiplicative factors, or a supported
logical breakdown; state the formula or relation instead of assuming every
branch sums to its parent. For an additive decomposition, use non-overlapping
parts on one stated basis. Otherwise label categories or overlapping contributors
without claiming a sum. Use plain hierarchy connectors for membership, explicit
formula links for a calculation, and directed labeled edges for causal assertions. Show proposed
causes as hypotheses with a distinct line style and a visible legend. Place
the required observation or test near the hypothesis. Do not use arrowheads
to turn an untested explanation into a proven mechanism.

### Architecture, boundaries and feedback

Group by the actual system or responsibility boundary. Give each node a role;
name what meaningful edges carry. Distinguish a data exchange from control,
ownership or sequence. Show a dependency on one side of a boundary only if
that is where it resides. For a control/learning loop, trace output → observation
→ decision → changed action when those roles exist. For causal feedback, follow
the actual closed influence path without inventing a controller or observer.
Return to the actual receiving node, not the nearest box.
Retain failure/review routes when they change the story.
Do not label a loop reinforcing/balancing without supported causal polarity.

### Matrix and option positioning

Define both axes and how positions are derived. Use measured values for a
scatter plot and an explicit rubric for qualitative scores. Show unknowns as
unknown; do not space items evenly to imply measurement. Thresholds and quadrant
names must come from the analysis or be labeled proposed. If only categories
are supported, use a comparison table instead of invented coordinates.
An unscored item stays outside the plot in an explicitly unassessed list; the
center of a matrix does not mean "unknown".

## Tools and editable output

- For a small diagram, use inline SVG in HTML or native PPTX shapes/connectors.
  Reuse an appropriate local example's construction, not its facts or labels.
  Keep labels as SVG `<text>`/`<tspan>` or native text frames, with stable
  `data-text-id` for HTML text editing; do not outline lettering into paths.
- For branching/cyclic topology that is hard to route, use an available layout
  engine or diagram skill (for example Mermaid/Graphviz/ELK or Archify) if it
  produces inspectable output. Do not install a new dependency just to draw a
  few boxes. Read that tool's current interface rather than guessing commands.
- Treat generated layout as a geometry proposal. Preserve relation meaning,
  restyle with the deck's tokens, and remove standalone viewer chrome before
  embedding. The containing slide still obeys Deck Forge's fixed stage/export.
- Export editable SVG separately when useful. Keep data, source values, labels
  and diagram structure available for revision; rasterize only when the output
  contract permits it. A generated full-slide bitmap is not editable analysis.
- Native PPTX editability is specific: independent lines may be editable yet
  fail to follow a moved node. If attached editing is required, use real
  connector anchors and verify them after save/reopen. Do not promise attachment
  from shape type alone. An SVG inserted as one picture is vector artwork,
  not a set of independently editable PowerPoint labels.

## Acceptance and repair

Check three layers independently; passing one does not prove the other two:

1. **Meaning:** every important node and edge maps to source evidence or an
   explicit hypothesis; directions, grouping, branching, return paths, values,
   units and totals agree. No invented equality, causality, position or closure.
2. **Geometry:** labels remain readable, arrowheads visible, edges avoid unrelated
   objects, crossings are unambiguous, and content fits the final static slide.
3. **Argument:** at thumbnail size the primary relationship and emphasis are
   clear; at full size the audience can inspect the evidence behind the title.

Trace both directions: every required relationship appears, and every drawn
connector has a justified meaning. Strip color mentally; if the relation becomes
unreadable, labels/grouping must improve. Color cannot carry the entire logic.

Repair in this order: clarify grouping/main path → move an annotation → widen
the relevant gap or route corridor → change the route → simplify only redundant
wording → separate a genuinely different analytical question. Do not delete an
essential edge, invent an alias, or shrink labels just to clear an overlap.

Use HTML/PDF and native scope audits afterwards, with an actual visual pass.
Those checks do not know whether a cause is true or a matrix score is justified.
