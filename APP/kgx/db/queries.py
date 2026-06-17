"""
KnowledgeGraphDB — the single interface for all SQLite access in the explorer.

Design rules:
- No other module touches sqlite3 directly.
- All methods return plain dicts, never sqlite3.Row objects.
- metadata is always deserialized from JSON before returning.
- execute_read() raises if SQL is not SELECT.
- execute_write() raises if SQL is SELECT (use execute_read instead).
- Domain-agnostic: no hardcoded entity or relationship types.
  Explore mode transformations (stub filtering, hierarchy flattening,
  collaboration synthesis) are driven by explore_config dict.
"""

import json
import re
import sqlite3
import threading
from pathlib import Path

from .schema import init_schema


def _rows(cursor) -> list[dict]:
    """Convert sqlite3 cursor results to list of plain dicts."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _deserialize(entity: dict) -> dict:
    """Deserialize JSON metadata field in-place."""
    if "metadata" in entity and isinstance(entity["metadata"], str):
        try:
            entity["metadata"] = json.loads(entity["metadata"])
        except (json.JSONDecodeError, TypeError):
            entity["metadata"] = {}
    return entity


def _normalize_id(raw: str) -> str:
    """Normalize a raw string to a canonical slug."""
    raw = raw.strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^a-z0-9:._/-]", "", raw)
    return raw


_TIMELINE_FIELD_PRIORITY = {
    "award_year": 0,
    "year": 1,
    "publication_year": 2,
    "event_year": 3,
    "date": 4,
    "start_date": 5,
    "end_date": 6,
    "sequence": 7,
    "order": 8,
    "rank": 9,
    "index": 10,
    "position": 11,
    "created_at": 90,
    "updated_at": 91,
}

_TIMELINE_TYPE_PRIORITY = {
    "award": 0,
    "event": 1,
    "publication": 2,
    "paper": 3,
    "grant": 4,
    "patent": 5,
    "person": 20,
    "organization": 30,
    "institution": 31,
    "department": 32,
    "tag": 80,
    "topic": 81,
    "keyword": 82,
    "category": 83,
}


def _timeline_value_kind(value) -> str | None:
    """Classify a value as timeline-orderable if it looks numeric or date-like."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return "numeric"
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text):
        return "year"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[tT ][0-9:.+-Zz]*)?", text):
        return "date"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return "numeric"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
        return "datetime"
    return None


def _timeline_type_priority(type_name: str) -> int:
    normalized = str(type_name or "").strip().lower()
    if normalized in _TIMELINE_TYPE_PRIORITY:
        return _TIMELINE_TYPE_PRIORITY[normalized]
    if "tag" in normalized or "topic" in normalized or "keyword" in normalized:
        return 85
    if "award" in normalized:
        return 0
    if "event" in normalized:
        return 1
    if "publication" in normalized or "paper" in normalized:
        return 2
    if "person" in normalized:
        return 20
    return 50


class KnowledgeGraphDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.schema_version = init_schema(self.conn)

    def _exec(self, sql, params=None):
        """Thread-safe execute — all DB access goes through this."""
        with self._lock:
            return self.conn.execute(sql, params or [])

    def _exec_commit(self, sql, params=None):
        """Thread-safe execute + commit."""
        with self._lock:
            cur = self.conn.execute(sql, params or [])
            self.conn.commit()
            return cur

    def _exec_many(self, statements):
        """Thread-safe batch: list of (sql, params) tuples, single commit."""
        with self._lock:
            results = []
            for sql, params in statements:
                results.append(self.conn.execute(sql, params or []))
            self.conn.commit()
            return results

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # Schema discovery
    # ------------------------------------------------------------------

    def entity_types(self) -> list[dict]:
        """Return all entity types with counts. Schema-driven, never hardcoded."""
        cur = self.conn.execute(
            "SELECT type, COUNT(*) as count FROM entities GROUP BY type ORDER BY type"
        )
        return _rows(cur)

    def relationship_types(self) -> list[dict]:
        """Return all relationship types with counts."""
        cur = self.conn.execute(
            "SELECT rel_type, COUNT(*) as count FROM relationships GROUP BY rel_type ORDER BY rel_type"
        )
        return _rows(cur)

    def metadata_keys(self, entity_type: str = "") -> list[str]:
        """
        Return all metadata keys observed across entities (optionally filtered by type).
        Useful for building query builders and filter UIs.
        """
        if entity_type:
            rows = self.conn.execute(
                "SELECT metadata FROM entities WHERE type = ?", (entity_type,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT metadata FROM entities").fetchall()

        keys: set[str] = set()
        for row in rows:
            try:
                meta = json.loads(row[0])
                keys.update(meta.keys())
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(keys)

    def timeline_candidates(self, min_type_count: int = 3) -> list[dict]:
        """
        Detect entity types and fields that look usable as timeline anchors.

        A candidate type must meet the minimum count and expose at least one
        metadata or timestamp field with 2+ distinct orderable values.
        """
        candidates = []
        for entity_type_info in self.entity_types():
            entity_type = entity_type_info["type"]
            entity_count = int(entity_type_info["count"])
            if entity_count < min_type_count:
                continue

            rows = self.conn.execute(
                "SELECT metadata, created_at, updated_at FROM entities WHERE type = ?",
                (entity_type,),
            ).fetchall()

            field_stats: dict[tuple[str, str], dict] = {}

            for row in rows:
                try:
                    metadata = json.loads(row["metadata"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

                if isinstance(metadata, dict):
                    for field_name, value in metadata.items():
                        kind = _timeline_value_kind(value)
                        if not kind:
                            continue
                        key = ("metadata", field_name)
                        stat = field_stats.setdefault(key, {
                            "field": field_name,
                            "source": "metadata",
                            "kind": kind,
                            "non_null_count": 0,
                            "distinct_values": set(),
                        })
                        stat["non_null_count"] += 1
                        stat["distinct_values"].add(str(value))

                for column_name in ("created_at", "updated_at"):
                    value = row[column_name]
                    kind = _timeline_value_kind(value)
                    if not kind:
                        continue
                    key = ("column", column_name)
                    stat = field_stats.setdefault(key, {
                        "field": column_name,
                        "source": "column",
                        "kind": kind,
                        "non_null_count": 0,
                        "distinct_values": set(),
                    })
                    stat["non_null_count"] += 1
                    stat["distinct_values"].add(str(value))

            order_fields = []
            for stat in field_stats.values():
                distinct_count = len(stat["distinct_values"])
                if stat["non_null_count"] < min_type_count or distinct_count < 2:
                    continue
                order_fields.append({
                    "field": stat["field"],
                    "source": stat["source"],
                    "kind": stat["kind"],
                    "non_null_count": stat["non_null_count"],
                    "distinct_count": distinct_count,
                    "priority": _TIMELINE_FIELD_PRIORITY.get(stat["field"], 50),
                })

            order_fields.sort(
                key=lambda item: (
                    item["priority"],
                    0 if item["source"] == "metadata" else 1,
                    -item["non_null_count"],
                    item["field"],
                )
            )

            if not order_fields:
                continue

            candidates.append({
                "type": entity_type,
                "count": entity_count,
                "order_fields": order_fields,
            })

        candidates.sort(
            key=lambda item: (
                _timeline_type_priority(item["type"]),
                item["order_fields"][0]["priority"],
                -item["count"],
                item["type"],
            )
        )
        return candidates

    # ------------------------------------------------------------------
    # Bulk graph data (for visualization — minimal fields only)
    # ------------------------------------------------------------------

    def graph_nodes(self, stub_type: str = "", stub_flag: str = "profiled") -> list[dict]:
        """Return graph-rendering nodes with only id/type/name/group fields."""
        if stub_type and stub_flag:
            cur = self.conn.execute(
                """
                SELECT id, type, name,
                    CASE
                        WHEN type = ?
                             AND COALESCE(json_extract(metadata, '$.' || ?), 0) != 1
                        THEN type || ' (stub)'
                        ELSE type
                    END AS "group"
                FROM entities ORDER BY type, name
                """,
                (stub_type, stub_flag),
            )
        else:
            cur = self.conn.execute(
                'SELECT id, type, name, type AS "group" FROM entities ORDER BY type, name'
            )
        return _rows(cur)

    def graph_edges(self) -> list[dict]:
        """Return all edges with source/target/rel_type — for graph rendering."""
        cur = self.conn.execute(
            "SELECT source_id as source, target_id as target, rel_type FROM relationships"
        )
        return _rows(cur)

    def graph_display(self, *, collapse_rel_types: list[str] | None = None,
                      top_k: int = 20, min_weight: int = 2,
                      collapse_stubs: bool = True,
                      stub_type: str = "", stub_flag: str = "profiled",
                      authored_edge: str = "AUTHORED",
                      collaboration_edge: str = "COAUTHOR",
                      mediator_type: str = "",
                      included_tag_roots: list[str] | None = None,
                      hierarchy_edge: str = "BROADER") -> dict:
        """Return a reduced graph projection for visualization.

        - collapse_rel_types: relationship types to hide by default
        - collapse_stubs: hide stub entities unless expanded
        """
        nodes = self.graph_nodes(stub_type=stub_type, stub_flag=stub_flag)
        edges = self.graph_edges()
        collapse_rel_types = {r.upper() for r in (collapse_rel_types or []) if r}
        node_by_id = {n["id"]: n for n in nodes}

        stub_ids = set()
        if collapse_stubs and stub_type:
            stub_suffix = f"{stub_type} (stub)"
            stub_ids = {
                n["id"] for n in nodes
                if n.get("type") == stub_type and n.get("group") == stub_suffix
            }
        profiled_ids = {
            n["id"] for n in nodes
            if n.get("type") == stub_type and n["id"] not in stub_ids
        }

        anchored_mediator_ids: set[str] = set()
        if mediator_type and authored_edge:
            for e in edges:
                if e["rel_type"] != authored_edge:
                    continue
                src, tgt = e["source"], e["target"]
                src_type = node_by_id.get(src, {}).get("type")
                tgt_type = node_by_id.get(tgt, {}).get("type")
                if src_type == stub_type and src in profiled_ids and tgt_type == mediator_type:
                    anchored_mediator_ids.add(tgt)
                elif tgt_type == stub_type and tgt in profiled_ids and src_type == mediator_type:
                    anchored_mediator_ids.add(src)

        leaf_stub_ids: set[str] = set()
        for e in edges:
            src, tgt, rel = e["source"], e["target"], e["rel_type"]
            if rel == collaboration_edge:
                if src in profiled_ids and tgt in stub_ids:
                    leaf_stub_ids.add(tgt)
                elif tgt in profiled_ids and src in stub_ids:
                    leaf_stub_ids.add(src)
            elif rel == authored_edge and mediator_type:
                src_type = node_by_id.get(src, {}).get("type")
                tgt_type = node_by_id.get(tgt, {}).get("type")
                if src in stub_ids and tgt_type == mediator_type and tgt in anchored_mediator_ids:
                    leaf_stub_ids.add(src)
                elif tgt in stub_ids and src_type == mediator_type and src in anchored_mediator_ids:
                    leaf_stub_ids.add(tgt)

        projected_nodes = []
        for n in nodes:
            projected = dict(n)
            hidden = False
            if collapse_stubs and n["id"] in stub_ids and n["id"] not in leaf_stub_ids:
                hidden = True
            if mediator_type and n.get("type") == mediator_type and anchored_mediator_ids and n["id"] not in anchored_mediator_ids:
                hidden = True
            projected["hidden"] = hidden
            projected_nodes.append(projected)

        hidden_node_ids = {n["id"] for n in projected_nodes if n["hidden"]}
        projected_edges = []
        for e in edges:
            projected = dict(e)
            src, tgt, rel = e["source"], e["target"], e["rel_type"]
            hidden = rel.upper() in collapse_rel_types
            if not hidden:
                if rel == collaboration_edge:
                    src_profiled = src in profiled_ids
                    tgt_profiled = tgt in profiled_ids
                    src_leaf_stub = src in leaf_stub_ids
                    tgt_leaf_stub = tgt in leaf_stub_ids
                    hidden = not (
                        (src_profiled and tgt_profiled)
                        or (src_profiled and tgt_leaf_stub)
                        or (tgt_profiled and src_leaf_stub)
                    )
                elif rel == authored_edge and mediator_type:
                    src_type = node_by_id.get(src, {}).get("type")
                    tgt_type = node_by_id.get(tgt, {}).get("type")
                    if src_type == mediator_type:
                        mediator_id, person_id = src, tgt
                    elif tgt_type == mediator_type:
                        mediator_id, person_id = tgt, src
                    else:
                        mediator_id, person_id = "", ""
                    hidden = not (
                        mediator_id in anchored_mediator_ids
                        and (person_id in profiled_ids or person_id in leaf_stub_ids)
                    )
                elif src in hidden_node_ids or tgt in hidden_node_ids:
                    hidden = True
            projected["hidden"] = hidden
            projected_edges.append(projected)

        visible_tag_groups = []
        if included_tag_roots:
            root_name_by_id = {
                n["id"]: n.get("name", n["id"])
                for n in nodes
                if n.get("type") == "tag"
            }
            visible_node_ids = {n["id"] for n in projected_nodes if not n["hidden"]}
            for root_id in [str(tag_id).strip() for tag_id in (included_tag_roots or []) if str(tag_id).strip()]:
                normalized_root = _normalize_id(root_id)
                descendant_ids = self._descendant_ids(normalized_root, hierarchy_edge=hierarchy_edge)
                group_node_ids = sorted(
                    tag_id for tag_id in ({normalized_root} | descendant_ids)
                    if tag_id in visible_node_ids
                )
                if not group_node_ids:
                    continue
                visible_tag_groups.append({
                    "id": normalized_root,
                    "label": root_name_by_id.get(normalized_root, normalized_root),
                    "node_ids": group_node_ids,
                })

        return {
            "nodes": projected_nodes,
            "edges": projected_edges,
            "projection": {
                "mode": "display",
                "collapse_rel_types": sorted(collapse_rel_types),
                "top_k": top_k,
                "min_weight": min_weight,
                "collapse_stubs": collapse_stubs,
                "visible_tag_groups": visible_tag_groups,
            },
        }

    def graph_explore(self, explore_config: dict | None = None) -> dict:
        """Return an exploration-optimized graph projection.

        All transformations are driven by explore_config. When a config field
        is empty or unset, the corresponding transformation is skipped.
        """
        cfg = explore_config or {}
        stub_type = cfg.get("stub_type", "")
        stub_flag = cfg.get("stub_flag", "profiled")
        include_node_types = set(cfg.get("include_node_types", []))
        include_rel_types = set(cfg.get("include_rel_types", []))
        include_rel_patterns = list(cfg.get("include_rel_patterns", []) or [])
        excluded_node_types = set(cfg.get("excluded_node_types", []))
        preserve_node_types = set(cfg.get("preserve_node_types", []))
        included_tag_roots = [str(tag_id).strip() for tag_id in cfg.get("included_tag_roots", []) if str(tag_id).strip()]
        mediator_type = cfg.get("mediator_type", "")
        mediator_edge = cfg.get("mediator_edge", "")
        derived_edge_type = cfg.get("derived_edge_type", "RELATED")
        derived_path_edges = list(cfg.get("derived_path_edges", []) or [])
        hierarchy_edge = cfg.get("hierarchy_edge", "")
        annotation_edge = cfg.get("annotation_edge", "")
        skipped_rel_types = set(cfg.get("skipped_rel_types", []))

        tag_categories: dict[str, str] = {}
        for row in self._exec(
            "SELECT id, COALESCE(json_extract(metadata, '$.category'), '') FROM entities WHERE type = 'tag'"
        ).fetchall():
            tag_categories[row[0]] = (row[1] or "").lower()

        leaf_to_field: dict[str, str] = {}
        field_tag_ids: set[str] = set()
        hierarchy_parent_tag_ids: set[str] = set()
        hierarchy_child_tag_ids: set[str] = set()
        leaf_tag_ids: set[str] = set()
        if hierarchy_edge:
            hierarchy_rows = self._exec(
                "SELECT source_id, target_id FROM relationships WHERE rel_type = ?",
                (hierarchy_edge,),
            ).fetchall()
            for row in hierarchy_rows:
                hierarchy_child_tag_ids.add(row[0])
                hierarchy_parent_tag_ids.add(row[1])
                # Only roll tags upward when the parent is field-like.
                # This preserves umbrella/domain containers like awards -> nobel-prize
                # instead of replacing all visible topic tags with their root parent.
                if tag_categories.get(row[1]) == "field":
                    leaf_to_field[row[0]] = row[1]
                field_tag_ids.add(row[1])
            leaf_tag_ids = hierarchy_child_tag_ids - hierarchy_parent_tag_ids

        allowed_tag_ids: set[str] | None = None
        if included_tag_roots:
            allowed_tag_ids = set()
            for root_id in included_tag_roots:
                normalized_root = _normalize_id(root_id)
                allowed_tag_ids.add(normalized_root)
                allowed_tag_ids.update(self._descendant_ids(normalized_root, hierarchy_edge=hierarchy_edge))

        stub_ids: set[str] = set()
        if stub_type and stub_flag:
            stub_ids = {
                r[0] for r in self._exec(
                    "SELECT id FROM entities WHERE type = ?"
                    " AND COALESCE(json_extract(metadata, '$.' || ?), 0) != 1",
                    (stub_type, stub_flag),
                ).fetchall()
            }

        excluded_type_ids: set[str] = set()
        if excluded_node_types:
            placeholders = ",".join("?" * len(excluded_node_types))
            excluded_type_ids = {
                r[0] for r in self._exec(
                    f"SELECT id FROM entities WHERE type IN ({placeholders})",
                    list(excluded_node_types),
                ).fetchall()
            }

        mediator_type_ids: set[str] = set()
        if mediator_type:
            mediator_type_ids = {
                r[0] for r in self._exec(
                    "SELECT id FROM entities WHERE type = ?",
                    (mediator_type,),
                ).fetchall()
            }

        exclude_ids = stub_ids | excluded_type_ids
        all_nodes = self.graph_nodes(stub_type=stub_type, stub_flag=stub_flag)
        node_by_id = {n["id"]: n for n in all_nodes}
        nodes = [n for n in all_nodes if n["id"] not in exclude_ids]
        if include_node_types:
            nodes = [n for n in nodes if n.get("type") in include_node_types]
        if allowed_tag_ids is not None:
            nodes = [
                n for n in nodes
                if n.get("type") != "tag" or n["id"] in allowed_tag_ids
            ]

        all_edges = self.graph_edges()

        def edge_matches_include_pattern(edge: dict) -> bool:
            if not include_rel_patterns:
                return False
            src_type = str(node_by_id.get(edge["source"], {}).get("type", ""))
            tgt_type = str(node_by_id.get(edge["target"], {}).get("type", ""))
            rel_type = str(edge.get("rel_type", ""))
            for pattern in include_rel_patterns:
                pattern_rel = str(pattern.get("rel_type", "") or "")
                source_type = str(pattern.get("source_type", "") or "")
                target_type = str(pattern.get("target_type", "") or "")
                if pattern_rel and rel_type != pattern_rel:
                    continue
                if source_type and src_type != source_type:
                    continue
                if target_type and tgt_type != target_type:
                    continue
                return True
            return False

        collab_weights: dict[tuple[str, str], int] = {}
        mediator_actors: dict[str, set[str]] = {}
        for e in all_edges:
            if mediator_edge and e["rel_type"] == mediator_edge:
                if e["source"] in mediator_type_ids:
                    mediator, actor = e["source"], e["target"]
                elif e["target"] in mediator_type_ids:
                    mediator, actor = e["target"], e["source"]
                else:
                    continue
                mediator_actors.setdefault(mediator, set()).add(actor)
        for actors in mediator_actors.values():
            actors_list = sorted(a for a in actors if a not in exclude_ids)
            for i in range(len(actors_list)):
                for j in range(i + 1, len(actors_list)):
                    key = (actors_list[i], actors_list[j])
                    collab_weights[key] = collab_weights.get(key, 0) + 1

        mediator_annotations: dict[str, set[str]] = {}
        if annotation_edge:
            for e in all_edges:
                if e["rel_type"] != annotation_edge:
                    continue
                med = e["source"] if e["source"] in mediator_type_ids else (
                    e["target"] if e["target"] in mediator_type_ids else None
                )
                tag = e["target"] if e["source"] in mediator_type_ids else (
                    e["source"] if e["target"] in mediator_type_ids else None
                )
                if med and tag:
                    if allowed_tag_ids is not None and tag not in allowed_tag_ids:
                        continue
                    mediator_annotations.setdefault(med, set()).add(leaf_to_field.get(tag, tag))

        edges = []
        node_id_set = {n["id"] for n in nodes}
        for e in all_edges:
            if include_rel_types or include_rel_patterns:
                if e["rel_type"] not in include_rel_types and not edge_matches_include_pattern(e):
                    continue
            if e["rel_type"] in skipped_rel_types:
                continue
            src, tgt = e["source"], e["target"]
            if src in node_id_set and tgt in node_id_set:
                edges.append({"source": src, "target": tgt, "rel_type": e["rel_type"]})

        if mediator_edge and annotation_edge:
            for med, tags in mediator_annotations.items():
                actors = mediator_actors.get(med, set())
                for actor in actors:
                    if actor not in node_id_set:
                        continue
                    for tag in tags:
                        if tag in node_id_set:
                            edges.append({"source": actor, "target": tag, "rel_type": annotation_edge})

        for (a, b), weight in collab_weights.items():
            if a in node_id_set and b in node_id_set:
                edges.append({
                    "source": a,
                    "target": b,
                    "rel_type": derived_edge_type,
                    "weight": weight,
                })

        if derived_path_edges:
            all_edges_by_rel: dict[str, list[dict]] = {}
            for edge in all_edges:
                all_edges_by_rel.setdefault(str(edge["rel_type"]), []).append(edge)
            for spec in derived_path_edges:
                source_type = str(spec.get("source_type", "") or "")
                via_type = str(spec.get("via_type", "") or "")
                target_type = str(spec.get("target_type", "") or "")
                first_rel_type = str(spec.get("first_rel_type", "") or "")
                second_rel_type = str(spec.get("second_rel_type", "") or "")
                path_edge_type = str(spec.get("edge_type", "") or derived_edge_type or "RELATED")
                if not source_type or not target_type or not first_rel_type or not second_rel_type:
                    continue

                source_to_via: dict[str, set[str]] = {}
                via_to_target: dict[str, set[str]] = {}

                for edge in all_edges_by_rel.get(first_rel_type, []):
                    src_id, tgt_id = edge["source"], edge["target"]
                    src_type = node_by_id.get(src_id, {}).get("type", "")
                    tgt_type = node_by_id.get(tgt_id, {}).get("type", "")
                    if src_type == source_type and tgt_type == via_type:
                        source_to_via.setdefault(src_id, set()).add(tgt_id)
                    elif tgt_type == source_type and src_type == via_type:
                        source_to_via.setdefault(tgt_id, set()).add(src_id)

                for edge in all_edges_by_rel.get(second_rel_type, []):
                    src_id, tgt_id = edge["source"], edge["target"]
                    src_type = node_by_id.get(src_id, {}).get("type", "")
                    tgt_type = node_by_id.get(tgt_id, {}).get("type", "")
                    if src_type == via_type and tgt_type == target_type:
                        via_to_target.setdefault(src_id, set()).add(tgt_id)
                    elif tgt_type == via_type and src_type == target_type:
                        via_to_target.setdefault(tgt_id, set()).add(src_id)

                path_weights: dict[tuple[str, str], int] = {}
                for source_id, via_ids in source_to_via.items():
                    if source_id not in node_id_set:
                        continue
                    for via_id in via_ids:
                        for target_id in via_to_target.get(via_id, set()):
                            if target_id not in node_id_set or source_id == target_id:
                                continue
                            key = (source_id, target_id)
                            path_weights[key] = path_weights.get(key, 0) + 1

                for (source_id, target_id), weight in path_weights.items():
                    edge_payload = {
                        "source": source_id,
                        "target": target_id,
                        "rel_type": path_edge_type,
                        "weight": weight,
                    }
                    if via_type:
                        edge_payload["metadata"] = {
                            "derived": True,
                            "via_type": via_type,
                            "path": [first_rel_type, second_rel_type],
                        }
                    edges.append(edge_payload)

        seen_edges: set[tuple[str, str, str]] = set()
        deduped_edges = []
        for e in edges:
            key = (e["source"], e["rel_type"], e["target"])
            if key not in seen_edges:
                seen_edges.add(key)
                deduped_edges.append(e)
        edges = deduped_edges

        connected_ids: set[str] = set()
        for e in edges:
            connected_ids.add(e["source"])
            connected_ids.add(e["target"])
        if preserve_node_types:
            connected_ids.update(
                n["id"] for n in nodes
                if n.get("type") in preserve_node_types
            )
        initial_node_ids = node_id_set
        initial_tag_ids = {
            n["id"] for n in nodes
            if n.get("type") == "tag"
        }
        pruned = len(node_id_set) - len(node_id_set & connected_ids)
        nodes = [n for n in nodes if n["id"] in connected_ids]
        final_node_ids = {n["id"] for n in nodes}
        pruned_node_ids = initial_node_ids - final_node_ids
        pruned_tag_ids = initial_tag_ids & pruned_node_ids
        pruned_leaf_tag_ids = leaf_tag_ids & pruned_tag_ids
        visible_tag_groups = []
        if included_tag_roots:
            root_name_by_id = {
                n["id"]: n.get("name", n["id"])
                for n in all_nodes
                if n.get("type") == "tag"
            }
            for root_id in included_tag_roots:
                normalized_root = _normalize_id(root_id)
                descendant_ids = self._descendant_ids(normalized_root, hierarchy_edge=hierarchy_edge)
                group_node_ids = sorted(
                    tag_id for tag_id in ({normalized_root} | descendant_ids)
                    if tag_id in final_node_ids
                )
                if not group_node_ids:
                    continue
                visible_tag_groups.append({
                    "id": normalized_root,
                    "label": root_name_by_id.get(normalized_root, normalized_root),
                    "node_ids": group_node_ids,
                })

        return {
            "nodes": nodes,
            "edges": edges,
            "projection": {
                "mode": "explore",
                "mediator_type": mediator_type,
                "mediator_edge": mediator_edge,
                "annotation_edge": annotation_edge,
                "included_types": sorted(include_node_types),
                "included_rel_types": sorted(include_rel_types),
                "included_rel_patterns": include_rel_patterns,
                "excluded_types": sorted(excluded_node_types),
                "preserved_types": sorted(preserve_node_types),
                "included_tag_roots": included_tag_roots,
                "excluded_stubs": len(stub_ids),
                "excluded_leaf_tags": len(pruned_leaf_tag_ids),
                "derived_edges": len(collab_weights),
                "derived_path_edges": len(derived_path_edges),
                "pruned_orphans": pruned,
                "pruned_tags": len(pruned_tag_ids),
                "visible_tag_groups": visible_tag_groups,
            },
        }

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    def get_entity(self, entity_id: str) -> dict | None:
        """Get a single entity by ID including aliases."""
        entity_id = _normalize_id(entity_id)
        row = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return None
        result = _deserialize(dict(row))
        result["aliases"] = [
            r[0] for r in self.conn.execute(
                "SELECT alias FROM aliases WHERE entity_id = ? ORDER BY alias",
                (entity_id,),
            ).fetchall()
        ]
        return result

    def get_entities(
        self,
        entity_type: str = "",
        search: str = "",
        *,
        exclude_stubs: bool = False,
        stub_type: str = "",
        stub_flag: str = "profiled",
    ) -> list[dict]:
        """Return entities, optionally filtered by type and/or name search."""
        params: list = []
        where: list[str] = []

        if entity_type:
            where.append("type = ?")
            params.append(entity_type)
        if search:
            where.append("name LIKE ?")
            params.append(f"%{search}%")
        if exclude_stubs and entity_type and stub_type and entity_type == stub_type and stub_flag:
            where.append("COALESCE(json_extract(metadata, '$.' || ?), 0) = 1")
            params.append(stub_flag)

        sql = "SELECT id, type, name, updated_at FROM entities"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY name"

        return _rows(self._exec(sql, params))

    def upsert_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        name: str = "",
        metadata: dict | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Insert or update an entity. Returns the canonical entity_id."""
        entity_id = _normalize_id(entity_id)
        name = name or entity_id
        meta_json = json.dumps(metadata or {})

        with self._lock:
            self.conn.execute(
                """INSERT INTO entities (id, type, name, metadata) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name = ?, metadata = ?, updated_at = datetime('now')""",
                (entity_id, entity_type, name, meta_json, name, meta_json),
            )

            if aliases:
                for alias in aliases:
                    norm = _normalize_id(alias)
                    self.conn.execute(
                        "INSERT OR IGNORE INTO aliases (alias, entity_id) VALUES (?, ?)",
                        (norm, entity_id),
                    )

            self.conn.commit()
        return entity_id

    def delete_entity(self, entity_id: str) -> bool:
        """Delete entity and all its relationships and aliases. Returns True if found."""
        entity_id = _normalize_id(entity_id)
        with self._lock:
            cur = self.conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            self.conn.commit()
        return cur.rowcount > 0

    def resolve(self, raw_id: str) -> str | None:
        """Resolve a raw ID or alias to the canonical entity_id."""
        norm = _normalize_id(raw_id)
        row = self.conn.execute("SELECT id FROM entities WHERE id = ?", (norm,)).fetchone()
        if row:
            return row[0]
        row = self.conn.execute(
            "SELECT entity_id FROM aliases WHERE alias = ?", (norm,)
        ).fetchone()
        return row[0] if row else None

    def ensure_entity(
        self,
        entity_type: str,
        raw_id: str,
        *,
        name: str = "",
        metadata: dict | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Resolve or create. Returns canonical ID."""
        canonical = self.resolve(raw_id)
        if canonical:
            return canonical
        return self.upsert_entity(
            entity_type, raw_id, name=name, metadata=metadata, aliases=aliases
        )

    # ------------------------------------------------------------------
    # Relationship CRUD
    # ------------------------------------------------------------------

    def get_relationships(
        self,
        entity_id: str,
        rel_type: str = "",
        direction: str = "both",
    ) -> list[dict]:
        """Get relationships for an entity. direction: 'outgoing', 'incoming', or 'both'."""
        results = []

        def _query(col_match: str, col_other: str) -> list[dict]:
            sql = f"SELECT source_id, rel_type, target_id, metadata FROM relationships WHERE {col_match} = ?"
            params: list = [entity_id]
            if rel_type:
                sql += " AND rel_type = ?"
                params.append(rel_type)
            rows = _rows(self.conn.execute(sql, params))
            for r in rows:
                try:
                    r["metadata"] = json.loads(r["metadata"])
                except (json.JSONDecodeError, TypeError):
                    r["metadata"] = {}
            return rows

        if direction in ("outgoing", "both"):
            results.extend(_query("source_id", "target_id"))
        if direction in ("incoming", "both"):
            results.extend(_query("target_id", "source_id"))
        return results

    def add_relationship(
        self,
        source_id: str,
        rel_type: str,
        target_id: str,
        metadata: dict | None = None,
    ):
        """Add a relationship between two entities (idempotent)."""
        source_id = _normalize_id(source_id)
        target_id = _normalize_id(target_id)
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO relationships (source_id, rel_type, target_id, metadata) VALUES (?, ?, ?, ?)",
                (source_id, rel_type, target_id, json.dumps(metadata or {})),
            )
            self.conn.commit()

    def delete_relationship(self, source_id: str, rel_type: str, target_id: str) -> bool:
        """Delete a specific relationship. Returns True if it existed."""
        source_id = _normalize_id(source_id)
        target_id = _normalize_id(target_id)
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM relationships WHERE source_id = ? AND rel_type = ? AND target_id = ?",
                (source_id, rel_type, target_id),
            )
            self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    def _descendant_ids(self, entity_id: str, hierarchy_edge: str = "BROADER") -> set[str]:
        """Walk hierarchy relationships to find all descendant entity IDs.

        Returns the set of IDs that have a (transitive) hierarchy path to
        entity_id. Uses iterative BFS — no recursion, no hardcoded depth.
        Returns an empty set if the entity has no children or hierarchy is disabled.
        """
        if not hierarchy_edge:
            return set()
        descendants: set[str] = set()
        frontier = {entity_id}
        while frontier:
            placeholders = ",".join("?" * len(frontier))
            children = {
                r[0] for r in self._exec(
                    f"SELECT source_id FROM relationships "
                    f"WHERE rel_type = ? AND target_id IN ({placeholders})",
                    [hierarchy_edge] + list(frontier),
                ).fetchall()
            }
            new = children - descendants
            descendants |= new
            frontier = new
        return descendants

    def neighbors(self, entity_id: str, rel_type: str = "") -> list[dict]:
        """Return all directly connected entities."""
        params: list
        if rel_type:
            sql = """
                SELECT DISTINCT e.id, e.type, e.name FROM entities e
                WHERE e.id IN (
                    SELECT target_id FROM relationships WHERE source_id = ? AND rel_type = ?
                    UNION
                    SELECT source_id FROM relationships WHERE target_id = ? AND rel_type = ?
                )
            """
            params = [entity_id, rel_type, entity_id, rel_type]
        else:
            sql = """
                SELECT DISTINCT e.id, e.type, e.name FROM entities e
                WHERE e.id IN (
                    SELECT target_id FROM relationships WHERE source_id = ?
                    UNION
                    SELECT source_id FROM relationships WHERE target_id = ?
                )
            """
            params = [entity_id, entity_id]
        return _rows(self._exec(sql, params))

    def neighbors_explore(self, entity_id: str,
                          hierarchy_edge: str = "BROADER",
                          annotation_edge: str = "TAGGED") -> list[dict]:
        """Like neighbors() but hierarchy-aware."""
        direct = self.neighbors(entity_id)
        if not hierarchy_edge or not annotation_edge:
            return direct
        descendants = self._descendant_ids(entity_id, hierarchy_edge)
        if not descendants:
            return direct

        placeholders = ",".join("?" * len(descendants))
        transitive = _rows(self._exec(
            f"""SELECT DISTINCT e.id, e.type, e.name FROM entities e
                WHERE e.id IN (
                    SELECT source_id FROM relationships
                    WHERE rel_type = ? AND target_id IN ({placeholders})
                )""",
            [annotation_edge] + list(descendants),
        ))

        seen = {n["id"] for n in direct}
        for n in transitive:
            if n["id"] not in seen:
                seen.add(n["id"])
                direct.append(n)
        return direct

    def shared_connections(self, id1: str, id2: str) -> list[dict]:
        """Find entities connected to both id1 and id2."""
        return _rows(self._exec("""
            SELECT e.id, e.type, e.name FROM entities e
            WHERE e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION SELECT source_id FROM relationships WHERE target_id = ?
            )
            AND e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION SELECT source_id FROM relationships WHERE target_id = ?
            )
        """, (id1, id1, id2, id2)))

    def hub_nodes(
        self,
        min_degree: int = 5,
        entity_type: str = "",
        exclude_stubs: bool = False,
        stub_type: str = "",
        stub_flag: str = "profiled",
    ) -> list[dict]:
        """Find entities with the most connections."""
        where = "WHERE e.type = ?" if entity_type else ""
        params: list = [entity_type] if entity_type else []

        stub_filter = ""
        if exclude_stubs and stub_type and stub_flag:
            stub_filter = """
                AND o.id NOT IN (
                    SELECT id FROM entities
                    WHERE type = ?
                    AND (json_extract(metadata, '$.' || ?) IS NULL
                         OR json_extract(metadata, '$.' || ?) = 0)
                )
            """
            params.extend([stub_type, stub_flag, stub_flag])

        sql = f"""
            SELECT e.id, e.type, e.name, COUNT(*) AS degree
            FROM entities e
            JOIN (
                SELECT source_id AS eid, target_id AS other FROM relationships
                UNION ALL
                SELECT target_id AS eid, source_id AS other FROM relationships
            ) r ON r.eid = e.id
            JOIN entities o ON o.id = r.other
            {where}
            {stub_filter}
            GROUP BY e.id
            HAVING degree >= ?
            ORDER BY degree DESC
        """
        params.append(min_degree)
        return _rows(self._exec(sql, params))

    def degree(self, entity_id: str) -> int:
        """Count total relationships (in + out) for an entity."""
        row = self.conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT source_id FROM relationships WHERE source_id = ?
                UNION ALL
                SELECT target_id FROM relationships WHERE target_id = ?
            )
        """, (entity_id, entity_id)).fetchone()
        return row[0]

    def degree_explore(self, entity_id: str,
                       hierarchy_edge: str = "BROADER",
                       annotation_edge: str = "TAGGED") -> int:
        """Like degree() but counts transitive annotation via hierarchy descendants."""
        base = self.degree(entity_id)
        if not hierarchy_edge or not annotation_edge:
            return base
        descendants = self._descendant_ids(entity_id, hierarchy_edge)
        if not descendants:
            return base
        placeholders = ",".join("?" * len(descendants))
        transitive = self._exec(
            f"""SELECT COUNT(DISTINCT source_id) FROM relationships
                WHERE rel_type = ? AND target_id IN ({placeholders})""",
            [annotation_edge] + list(descendants),
        ).fetchone()[0]
        return base + transitive

    def stats(self) -> dict:
        """Summary counts for entities, relationships, aliases."""
        entity_counts = {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT type, COUNT(*) FROM entities GROUP BY type"
            ).fetchall()
        }
        rel_counts = {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT rel_type, COUNT(*) FROM relationships GROUP BY rel_type"
            ).fetchall()
        }
        alias_count = self.conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        return {
            "entities": entity_counts,
            "relationships": rel_counts,
            "aliases": alias_count,
            "total_entities": sum(entity_counts.values()),
            "total_relationships": sum(rel_counts.values()),
        }

    # ------------------------------------------------------------------
    # Rich content (topics, snippets, research interests, contact, sources)
    # ------------------------------------------------------------------

    def get_topics(self, entity_id: str) -> list[str]:
        """Return topic strings for an entity."""
        rows = self.conn.execute(
            "SELECT topic FROM entity_topics WHERE entity_id = ? ORDER BY topic",
            (entity_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def get_snippets(self, entity_id: str) -> list[dict]:
        """Return snippets for an entity, grouped by ref_type/ref_id."""
        rows = self.conn.execute(
            """SELECT id, ref_id, ref_type, text, ordinal
               FROM snippets WHERE entity_id = ?
               ORDER BY ref_type, ref_id, ordinal""",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_snippets_about(self, ref_id: str) -> list[dict]:
        """Return all snippets that reference a given entity,
        along with the source entity name they came from."""
        rows = self.conn.execute(
            """SELECT s.id, s.entity_id, e.name AS signal_name,
                      s.ref_type, s.text, s.ordinal
               FROM snippets s
               JOIN entities e ON e.id = s.entity_id
               WHERE s.ref_id = ?
               ORDER BY e.name, s.ordinal""",
            (ref_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_research_interests(self, entity_id: str) -> list[str]:
        """Return ordered research interests for an entity."""
        rows = self.conn.execute(
            "SELECT interest FROM research_interests WHERE entity_id = ? ORDER BY ordinal",
            (entity_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def get_contact(self, entity_id: str) -> dict:
        """Return contact fields for an entity as {field: value}."""
        rows = self.conn.execute(
            "SELECT field, value FROM contact_info WHERE entity_id = ? ORDER BY field",
            (entity_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def get_sources(self, entity_id: str) -> list[dict]:
        """Return provenance sources for an entity."""
        rows = self.conn.execute(
            "SELECT source_name, url, retrieved_at FROM sources WHERE entity_id = ? ORDER BY source_name",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_rich(self, entity_id: str, entity_type: str = "") -> dict:
        """Return all rich-content tables for one entity in a single call."""
        return {
            "topics": self.get_topics(entity_id),
            "snippets": self.get_snippets(entity_id),
            "snippets_about": self.get_snippets_about(entity_id),
            "research_interests": self.get_research_interests(entity_id),
            "contact": self.get_contact(entity_id),
            "sources": self.get_sources(entity_id),
        }

    # ------------------------------------------------------------------
    # Raw SQL (for chat-to-SQL)
    # ------------------------------------------------------------------

    def execute_read(self, sql: str, params: list | None = None) -> list[dict]:
        """Execute a SELECT query (including WITH CTEs). Raises ValueError on DML."""
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise ValueError(f"execute_read only accepts SELECT/WITH queries. Got: {sql[:80]}")
        cur = self.conn.execute(sql, params or [])
        return _rows(cur)

    def execute_write(self, sql: str, params: list | None = None) -> int:
        """Execute an INSERT/UPDATE/DELETE. Raises ValueError if it's a SELECT."""
        if sql.strip().upper().startswith("SELECT"):
            raise ValueError("execute_write does not accept SELECT queries. Use execute_read.")
        with self._lock:
            cur = self.conn.execute(sql, params or [])
            self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_graph_json(self) -> dict:
        """Export full graph as JSON (nodes + edges + metadata)."""
        nodes = []
        for row in self.conn.execute("SELECT * FROM entities ORDER BY type, name").fetchall():
            e = _deserialize(dict(row))
            e["aliases"] = [
                r[0] for r in self.conn.execute(
                    "SELECT alias FROM aliases WHERE entity_id = ?", (e["id"],)
                ).fetchall()
            ]
            nodes.append(e)

        edges = _rows(self.conn.execute(
            "SELECT source_id, rel_type, target_id, metadata FROM relationships"
        ))
        for e in edges:
            try:
                e["metadata"] = json.loads(e["metadata"])
            except (json.JSONDecodeError, TypeError):
                e["metadata"] = {}

        return {
            "schema_version": self.schema_version,
            "stats": self.stats(),
            "nodes": nodes,
            "edges": edges,
        }

    def export_markdown(self, entity_id: str) -> str:
        """Render a single entity as markdown. Generic — works for any entity type."""
        entity = self.get_entity(entity_id)
        if not entity:
            return f"# Not found: {entity_id}\n"

        rels = self.get_relationships(entity_id)
        meta = entity.get("metadata", {})

        lines = [
            "---",
            f'id: "{entity["id"]}"',
            f'type: "{entity["type"]}"',
            f'name: "{entity["name"]}"',
        ]
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                lines.append(f'{k}: "{v}"')
        lines.extend(["---", "", f'# {entity["name"]}', ""])

        if meta:
            lines.append("## Properties")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("|---|---|")
            for k, v in meta.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

        if rels:
            lines.append("## Relationships")
            lines.append("")
            # Group by rel_type
            by_type: dict[str, list] = {}
            for r in rels:
                by_type.setdefault(r["rel_type"], []).append(r)
            for rel_type, rel_list in sorted(by_type.items()):
                lines.append(f"### {rel_type}")
                lines.append("")
                for r in rel_list:
                    other = r["target_id"] if r["source_id"] == entity_id else r["source_id"]
                    lines.append(f"- [[{other}]]")
                lines.append("")

        return "\n".join(lines)

    def export_neo4j_csv(self, output_dir: Path) -> dict[str, Path]:
        """
        Export graph to Neo4j-importable CSV files.
        Returns dict of {name: path} for all files written.
        """
        import csv
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        files: dict[str, Path] = {}

        # Node files per entity type
        for type_row in self.entity_types():
            etype = type_row["type"]
            entities = self.conn.execute(
                "SELECT id, name, metadata FROM entities WHERE type = ?", (etype,)
            ).fetchall()

            # Collect all metadata keys for this type to use as columns
            meta_keys: list[str] = []
            metas = []
            for e in entities:
                try:
                    m = json.loads(e[2])
                except (json.JSONDecodeError, TypeError):
                    m = {}
                metas.append(m)
                for k in m:
                    if k not in meta_keys:
                        meta_keys.append(k)

            path = output_dir / f"nodes_{etype}.csv"
            with open(path, "w", newline="") as f:
                fieldnames = [f"{etype}Id:ID({etype})", "name"] + meta_keys
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for e, m in zip(entities, metas):
                    row = {f"{etype}Id:ID({etype})": e[0], "name": e[1]}
                    for k in meta_keys:
                        v = m.get(k, "")
                        row[k] = v if not isinstance(v, (dict, list)) else json.dumps(v)
                    writer.writerow(row)
            files[f"nodes_{etype}"] = path

        # Relationship files per rel_type
        for rel_row in self.relationship_types():
            rtype = rel_row["rel_type"]
            rels = self.conn.execute(
                "SELECT source_id, target_id FROM relationships WHERE rel_type = ?", (rtype,)
            ).fetchall()
            path = output_dir / f"rels_{rtype.lower()}.csv"
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[":START_ID", ":END_ID", ":TYPE"])
                writer.writeheader()
                for r in rels:
                    writer.writerow({":START_ID": r[0], ":END_ID": r[1], ":TYPE": rtype})
            files[f"rels_{rtype.lower()}"] = path

        return files
