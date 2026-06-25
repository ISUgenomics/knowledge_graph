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

    def _registry_dynamic_family(self, family_id: str) -> dict[str, Any]:
        families = self._registry_operators().get("dynamic_families", {})
        family = families.get(str(family_id), {}) if isinstance(families, dict) else {}
        return dict(family) if isinstance(family, dict) else {}


class RegistryOperatorModule(RegistryChatModule):
    # Dynamic-family contract:
    # - Registry config owns semantic source selection rules, normalization,
    #   flag classification, alias templates, owner typing, and output shape.
    # - Domain modules should only override `_dynamic_family_scoped_aliases()`
    #   when live graph data is needed to provide scoped placeholder values
    #   such as organism aliases.
    # - If a domain needs more than scoped alias inputs, prefer extending this
    #   shared executor before reintroducing semantic family logic locally.
    def _dynamic_family_source_rows(self, chat: "ChatToSQL", family_id: str) -> list[dict[str, Any]]:
        family = self._registry_dynamic_family(family_id)
        source = family.get("source", {}) if isinstance(family, dict) else {}
        if not isinstance(source, dict):
            return []
        if str(source.get("mode", "") or "") != "branch_tags":
            return []
        root_tag_id = str(source.get("root_tag_id", "") or "")
        hierarchy_rel_type = str(source.get("hierarchy_rel_type", "BROADER") or "BROADER")
        fallback_pattern = str(source.get("fallback_tag_id_pattern", "") or "")
        branch_ids = chat.db._ordered_branch_ids(root_tag_id, hierarchy_edge=hierarchy_rel_type)
        if branch_ids == [root_tag_id] and not chat.db.get_entity(root_tag_id):
            if not fallback_pattern:
                return []
            return chat.db.execute_read(
                f"SELECT id, name FROM entities WHERE type = 'tag' AND id LIKE '{fallback_pattern}' ORDER BY id"
            )
        rows = []
        for tag_id in branch_ids:
            entity = chat.db.get_entity(tag_id)
            if not entity or entity.get("type") != "tag" or entity.get("id") == root_tag_id:
                continue
            rows.append({"id": entity["id"], "name": entity.get("name", entity["id"])})
        return rows

    @staticmethod
    def _dynamic_family_flag_values(flag_config: dict[str, Any], norm_id: str, norm_name: str) -> dict[str, bool]:
        flag_values: dict[str, bool] = {}
        for flag_name, flag_rule in flag_config.items():
            if not isinstance(flag_rule, dict):
                continue
            substrings = [str(item).lower() for item in list(flag_rule.get("any_substrings", []) or []) if str(item).strip()]
            flag_values[str(flag_name)] = any(substring in norm_id or substring in norm_name for substring in substrings)
        return flag_values

    @staticmethod
    def _dynamic_family_base_aliases(tag_id: str, tag_name: str, normalize: dict[str, Any]) -> set[str]:
        id_strip_prefix = str(normalize.get("id_strip_prefix", "") or "")
        remove_suffixes = [str(item).lower() for item in list(normalize.get("remove_suffixes", []) or []) if str(item).strip()]
        norm_id = str(tag_id or "").strip().lower()
        norm_name = str(tag_name or "").strip().lower()
        base_id = norm_id[len(id_strip_prefix):] if id_strip_prefix and norm_id.startswith(id_strip_prefix) else norm_id
        aliases = {norm_name, base_id}
        if normalize.get("replace_dash_with_space", False):
            aliases.update({norm_name.replace("-", " "), base_id.replace("-", " ")})
        for suffix in remove_suffixes:
            aliases.update({alias.removesuffix(suffix) for alias in list(aliases)})
        return {alias.strip() for alias in aliases if alias.strip()}

    @staticmethod
    def _dynamic_family_matches_flags(flag_values: dict[str, bool], include_when_any: list[str], exclude_when: list[str]) -> bool:
        if exclude_when and any(flag_values.get(flag_name, False) for flag_name in exclude_when):
            return False
        if include_when_any:
            return any(flag_values.get(flag_name, False) for flag_name in include_when_any)
        return True

    @staticmethod
    def _dynamic_family_expand_templates(templates: list[str], scoped_aliases: set[str]) -> set[str]:
        expanded: set[str] = set()
        for template in templates:
            for scoped_alias in scoped_aliases:
                expanded.add(str(template).format(organism=scoped_alias).strip().lower())
        return expanded

    def _dynamic_family_owner_types(self, family: dict[str, Any], flag_values: dict[str, bool]) -> list[str]:
        owner_config = family.get("owner_types", {}) if isinstance(family, dict) else {}
        if not isinstance(owner_config, dict):
            return ["protein"]
        when_flags = owner_config.get("when_flags", {}) if isinstance(owner_config, dict) else {}
        if isinstance(when_flags, dict):
            for flag_name, owner_types in when_flags.items():
                if flag_values.get(str(flag_name), False):
                    return [str(item) for item in list(owner_types or []) if str(item).strip()]
        return [str(item) for item in list(owner_config.get("default", []) or ["protein"]) if str(item).strip()]

    def _dynamic_family_scoped_aliases(self, chat: "ChatToSQL", family: dict[str, Any]) -> dict[str, set[str]]:
        # Domain hook for supplying live scoped values used by alias templates.
        # Typical examples are primary/secondary organism alias sets.
        return {}

    def _dynamic_family_alias_sets(
        self,
        chat: "ChatToSQL",
        family: dict[str, Any],
        base_aliases: set[str],
        flag_values: dict[str, bool],
    ) -> tuple[set[str], dict[str, set[str]]]:
        templates = family.get("alias_templates", {}) if isinstance(family, dict) else {}
        if not isinstance(templates, dict):
            return base_aliases, {}
        generic_config = templates.get("generic", {}) if isinstance(templates, dict) else {}
        generic_aliases = set(base_aliases)
        if isinstance(generic_config, dict):
            for flag_name, values in generic_config.items():
                if flag_values.get(str(flag_name), False):
                    generic_aliases.update(str(item).strip().lower() for item in list(values or []) if str(item).strip())

        scoped_config = templates.get("organism_scoped", {}) if isinstance(templates, dict) else {}
        if not isinstance(scoped_config, dict):
            return generic_aliases, {}
        templates_by_flag = scoped_config.get("templates", {}) if isinstance(scoped_config, dict) else {}
        template_flag_matches = scoped_config.get("template_flag_matches", {}) if isinstance(scoped_config, dict) else {}
        scoped_alias_sets = self._dynamic_family_scoped_aliases(chat, family)
        rendered_aliases_by_set: dict[str, set[str]] = {set_name: set() for set_name in scoped_alias_sets}
        organism_sets = scoped_config.get("organism_sets", {}) if isinstance(scoped_config, dict) else {}
        for flag_name, set_templates in templates_by_flag.items():
            match_flags = [
                str(item) for item in list(
                    template_flag_matches.get(flag_name, [flag_name]) if isinstance(template_flag_matches, dict) else [flag_name]
                ) if str(item).strip()
            ]
            if not any(flag_values.get(match_flag, False) for match_flag in match_flags) or not isinstance(set_templates, dict):
                continue
            for set_name, scoped_aliases in scoped_alias_sets.items():
                set_config = organism_sets.get(set_name, {}) if isinstance(organism_sets, dict) else {}
                if not isinstance(set_config, dict):
                    continue
                include_when_any = [str(item) for item in list(set_config.get("include_when_any_flags", []) or []) if str(item).strip()]
                exclude_when = [str(item) for item in list(set_config.get("exclude_when_flags", []) or []) if str(item).strip()]
                if not self._dynamic_family_matches_flags(flag_values, include_when_any, exclude_when):
                    continue
                rendered_aliases_by_set.setdefault(set_name, set()).update(
                    self._dynamic_family_expand_templates(
                        [str(item) for item in list(set_templates.get(set_name, []) or []) if str(item).strip()],
                        scoped_aliases,
                    )
                )
        return generic_aliases, rendered_aliases_by_set

    def _dynamic_family_specs(self, chat: "ChatToSQL", family_id: str) -> list[dict[str, Any]]:
        family = self._registry_dynamic_family(family_id)
        normalize = family.get("normalize", {}) if isinstance(family, dict) else {}
        classify = family.get("classify", {}) if isinstance(family, dict) else {}
        output = family.get("output", {}) if isinstance(family, dict) else {}
        if not isinstance(normalize, dict) or not isinstance(classify, dict) or not isinstance(output, dict):
            return []
        specs: list[dict[str, Any]] = []
        for row in self._dynamic_family_source_rows(chat, family_id):
            tag_id = str(row.get("id", "") or "")
            tag_name = str(row.get("name", "") or "")
            norm_id = tag_id.lower()
            norm_name = tag_name.lower()
            base_aliases = self._dynamic_family_base_aliases(tag_id, tag_name, normalize)
            flag_values = self._dynamic_family_flag_values(
                classify.get("flags", {}) if isinstance(classify, dict) else {},
                norm_id,
                norm_name,
            )
            generic_aliases, scoped_aliases = self._dynamic_family_alias_sets(chat, family, base_aliases, flag_values)
            specs.append({
                "id": norm_id.replace(str(normalize.get("id_strip_prefix", "") or ""), "", 1),
                "aliases": [
                    f" {alias.strip()} "
                    for alias in ({*generic_aliases, *(alias for values in scoped_aliases.values() for alias in values)})
                    if alias.strip()
                ],
                "generic_aliases": [f" {alias.strip()} " for alias in generic_aliases if alias.strip()],
                **{
                    f"{set_name}_scoped_aliases": [f" {alias.strip()} " for alias in aliases if alias.strip()]
                    for set_name, aliases in scoped_aliases.items()
                },
                "tag_ids": [tag_id],
                "owner_types": self._dynamic_family_owner_types(family, flag_values),
                "kind": str(output.get("condition_kind", "tag_evidence") or "tag_evidence"),
                **{f"is_{flag_name}": value for flag_name, value in flag_values.items()},
            })
        return specs

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
