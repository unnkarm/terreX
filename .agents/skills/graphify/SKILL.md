---
name: graphify
description: Knowledge graph CLI and query engine for codebase architecture, dependency paths, and community clusters. Use when investigating cross-module relationships or tracing architecture.
---

# Graphify Reference

Graphify maintains a precomputed knowledge graph in `graphify-out/` to navigate codebase architecture without costly file scans.

## When to Use
- Answering architectural, cross-module dependency, or data flow questions
- Finding shortest paths between services or subsystems
- Inspecting core abstractions ("god nodes") and community clusters

## Fast CLI Commands (Token-Saving)
- `graphify query "<question>"`: BFS traversal across graph nodes (capped at ~2,000 tokens).
- `graphify query "<question>" --dfs`: DFS traversal to trace a specific call/dependency chain.
- `graphify path "<Source>" "<Target>"`: Shortest dependency path between two symbols or files.
- `graphify explain "<Node>"`: Node details, community ID, and incoming/outgoing connections.
- `graphify update .`: AST-only incremental graph refresh after code edits (0 LLM tokens).

## Core Artifacts
- `graphify-out/GRAPH_REPORT.md`: God nodes, community hubs, and surprising couplings.
- `graphify-out/graph.html`: Interactive visual graph for browser inspection.
- `graphify-out/graph.json`: Graph structure and node/edge data.
