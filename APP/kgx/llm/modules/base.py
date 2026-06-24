from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kgx.llm.chat_sql import ChatToSQL


class ChatModule:
    def corpus_section(self) -> str | None:
        return None

    def preferred_result_types(self, chat: "ChatToSQL", message: str, available_types: list[str]) -> list[str]:
        return []

    def suppressed_result_types(self, chat: "ChatToSQL", message: str, available_types: list[str]) -> list[str]:
        return []

    def schema_context_lines(self, chat: "ChatToSQL") -> list[str]:
        return []

    def validation_error(self, chat: "ChatToSQL", sql: str, requested_types: list[str], message: str) -> str | None:
        return None

    def synthesize_query(self, chat: "ChatToSQL", message: str, sql: str, requested_types: list[str]) -> str | None:
        return None


class RegistryChatModule(ChatModule):
    def __init__(
        self,
        *,
        semantic_registry_loader,
        semantic_schema: dict[str, Any] | None = None,
        semantic_registry: dict[str, Any] | None = None,
    ):
        self.semantic_registry = semantic_registry or semantic_registry_loader(None)
        self.semantic_schema = semantic_schema or dict(self.semantic_registry.get("schema", {}) or {})

    def _semantic_registry_section(self, key: str) -> dict[str, Any]:
        section = self.semantic_registry.get(str(key), {}) if isinstance(self.semantic_registry, dict) else {}
        return dict(section) if isinstance(section, dict) else {}

    def _semantic_schema_groups(self) -> dict[str, Any]:
        groups = self.semantic_schema.get("groups", {}) if isinstance(self.semantic_schema, dict) else {}
        return dict(groups) if isinstance(groups, dict) else {}

    def _registry_operators(self) -> dict[str, Any]:
        return self._semantic_registry_section("operators")

    def _registry_operator_spec(self, key: str) -> dict[str, Any]:
        specs = self._registry_operators().get("specs", {})
        spec = specs.get(str(key), {}) if isinstance(specs, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _registry_condition_handlers(self) -> dict[str, str]:
        handlers = self._registry_operators().get("condition_handlers", {})
        return dict(handlers) if isinstance(handlers, dict) else {}

    def _registry_relation_families(self) -> dict[str, Any]:
        return self._semantic_registry_section("relation_families")

    def _registry_relation_family(self, family_id: str) -> dict[str, Any]:
        families = self._registry_relation_families()
        family = families.get(family_id, {}) if isinstance(families, dict) else {}
        return dict(family) if isinstance(family, dict) else {}


class RegistryOperatorModule(RegistryChatModule):
    def _registry_path(self, from_type: str, to_type: str) -> list[dict[str, str]]:
        paths = self._semantic_registry_section("paths")
        key = f"{from_type}->{to_type}"
        path = paths.get(key, []) if isinstance(paths, dict) else []
        return [dict(step) for step in list(path or []) if isinstance(step, dict)]

    def _append_path_joins(
        self,
        chat: "ChatToSQL",
        *,
        from_type: str,
        to_type: str,
        current_node_ref: str,
        alias_index: int,
    ) -> tuple[list[str], str, int]:
        joins: list[str] = []
        registry_path = self._registry_path(from_type, to_type)
        if registry_path:
            path = [
                (
                    str(step.get("src", "")),
                    str(step.get("rel_type", "")),
                    str(step.get("dst", "")),
                    str(step.get("direction", "forward")),
                )
                for step in registry_path
            ]
        else:
            path = chat._shortest_type_path_any_direction(from_type, to_type)
        if from_type != to_type and not path:
            return [], "", alias_index
        ref = current_node_ref
        current_type = from_type
        for src, edge_rel, dst, direction in path:
            if src != current_type:
                return [], "", alias_index
            alias_index += 1
            rel_alias = f"p{alias_index}"
            if direction == "forward":
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {ref} AND {rel_alias}.rel_type = '{edge_rel}'"
                )
                ref = f"{rel_alias}.target_id"
            else:
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.target_id = {ref} AND {rel_alias}.rel_type = '{edge_rel}'"
                )
                ref = f"{rel_alias}.source_id"
            current_type = dst
        return joins, ref, alias_index

    @staticmethod
    def _format_operator_template(template: str, context: dict[str, Any]) -> str:
        try:
            return str(template).format(**context)
        except KeyError:
            return str(template)

    def _operator_rel_types(self, operator_id: str) -> list[str]:
        spec = self._registry_operator_spec(operator_id)
        rel_types: list[str] = []
        for step in list(spec.get("steps", []) or []):
            if not isinstance(step, dict) or step.get("kind") != "relationship":
                continue
            rel_type = str(step.get("rel_type", "") or "").strip()
            if rel_type and rel_type not in rel_types:
                rel_types.append(rel_type)
        return rel_types

    @staticmethod
    def _entity_type_clause(alias: str, entity_types: list[str]) -> str:
        if len(entity_types) == 1:
            return f"{alias}.type = '{entity_types[0]}'"
        return f"{alias}.type IN ({', '.join(repr(entity_type) for entity_type in entity_types)})"

    @staticmethod
    def _sql_in_list(values: list[str]) -> str:
        return ", ".join(repr(value) for value in values)

    def _append_registry_operator_joins(
        self,
        chat: "ChatToSQL" | None,
        *,
        operator_id: str,
        requested_type: str,
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        template_context: dict[str, Any] | None = None,
        initial_context: dict[str, Any] | None = None,
    ) -> tuple[bool, int, dict[str, Any]]:
        spec = self._registry_operator_spec(operator_id)
        if not spec:
            return False, alias_index, {}
        owner_type = str(spec.get("owner_type", "") or "")
        owner_type_ref = str(spec.get("owner_type_ref", "") or "")
        if owner_type_ref:
            owner_type = str((template_context or {}).get(owner_type_ref, "") or owner_type)
        if not owner_type:
            return False, alias_index, {}
        context = dict(initial_context or {})
        if "owner_ref" not in context:
            if chat is None:
                return False, alias_index, {}
            path_joins, owner_ref, alias_index = self._append_path_joins(
                chat,
                from_type=requested_type,
                to_type=owner_type,
                current_node_ref="e.id",
                alias_index=alias_index,
            )
            if requested_type != owner_type and not path_joins:
                return False, alias_index, {}
            joins.extend(path_joins)
            context["owner_ref"] = owner_ref or "e.id"
        if template_context:
            context.update(template_context)
        for step in list(spec.get("steps", []) or []):
            if not isinstance(step, dict):
                return False, alias_index, {}
            kind = str(step.get("kind", "") or "")
            alias_prefix = str(step.get("alias_prefix", "") or "op")
            bind = str(step.get("bind", "") or "").strip()
            if kind == "relationship":
                source_ref = self._format_operator_template(str(step.get("source_ref", "") or ""), context)
                rel_type = str(step.get("rel_type", "") or "").strip()
                rel_type_ref = str(step.get("rel_type_ref", "") or "").strip()
                if rel_type_ref:
                    rel_type = str(context.get(rel_type_ref, "") or rel_type)
                direction = str(step.get("direction", "forward") or "forward")
                if not source_ref or not rel_type:
                    return False, alias_index, {}
                alias_index += 1
                rel_alias = f"{alias_prefix}{alias_index}"
                if direction == "forward":
                    joins.append(
                        f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {source_ref} AND {rel_alias}.rel_type = '{rel_type}'"
                    )
                else:
                    joins.append(
                        f"JOIN relationships {rel_alias} ON {rel_alias}.target_id = {source_ref} AND {rel_alias}.rel_type = '{rel_type}'"
                    )
                if bind:
                    context[bind] = rel_alias
            elif kind == "entity":
                id_ref = self._format_operator_template(str(step.get("id_ref", "") or ""), context)
                entity_type = str(step.get("entity_type", "") or "").strip()
                entity_types_ref = str(step.get("entity_types_ref", "") or "").strip()
                id_in_ref = str(step.get("id_in_ref", "") or "").strip()
                entity_types = [entity_type] if entity_type else []
                if entity_types_ref:
                    entity_types = [str(item) for item in list(context.get(entity_types_ref, []) or []) if str(item).strip()]
                if not id_ref or not entity_types:
                    return False, alias_index, {}
                alias_index += 1
                entity_alias = f"{alias_prefix}{alias_index}"
                entity_clauses = [
                    f"{entity_alias}.id = {id_ref}",
                    self._entity_type_clause(entity_alias, entity_types),
                ]
                if id_in_ref:
                    id_values = [str(item) for item in list(context.get(id_in_ref, []) or []) if str(item).strip()]
                    if not id_values:
                        return False, alias_index, {}
                    entity_clauses.append(f"{entity_alias}.id IN ({self._sql_in_list(id_values)})")
                joins.append(
                    f"JOIN entities {entity_alias} ON {' AND '.join(entity_clauses)}"
                )
                if bind:
                    context[bind] = entity_alias
            else:
                return False, alias_index, {}
        for template in list(spec.get("where_templates", []) or []):
            where_lines.append(self._format_operator_template(str(template), context))
        return True, alias_index, context


class RegistryConditionModule(RegistryOperatorModule):
    @staticmethod
    def _find_unexpected_signature_error(
        sql_text: str,
        checks: list[tuple[list[str], bool, str]],
    ) -> str | None:
        sql_up = str(sql_text or "").upper()
        for signatures, requested, error in checks:
            normalized = [str(signature).upper() for signature in signatures if str(signature).strip()]
            if not normalized or requested:
                continue
            if any(signature in sql_up for signature in normalized):
                return error
        return None

    @staticmethod
    def _find_missing_signature_error(
        sql_text: str,
        checks: list[tuple[list[str], bool, str]],
    ) -> str | None:
        sql_up = str(sql_text or "").upper()
        for signatures, requested, error in checks:
            normalized = [str(signature).upper() for signature in signatures if str(signature).strip()]
            if not normalized or not requested:
                continue
            if not all(signature in sql_up for signature in normalized):
                return error
        return None

    def _semantic_condition_handler_name(self, condition: dict[str, Any]) -> str:
        kind = str(condition.get("kind", "") or "")
        return self._registry_condition_handlers().get(kind, "")

    def _semantic_condition_handlers_map(self) -> dict[str, Any]:
        return {}

    def _dispatch_semantic_condition(
        self,
        chat: "ChatToSQL",
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any] | None = None,
    ) -> tuple[bool, int]:
        handler_name = self._semantic_condition_handler_name(condition)
        handler = self._semantic_condition_handlers_map().get(handler_name)
        if handler is None:
            return True, alias_index
        return handler(
            chat,
            requested_type=requested_type,
            condition=condition,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            state=state or {},
        )

    def _build_semantic_entity_query(
        self,
        chat: "ChatToSQL",
        *,
        requested_type: str,
        conditions: list[dict[str, Any]],
        where_lines: list[str] | None = None,
        distinct: bool = True,
        state: dict[str, Any] | None = None,
    ) -> str | None:
        joins: list[str] = []
        compiled_where = list(where_lines or [f"WHERE e.type = '{requested_type}'"])
        alias_index = 0
        for condition in conditions:
            ok, alias_index = self._dispatch_semantic_condition(
                chat,
                requested_type=requested_type,
                condition=condition,
                joins=joins,
                where_lines=compiled_where,
                alias_index=alias_index,
                state=state,
            )
            if not ok:
                return None
        select_clause = "SELECT DISTINCT e.id, e.name, e.type" if distinct else "SELECT e.id, e.name, e.type"
        return "\n".join([
            select_clause,
            "FROM entities e",
            *joins,
            *compiled_where,
        ])
