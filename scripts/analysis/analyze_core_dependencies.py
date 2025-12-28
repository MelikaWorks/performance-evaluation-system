#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze dependencies inside a Django app package (default: js/).

USAGE (run from your project root, where the app folder lives):
    python analyze_core_dependencies.py --app js --out out_core_deps

Outputs:
  - out_core_deps/files.csv                 : list of Python files under the app
  - out_core_deps/deps_edges.csv            : intra-app import edges (from, to)
  - out_core_deps/graph.dot                 : Graphviz DOT you can render with: dot -Tpng graph.dot -o graph.png
  - out_core_deps/summary.txt               : quick stats (nodes/edges, orphans, heavy modules)

Notes:
  - Only imports inside the same app (e.g., js.* -> js.*) are considered edges.
  - Migrations, __pycache__, tests, static, templates are ignored by default.
"""

import os
import re
import ast
import argparse
from pathlib import Path
from typing import Dict, Set, List, Tuple

IGNORE_DIRS = {
    "__pycache__","migrations","static","templates","tests","test",".pytest_cache",".mypy_cache",".venv","env","venv",".idea",".vscode"
}
PY_EXT = ".py"

def discover_py_files(app_dir: Path) -> List[Path]:
    files: List[Path] = []
    for root, dirnames, filenames in os.walk(app_dir):
        # filter ignored dirs
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            if fn.endswith(PY_EXT):
                files.append(Path(root) / fn)
    return files

def module_name_from_path(app_dir: Path, p: Path) -> str:
    rel = p.relative_to(app_dir.parent) if app_dir.parent in p.parents else p
    s = rel.as_posix()
    if s.endswith(".py"):
        s = s[:-3]
    if s.endswith("/__init__"):
        s = s[:-9]  # strip /__init__
    return s.replace("/", ".")

def parse_imports(py_file: Path) -> Set[str]:
    try:
        src = py_file.read_text(encoding="utf-8")
    except Exception:
        return set()
    try:
        tree = ast.parse(src, filename=str(py_file))
    except SyntaxError:
        return set()
    imps: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name:
                    imps.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imps.add(node.module)
    return imps

def ensure_out_dir(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

def write_csv(path: Path, rows: List[List[str]], header: List[str]):
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            # naive CSV escaping
            esc = [str(x).replace('"','""') for x in r]
            f.write(",".join(f'"{c}"' if ("," in c or " " in c) else c for c in esc) + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="js", help="App folder name (e.g., js)")
    ap.add_argument("--out", default="out_core_deps", help="Output folder")
    args = ap.parse_args()

    app_dir = Path(args.app).resolve()
    if not app_dir.exists() or not app_dir.is_dir():
        raise SystemExit(f"App folder not found: {app_dir}")

    out_dir = Path(args.out).resolve()
    ensure_out_dir(out_dir)

    # Discover files
    files = discover_py_files(app_dir)
    # Map module name -> file
    mod_by_file: Dict[Path, str] = {}
    file_by_mod: Dict[str, Path] = {}
    for p in files:
        mod = module_name_from_path(app_dir, p)
        mod_by_file[p] = mod
        file_by_mod[mod] = p

    # Collect imports and intra-app edges
    edges: List[Tuple[str,str]] = []
    imports_map: Dict[str, Set[str]] = {}
    app_prefix = f"{app_dir.name}."
    for p in files:
        mod = mod_by_file[p]
        imps = parse_imports(p)
        imports_map[mod] = imps
        for imp in imps:
            # normalize relative "js.something" or "js.something.more"
            if imp == app_dir.name or imp.startswith(app_prefix):
                target = imp
                edges.append((mod, target))

    # Write files.csv
    files_rows = [[str(file_by_mod[m]), m] for m in sorted(file_by_mod.keys())]
    write_csv(out_dir / "files.csv", files_rows, ["path","module"])

    # Write deps_edges.csv
    edge_rows = [[a,b] for (a,b) in sorted(set(edges))]
    write_csv(out_dir / "deps_edges.csv", edge_rows, ["from","to"])

    # Build DOT
    dot_lines = ["digraph G {", '  graph [rankdir="LR"];', '  node [shape=box, fontsize=10];']
    for m in sorted(file_by_mod.keys()):
        label = m.split(".",1)[-1] if m.startswith(app_dir.name + ".") else m
        dot_lines.append(f'  "{m}" [label="{label}"];')
    for a,b in sorted(set(edges)):
        dot_lines.append(f'  "{a}" -> "{b}";')
    dot_lines.append("}")
    (out_dir / "graph.dot").write_text("\n".join(dot_lines), encoding="utf-8")

    # Summary
    nodes = len(file_by_mod)
    edges_count = len(set(edges))
    # orphans: nodes with no in-degree and no out-degree (inside app)
    outgoing = {}
    incoming = {}
    for m in file_by_mod:
        outgoing[m] = 0
        incoming[m] = 0
    for a,b in set(edges):
        outgoing[a] += 1
        incoming[b] += 1
    orphans = [m for m in file_by_mod if outgoing[m]==0 and incoming[m]==0]
    heavy = sorted(file_by_mod.keys(), key=lambda m: outgoing[m], reverse=True)[:10]

    summary = [
        f"Nodes (modules): {nodes}",
        f"Edges (imports inside app): {edges_count}",
        f"Orphans (no in/out edges): {len(orphans)}",
        "",
        "Top 10 modules by outgoing edges:",
        *[f"  - {m} (out={outgoing[m]}, in={incoming[m]})" for m in heavy],
        "",
        "Orphans:",
        *[f"  - {m}" for m in orphans]
    ]
    (out_dir / "summary.txt").write_text("\n".join(summary), encoding="utf-8")

    print("✅ Done.")
    print(f"- Files:      {out_dir / 'files.csv'}")
    print(f"- Edges:      {out_dir / 'deps_edges.csv'}")
    print(f"- Graph DOT:  {out_dir / 'graph.dot'}")
    print(f"- Summary:    {out_dir / 'summary.txt'}")
    print("\nRender graph with Graphviz (optional):")
    print(f"  dot -Tpng {(out_dir / 'graph.dot')} -o {(out_dir / 'graph.png')}")

if __name__ == "__main__":
    main()
