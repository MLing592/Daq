#!/usr/bin/env python3
"""
Smart layout engine for drawio files.

Handles three page types:
  1. Class diagrams (swimlane with child cells)        -> graphviz layout for top-level swimlanes
  2. Container pages (dashed boxes containing nodes)    -> custom layered layout
  3. Plain flowcharts                                   -> graphviz layout

Layout rules:
  R1. No meaningless edges — edges without source or target are removed;
      edges referencing non-existent vertices are removed.
  R2. Same-level alignment — all container boxes left-aligned at page margin;
      children inside containers arranged in a grid with aligned columns
      (same X for same column) and aligned rows (same Y for same row).
  R3. Uniform sizing — child elements normalized to a standard size (median);
      elements significantly larger (>30%) keep their original size.
  R4. Edge optimization:
      - All edges use orthogonal routing (vertical/horizontal only)
      - Multiple edges to same target converge to shared entry point
      - Multiple edges from same source spread exit points
      - Bidirectional pairs offset to avoid overlap
      - All manual waypoints cleared for clean recalculation

Usage:
    python layout_drawio.py input.drawio output.drawio
"""

import re
import sys
import math
import subprocess
import xml.etree.ElementTree as ET

DOT = r"C:\Program Files\Graphviz\bin\dot.exe"
PPI = 72  # pixels per inch for graphviz

# Layout constants
GAP_Y          = 35   # vertical gap between elements
GAP_X_INNER    = 30   # horizontal gap between nodes inside a container
GAP_Y_INNER    = 25   # vertical gap between rows inside a container
PAD_CONTAINER  = 30   # padding inside container (bottom/sides)
TITLE_H        = 35   # container title bar height
PAGE_MARGIN    = 30   # page left/top margin
SIZE_TOLERANCE = 0.30 # ratio above standard to keep original size (30%)


# ── XML helpers ────────────────────────────────────────────────────────────

def parse_drawio(path):
    ET.register_namespace("", "")
    tree = ET.parse(path)
    root = tree.getroot()
    diagrams = [(d.get("name", ""), d) for d in root.findall(".//diagram")]
    return tree, diagrams


def get_geometry(cell):
    """Return (x, y, w, h) from mxGeometry, or None."""
    geo = cell.find(".//mxGeometry")
    if geo is None:
        return None
    x = float(geo.get("x", "0"))
    y = float(geo.get("y", "0"))
    w = float(geo.get("width", "200"))
    h = float(geo.get("height", "60"))
    return (x, y, w, h)


def set_geometry(cell, x, y, w=None, h=None):
    geo = cell.find(".//mxGeometry")
    if geo is None:
        return
    geo.set("x", str(int(round(x))))
    geo.set("y", str(int(round(y))))
    if w is not None:
        geo.set("width", str(int(round(w))))
    if h is not None:
        geo.set("height", str(int(round(h))))


def get_page_width(diagram):
    model = diagram.find(".//mxGraphModel")
    if model is not None:
        return int(model.get("pageWidth", "1200"))
    return 1200


# ── Classification ──────────────────────────────────────────────────────────

def is_container_box(cell):
    """A container box is a large dashed translucent rectangle that visually
    contains other nodes (e.g. '初始化阶段', '底层硬件层')."""
    style = cell.get("style", "")
    return "dashed=1" in style and "opacity=70" in style


def is_swimlane(cell):
    """Swimlane = UML class box with child cells stacked inside."""
    style = cell.get("style", "")
    return "swimlane" in style


def is_note(cell):
    style = cell.get("style", "")
    return "shape=note" in style


# ── R3: Size normalization ─────────────────────────────────────────────────

def normalize_sizes(vertices_dict, exclude_ids=None):
    """
    Rule 3: Normalize vertex sizes to be as uniform as possible.

    Strategy:
      - Calculate standard width and height as the median of all sizes.
      - Resize all elements to standard, UNLESS an element is significantly
        larger than standard (> SIZE_TOLERANCE ratio), in which case it
        keeps its original size (content too long to shrink).

    Args:
      vertices_dict: {id: {w, h, ...}} - modified in place
      exclude_ids: set of ids to skip (e.g. containers, notes)

    Returns:
      {id: (w, h)} - new sizes for elements that were resized
    """
    exclude_ids = exclude_ids or set()
    candidates = {
        vid: v for vid, v in vertices_dict.items()
        if vid not in exclude_ids
    }
    if len(candidates) < 2:
        return {}

    widths = sorted(v["w"] for v in candidates.values())
    heights = sorted(v["h"] for v in candidates.values())

    # Standard = median
    mid = len(widths) // 2
    std_w = widths[mid]
    std_h = heights[mid]

    sizes = {}
    for vid, v in candidates.items():
        orig_w = v["w"]
        orig_h = v["h"]
        # Resize to standard unless significantly larger
        if orig_w <= std_w * (1 + SIZE_TOLERANCE):
            new_w = std_w
        else:
            new_w = orig_w
        if orig_h <= std_h * (1 + SIZE_TOLERANCE):
            new_h = std_h
        else:
            new_h = orig_h

        if new_w != orig_w or new_h != orig_h:
            v["w"] = new_w
            v["h"] = new_h
            sizes[vid] = (new_w, new_h)

    return sizes


# ── Extract page structure ──────────────────────────────────────────────────

def extract_page(diagram):
    """
    Returns:
      top_vertices: {id: {x, y, w, h, style, value, element, parent}}
      edges: [{id, source, target, element}]
      child_vertices: {id: {element, parent_id}}  (vertices with parent != "1")
      invalid_edges: [element]  — edge elements to remove from XML (R1)
    """
    top_vertices = {}
    edges = []
    child_vertices = {}
    invalid_edges = []

    for cell in diagram.findall(".//mxCell"):
        cid = cell.get("id", "")
        parent = cell.get("parent", "")
        vertex = cell.get("vertex", "")
        edge = cell.get("edge", "")

        if cid in ("0", "1"):
            continue

        if edge == "1":
            src = cell.get("source", "")
            tgt = cell.get("target", "")
            # R1: Skip edges without source or target — mark for removal
            if not src or not tgt:
                invalid_edges.append(cell)
                continue
            edges.append({
                "id": cid,
                "source": src,
                "target": tgt,
                "element": cell,
            })
        elif vertex == "1":
            geo = get_geometry(cell)
            if geo is None:
                continue
            entry = {
                "x": geo[0], "y": geo[1], "w": geo[2], "h": geo[3],
                "style": cell.get("style", ""),
                "value": cell.get("value", ""),
                "element": cell,
                "parent": parent,
            }
            if parent == "1":
                top_vertices[cid] = entry
            else:
                child_vertices[cid] = entry

    return top_vertices, edges, child_vertices, invalid_edges


# ── R1: Edge filtering ─────────────────────────────────────────────────────

def filter_valid_edges(edges, valid_vertex_ids):
    """
    Rule 1: Remove edges that reference non-existent vertices.
    Returns filtered edge list.
    """
    return [
        e for e in edges
        if e["source"] in valid_vertex_ids and e["target"] in valid_vertex_ids
    ]


# ── Container layout (custom) ───────────────────────────────────────────────

def layout_container_page(top_vertices, edges, page_width, diagram):
    """
    Layout pages that have container boxes.

    Strategy:
      1. Identify container boxes and their contained children (by coordinate overlap)
      2. R3: Normalize child sizes to a standard size
      3. R2: All containers left-aligned at PAGE_MARGIN
      4. R2: Children arranged in a grid inside each container
         - Same column -> same X (vertical alignment)
         - Same row -> same Y (horizontal alignment)
      5. Resize containers to fit their children grid
      6. Auto-expand page width if children need more space
    """
    containers = {}   # {id: vertex}
    free_nodes = {}    # {id: vertex}

    for vid, v in top_vertices.items():
        if is_container_box(v["element"]):
            containers[vid] = v
        else:
            free_nodes[vid] = v  # notes and regular nodes

    # Map children to containers (each child assigned to at most one container)
    container_children = {}  # {container_id: [child_ids]}
    assigned = set()
    # Sort containers by area (smallest first) so smaller containers claim children first
    sorted_containers = sorted(containers.items(), key=lambda x: x[1]["w"] * x[1]["h"])
    for cid, cdata in sorted_containers:
        cx, cy, cw, ch = cdata["x"], cdata["y"], cdata["w"], cdata["h"]
        children = []
        for fid, fdata in free_nodes.items():
            if fid in assigned or is_note(fdata["element"]):
                continue
            mx = fdata["x"] + fdata["w"] / 2
            my = fdata["y"] + fdata["h"] / 2
            if cx < mx < cx + cw and cy < my < cy + ch:
                children.append(fid)
                assigned.add(fid)
        container_children[cid] = children

    all_children = set()
    for kids in container_children.values():
        all_children.update(kids)

    standalone = [fid for fid in free_nodes if fid not in all_children]

    # ── R3: Normalize ALL free node sizes (children + standalone) ─────
    # Exclude notes (they have special sizing)
    nodes_to_normalize = {
        fid: fdata for fid, fdata in free_nodes.items()
        if not is_note(fdata["element"])
    }
    all_sizes = normalize_sizes(nodes_to_normalize)

    # Sort everything by original Y
    elements = []
    for cid in containers:
        elements.append(("container", cid, containers[cid]["y"]))
    for sid in standalone:
        elements.append(("node", sid, free_nodes[sid]["y"]))
    elements.sort(key=lambda e: e[2])

    # Layout top-to-bottom
    current_y = PAGE_MARGIN
    positions = {}   # {id: (x, y)}
    sizes = {}       # {id: (w, h)}  only for resized elements

    usable_width = page_width - 2 * PAGE_MARGIN

    # ── R2: Calculate grid layout parameters ───────────────────────────
    # Determine standard child size (after normalization)
    if all_children:
        child_widths = [free_nodes[c]["w"] for c in all_children]
        child_heights = [free_nodes[c]["h"] for c in all_children]
        std_child_w = max(child_widths)  # use max so all fit
        std_child_h = max(child_heights)
    else:
        std_child_w = 200
        std_child_h = 60

    # Calculate how many columns fit in the default page width
    inner_w = usable_width - 2 * PAD_CONTAINER
    max_per_row = max(1, int((inner_w + GAP_X_INNER) / (std_child_w + GAP_X_INNER)))

    # Check if any container needs more columns than max_per_row
    for cid in containers:
        n = len(container_children[cid])
        if n > max_per_row:
            needed_cols = min(n, max_per_row)
            needed_w = needed_cols * std_child_w + (needed_cols - 1) * GAP_X_INNER + 2 * PAD_CONTAINER
            if needed_w > usable_width:
                usable_width = needed_w
                page_width = usable_width + 2 * PAGE_MARGIN
                model = diagram.find(".//mxGraphModel")
                if model is not None:
                    model.set("pageWidth", str(int(page_width)))
                inner_w = usable_width - 2 * PAD_CONTAINER
                max_per_row = max(1, int((inner_w + GAP_X_INNER) / (std_child_w + GAP_X_INNER)))

    container_w = usable_width

    for elem_type, eid, _ in elements:
        if elem_type == "node":
            v = free_nodes[eid]
            # Center horizontally
            x = (page_width - v["w"]) / 2
            positions[eid] = (x, current_y)
            # Apply normalized size for standalone nodes
            if eid in all_sizes:
                sizes[eid] = all_sizes[eid]
            current_y += v["h"] + GAP_Y
        else:
            v = containers[eid]
            children = container_children[eid]

            if children:
                # Sort children by original X then Y
                children.sort(key=lambda c: (free_nodes[c]["y"], free_nodes[c]["x"]))

                n = len(children)
                num_rows = math.ceil(n / max_per_row)
                cols_per_row = [min(max_per_row, n - r * max_per_row) for r in range(num_rows)]

                # ── R2: Grid layout with aligned columns ─────────────
                # All rows use the same column X positions (based on max_per_row)
                # This ensures vertical alignment across rows
                col_x_start = PAGE_MARGIN + PAD_CONTAINER
                col_widths = [std_child_w] * max_per_row
                col_x = [col_x_start + j * (std_child_w + GAP_X_INNER) for j in range(max_per_row)]

                child_y_start = current_y + TITLE_H
                max_row_h = 0

                child_idx = 0
                for row_idx in range(num_rows):
                    n_cols = cols_per_row[row_idx]
                    row_y = child_y_start + row_idx * (std_child_h + GAP_Y_INNER)

                    # Center the row if it has fewer columns than max_per_row
                    row_total_w = n_cols * std_child_w + (n_cols - 1) * GAP_X_INNER
                    row_offset = (container_w - 2 * PAD_CONTAINER - row_total_w) / 2

                    for col_idx in range(n_cols):
                        if child_idx >= n:
                            break
                        cid = children[child_idx]
                        cdata = free_nodes[cid]
                        # Use aligned column X, add row offset for centering
                        x = col_x_start + row_offset + col_idx * (std_child_w + GAP_X_INNER)
                        positions[cid] = (x, row_y)
                        # Apply normalized size
                        if cid in all_sizes:
                            sizes[cid] = all_sizes[cid]
                        child_idx += 1

                    max_row_h = std_child_h

                container_h = TITLE_H + num_rows * std_child_h + (num_rows - 1) * GAP_Y_INNER + PAD_CONTAINER
            else:
                container_h = v["h"]

            # R2: All containers left-aligned at PAGE_MARGIN
            positions[eid] = (PAGE_MARGIN, current_y)
            sizes[eid] = (container_w, container_h)
            current_y += container_h + GAP_Y

    # Notes: place at bottom, full width
    for fid in standalone:
        if is_note(free_nodes[fid]["element"]):
            v = free_nodes[fid]
            positions[fid] = (PAGE_MARGIN, current_y)
            sizes[fid] = (container_w, v["h"])
            current_y += v["h"] + GAP_Y

    return positions, sizes


# ── Graphviz layout (for class diagrams & plain flowcharts) ──────────────────

def graphviz_layout(vertices, edges, rankdir="TB"):
    """
    Use graphviz dot to compute positions.
    Returns: {id: (x, y)} or None on failure.
    """
    lines = [
        "digraph G {",
        f"  rankdir={rankdir};",
        "  nodesep=0.5;",
        "  ranksep=0.8;",
        '  node [shape=box, style=""];',
    ]

    for vid, v in vertices.items():
        w_in = v["w"] / PPI
        h_in = v["h"] / PPI
        label = v["value"].split("&#xa;")[0].split("\n")[0][:25] if v["value"] else vid
        label = label.replace('"', '\\"')
        lines.append(f'  "{vid}" [label="{label}", width={w_in:.4f}, height={h_in:.4f}, fixedsize=true];')

    for e in edges:
        s, t = e["source"], e["target"]
        if s in vertices and t in vertices:
            lines.append(f'  "{s}" -> "{t}";')

    lines.append("}")
    dot_input = "\n".join(lines)

    try:
        result = subprocess.run(
            [DOT, "-Tplain"],
            input=dot_input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout:
            return None
    except Exception:
        return None

    positions = {}
    for line in result.stdout.strip().split("\n"):
        parts = line.split()
        if not parts or parts[0] != "node":
            continue
        name = parts[1].strip('"')
        x_in = float(parts[2])
        y_in = float(parts[3])
        w_in = float(parts[4])
        h_in = float(parts[5])
        x_px = x_in * PPI - w_in * PPI / 2
        y_px = -y_in * PPI - h_in * PPI / 2
        positions[name] = (x_px, y_px)

    if positions:
        min_x = min(p[0] for p in positions.values())
        min_y = min(p[1] for p in positions.values())
        positions = {
            k: (v[0] - min_x + PAGE_MARGIN, v[1] - min_y + PAGE_MARGIN)
            for k, v in positions.items()
        }

    return positions


# ── Apply layout ────────────────────────────────────────────────────────────

def apply_positions(top_vertices, positions, sizes):
    """Update XML geometry with computed positions."""
    for vid, (x, y) in positions.items():
        if vid not in top_vertices:
            continue
        v = top_vertices[vid]
        if vid in sizes:
            w, h = sizes[vid]
            set_geometry(v["element"], x, y, w, h)
        else:
            set_geometry(v["element"], x, y)


def clear_edge_waypoints(edges):
    """Remove manual edge waypoints so drawio recalculates routes."""
    for e in edges:
        elem = e["element"]
        geo = elem.find(".//mxGeometry")
        if geo is None:
            continue
        # Remove <Array as="points"> child
        for arr in geo.findall(".//Array"):
            geo.remove(arr)


# ── Edge optimization ───────────────────────────────────────────────────────

def _strip_style_attr(style, keys):
    """Remove specified attributes from a drawio style string."""
    for key in keys:
        style = re.sub(rf'{key}=[^;]*;?', '', style)
    return style


def optimize_edges(edges, vertices_info, positions):
    """
    Optimize edge connection points for clean orthogonal routing.

    Rules:
      1. All edges use edgeStyle=orthogonalEdgeStyle (no diagonals)
      2. Multiple edges TO same target: converge to shared entry point
      3. Multiple edges FROM same source: spread exit points
      4. Bidirectional pairs (A->B and B->A): offset to avoid overlap
      5. Direction determined by relative node positions (vertical vs horizontal)
      6. All manual waypoints cleared

    Args:
      edges: list of {id, source, target, element}
      vertices_info: {id: {w, h, ...}} - size info for all vertices
      positions: {id: (x, y)} - absolute positions of all vertices
    """
    # Group edges by (source, target) pair
    by_pair = {}
    for i, e in enumerate(edges):
        key = (e["source"], e["target"])
        by_pair.setdefault(key, []).append(i)

    # Find bidirectional pairs (A->B and B->A both exist)
    bidir_set = set()
    for (s, t) in by_pair:
        if s != t and (t, s) in by_pair:
            bidir_set.add(frozenset([s, t]))

    # Group by source and target
    outgoing = {}  # {source_id: [edge_indices]}
    incoming = {}  # {target_id: [edge_indices]}
    for i, e in enumerate(edges):
        outgoing.setdefault(e["source"], []).append(i)
        incoming.setdefault(e["target"], []).append(i)

    for i, e in enumerate(edges):
        s, t = e["source"], e["target"]
        elem = e["element"]
        style = elem.get("style", "")

        # Skip edges where we don't have position info
        if s not in positions or t not in positions:
            # Still ensure orthogonal style
            style = _strip_style_attr(style, ["edgeStyle"])
            style += "edgeStyle=orthogonalEdgeStyle;"
            elem.set("style", style)
            continue

        if s not in vertices_info or t not in vertices_info:
            style = _strip_style_attr(style, ["edgeStyle"])
            style += "edgeStyle=orthogonalEdgeStyle;"
            elem.set("style", style)
            continue

        # --- 1. Ensure orthogonal edge style ---
        style = _strip_style_attr(style, [
            "edgeStyle", "rounded", "curved", "noEdgeStyle",
        ])
        style += "edgeStyle=orthogonalEdgeStyle;rounded=1;curved=0;"

        # Remove existing connection point attributes
        style = _strip_style_attr(style, [
            "exitX", "exitY", "entryX", "entryY",
            "exitDx", "exitDy", "entryDx", "entryDy",
            "jettySize", "sourceJettySize", "targetJettySize",
            "orthogonalLoop",
        ])

        # --- 2. Determine relative position ---
        sx, sy = positions[s][0], positions[s][1]
        tx, ty = positions[t][0], positions[t][1]
        sw = vertices_info[s].get("w", 200)
        sh = vertices_info[s].get("h", 60)
        tw = vertices_info[t].get("w", 200)
        th = vertices_info[t].get("h", 60)

        s_cx, s_cy = sx + sw / 2, sy + sh / 2
        t_cx, t_cy = tx + tw / 2, ty + th / 2

        dx = t_cx - s_cx
        dy = t_cy - s_cy

        is_bidir = frozenset([s, t]) in bidir_set

        # --- 3. Determine flow direction ---
        # Use vertical overlap test: if nodes don't overlap vertically,
        # they're in different layers -> use vertical routing.
        s_bottom = sy + sh
        s_top = sy
        t_bottom = ty + th
        t_top = ty
        vertical_overlap = not (s_bottom <= t_top or t_bottom <= s_top)

        if not vertical_overlap:
            use_vertical = True
        elif not (sx + sw <= tx or tx + tw <= sx):
            use_vertical = True
        else:
            use_vertical = False

        # --- 4. Assign connection points ---
        if use_vertical:
            if dy > 0:
                exit_y, entry_y = 1.0, 0.0
            else:
                exit_y, entry_y = 0.0, 1.0

            n_out = len(outgoing.get(s, []))
            if is_bidir:
                if s < t:
                    exit_x = 0.35
                    entry_x = 0.35
                else:
                    exit_x = 0.65
                    entry_x = 0.65
            elif n_out > 1:
                out_list = outgoing[s]
                idx = out_list.index(i)
                if n_out == 2:
                    spread = [0.35, 0.65]
                else:
                    spread = [0.2 + 0.6 * j / max(n_out - 1, 1) for j in range(n_out)]
                exit_x = spread[idx]
                entry_x = 0.5
            else:
                exit_x = 0.5
                entry_x = 0.5

            style += (
                f"exitX={exit_x:.2f};exitY={exit_y};"
                f"entryX={entry_x:.2f};entryY={entry_y};"
            )
        else:
            if dx > 0:
                exit_x, entry_x = 1.0, 0.0
            else:
                exit_x, entry_x = 0.0, 1.0

            n_out = len(outgoing.get(s, []))
            if is_bidir:
                if s < t:
                    exit_y = 0.35
                    entry_y = 0.35
                else:
                    exit_y = 0.65
                    entry_y = 0.65
            elif n_out > 1:
                out_list = outgoing[s]
                idx = out_list.index(i)
                if n_out == 2:
                    spread = [0.35, 0.65]
                else:
                    spread = [0.2 + 0.6 * j / max(n_out - 1, 1) for j in range(n_out)]
                exit_y = spread[idx]
                entry_y = 0.5
            else:
                exit_y = 0.5
                entry_y = 0.5

            style += (
                f"exitX={exit_x};exitY={exit_y:.2f};"
                f"entryX={entry_x};entryY={entry_y:.2f};"
            )

        style += "jettySize=auto;orthogonalLoop=1;"
        elem.set("style", style)


# ── Per-page dispatch ───────────────────────────────────────────────────────

def process_page(name, diagram):
    top_vertices, edges, child_vertices, invalid_edges = extract_page(diagram)
    page_width = get_page_width(diagram)

    # R1: Remove invalid edge elements from XML tree
    invalid_set = set(id(e) for e in invalid_edges)
    root_elem = diagram.find(".//mxGraphModel/root")
    if root_elem is not None:
        for cell in list(root_elem):
            if id(cell) in invalid_set:
                root_elem.remove(cell)
    removed_count = len(invalid_edges)

    # R1: Filter edges referencing non-existent vertices
    all_vertex_ids = set(top_vertices.keys()) | set(child_vertices.keys())
    original_edge_count = len(edges)
    edges = filter_valid_edges(edges, all_vertex_ids)
    removed_count += original_edge_count - len(edges)
    edge_filter_msg = f", {removed_count} invalid edges removed" if removed_count > 0 else ""

    # Classify page
    has_containers = any(is_container_box(v["element"]) for v in top_vertices.values())
    has_swimlanes = any(is_swimlane(v["element"]) for v in top_vertices.values())

    if has_containers:
        # Container page: custom layered layout
        positions, sizes = layout_container_page(top_vertices, edges, page_width, diagram)
        apply_positions(top_vertices, positions, sizes)
        clear_edge_waypoints(edges)
        # Build vertices_info with updated sizes
        vinfo = {}
        for vid, v in top_vertices.items():
            if vid in sizes:
                vinfo[vid] = {"w": sizes[vid][0], "h": sizes[vid][1]}
            else:
                vinfo[vid] = {"w": v["w"], "h": v["h"]}
        optimize_edges(edges, vinfo, positions)
        return f"container layout ({len(positions)} nodes, {len(edges)} edges{edge_filter_msg})"

    elif has_swimlanes:
        # Class diagram: graphviz for top-level swimlanes only
        swimlane_vertices = {
            vid: v for vid, v in top_vertices.items()
            if is_swimlane(v["element"])
        }
        other_vertices = {
            vid: v for vid, v in top_vertices.items()
            if not is_swimlane(v["element"])
        }
        all_for_layout = {**swimlane_vertices, **other_vertices}

        if not all_for_layout:
            return "skip (no top-level vertices)"

        positions = graphviz_layout(all_for_layout, edges, rankdir="TB")
        if positions is None:
            return "skip (graphviz failed)"

        apply_positions(top_vertices, positions, {})
        clear_edge_waypoints(edges)
        vinfo = {vid: {"w": v["w"], "h": v["h"]} for vid, v in top_vertices.items()}
        optimize_edges(edges, vinfo, positions)
        return f"graphviz layout ({len(positions)} nodes, {len(edges)} edges{edge_filter_msg})"

    else:
        # Plain flowchart: graphviz layout
        if not top_vertices:
            return "skip (no vertices)"

        # R3: Normalize sizes for plain flowcharts too
        flowchart_sizes = normalize_sizes(top_vertices)

        positions = graphviz_layout(top_vertices, edges, rankdir="TB")
        if positions is None:
            return "skip (graphviz failed)"

        apply_positions(top_vertices, positions, flowchart_sizes)
        clear_edge_waypoints(edges)
        vinfo = {vid: {"w": v["w"], "h": v["h"]} for vid, v in top_vertices.items()}
        optimize_edges(edges, vinfo, positions)
        return f"graphviz layout ({len(positions)} nodes, {len(edges)} edges{edge_filter_msg})"


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Usage: python layout_drawio.py input.drawio output.drawio")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    print(f"Reading: {input_path}")
    tree, diagrams = parse_drawio(input_path)
    print(f"Found {len(diagrams)} pages\n")

    for name, diag in diagrams:
        result = process_page(name, diag)
        print(f"  {name}: {result}")

    ET.indent(tree, space="    ")
    tree.write(output_path, encoding="unicode", xml_declaration=False)
    print(f"\nDone! Output: {output_path}")


if __name__ == "__main__":
    main()
