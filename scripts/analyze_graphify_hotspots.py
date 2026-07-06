from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

NOISE_PARTS = (
    "/__tests__/",
    "/node_modules/",
    "/graphify-out/",
    "/proto/",
    "/__pycache__/",
)
NOISE_PREFIXES = (
    "backend/tests/",
    "scraper/tests/",
    "shared/integrations/storage_providers/clouddrive2/proto/",
)
RUNTIME_PREFIXES = (
    "backend/app/",
    "frontend/src/",
    "shared/",
    "scraper/",
)


def is_noise_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized.startswith(NOISE_PREFIXES):
        return True
    return any(part in f"/{normalized}" for part in NOISE_PARTS)


def is_runtime_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized.startswith(RUNTIME_PREFIXES) and not is_noise_path(normalized)


def current_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "<unknown>"


def _node_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or node.get("id") or "")
    source_file = str(node.get("source_file") or "")
    source_location = str(node.get("source_location") or "")
    suffix = f":{source_location}" if source_location else ""
    return f"{label} [{source_file}{suffix}]"


def _format_counter(title: str, counter: Counter[str], nodes: dict[str, dict[str, Any]], top: int) -> list[str]:
    lines = [title]
    for node_id, count in counter.most_common(top):
        node = nodes[node_id]
        lines.append(f"- {count:>4} {_node_label(node)}")
    if len(lines) == 1:
        lines.append("- none")
    return lines


def analyze_graph(graph_path: Path, *, top: int = 10, repo_root: Path | None = None) -> str:
    repo_root = repo_root or Path.cwd()
    graph = json.loads(graph_path.read_text())
    nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
    runtime_nodes = {
        node_id
        for node_id, node in nodes.items()
        if is_runtime_path(str(node.get("source_file") or ""))
    }
    degree: Counter[str] = Counter()
    outdegree: Counter[str] = Counter()
    indegree: Counter[str] = Counter()
    for link in graph.get("links", []):
        source = str(link.get("source"))
        target = str(link.get("target"))
        if source in runtime_nodes and target in runtime_nodes:
            degree[source] += 1
            degree[target] += 1
            outdegree[source] += 1
            indegree[target] += 1

    built_at = str(graph.get("built_at_commit") or "<missing>")
    head = current_head(repo_root)
    lines = [
        f"Graph: {graph_path}",
        f"built_at_commit: {built_at}",
        f"current_head: {head}",
    ]
    if built_at != "<missing>" and head != "<unknown>" and built_at != head:
        lines.append("WARNING: graph built_at_commit differs from current HEAD")
    lines.append("")
    lines.extend(_format_counter("Top runtime degree", degree, nodes, top))
    lines.append("")
    lines.extend(_format_counter("Top runtime outdegree", outdegree, nodes, top))
    lines.append("")
    lines.extend(_format_counter("Top runtime indegree", indegree, nodes, top))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter graphify hotspots for runtime code review.")
    parser.add_argument("graph", type=Path, help="Path to graphify graph.json")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    print(analyze_graph(args.graph, top=args.top))


if __name__ == "__main__":
    main()
