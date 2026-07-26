# 09 · A neat diagram with the wrong flywheel topology

**Contract under test:** Nodes, directed edges, shared backbones, and cycles are
content, not decoration.

## Setup

Provide a mother-draft graph:

```text
A → B → C → D
D → E → G → A
D → F → H → A
```

The candidate slide should initially be tempting but wrong: two clean rows that
duplicate D and A and omit the return edges.

## User prompt (verbatim)

> 把这一页双飞轮重画清楚，按母稿关系来。不要一串换行箭头，要用图形表达。

## PASS criteria

- The agent freezes a node/edge/cycle contract before or while redesigning.
- The final render contains one shared A–D backbone, one D branch to E and F,
  and visible returns G→A and H→A.
- D and A are not duplicated into semantically different proxy nodes.
- Node wording remains faithful to the mother draft.
- The two loop explanations, analogy/evidence, and conclusion are still
  accounted for.
- An independent reviewer traces the raw source graph against the final render;
  if unavailable, a separated fresh second pass traces the raw adjacency list.

## FAIL signals

- Presenting D→E→G and D→F→H as two open chains.
- Returning to the wrong node.
- Replacing the graph with a multiline `A→B→C` text string.
- Declaring PASS because the page is balanced and arrows do not cross.
