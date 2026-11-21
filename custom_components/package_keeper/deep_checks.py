"""Contrôles que le contrôle de configuration de Home Assistant ne fait pas.

Ces erreurs ne se voient sinon qu'au démarrage, dans les journaux ou en
réparation : templates Jinja invalides, automatisations et scripts mal écrits,
unique_id déjà utilisés par un autre package. Lecture seule.
"""

from __future__ import annotations

from collections.abc import Iterator
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
import voluptuous as vol

_TEMPLATE_MARKERS = ("{{", "{%", "{#")
# Domaines dont les clés de premier niveau sont des object_id (input_boolean: {x: …})
KEYED_DOMAINS = frozenset(
    {
        "counter",
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "schedule",
        "script",
        "timer",
    }
)
_ENTITY_DOMAINS = frozenset(
    {"sensor", "binary_sensor", "switch", "button", "number", "select", "image", "weather"}
    | {"light", "fan", "cover", "lock", "vacuum", "alarm_control_panel", "event", "update"}
)


def base_domain(key: object) -> str:
    """« automation old » → « automation » (clés multiples d'un même domaine)."""
    return str(key).split(" ", 1)[0]


def _walk(node: Any, path: str) -> Iterator[tuple[str, Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path} → {key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index + 1}]")


def template_errors(hass: HomeAssistant, content: dict[str, Any]) -> list[str]:
    """Compile chaque template du package avec le moteur de Home Assistant."""
    errors = []
    for path, value in _walk(content, ""):
        if not isinstance(value, str) or not any(m in value for m in _TEMPLATE_MARKERS):
            continue
        try:
            Template(value, hass).ensure_valid()
        except TemplateError as err:
            message = str(err).removeprefix("TemplateSyntaxError: ")
            errors.append(f"Template invalide ({path}) : {message}")
    return errors


async def automation_script_errors(hass: HomeAssistant, content: dict[str, Any]) -> list[str]:
    """Valide automatisations et scripts avec les fonctions utilisées à leur chargement."""
    from homeassistant.components.automation.config import (
        async_validate_config_item as validate_automation,
    )
    from homeassistant.components.script.config import (
        async_validate_config_item as validate_script,
    )

    errors = []
    for key, value in content.items():
        domain = base_domain(key)
        if domain == "automation":
            items = value if isinstance(value, list) else [value]
            for index, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    continue
                label = item.get("alias") or item.get("id") or f"n° {index}"
                try:
                    await validate_automation(hass, str(item.get("id", index)), item)
                except (vol.Invalid, HomeAssistantError) as err:
                    errors.append(f"Automatisation « {label} » : {_humanize(err)}")
        elif domain == "script" and isinstance(value, dict):
            for object_id, item in value.items():
                if not isinstance(item, dict):
                    continue
                try:
                    await validate_script(hass, str(object_id), item)
                except (vol.Invalid, HomeAssistantError) as err:
                    errors.append(f"Script « {object_id} » : {_humanize(err)}")
    return errors


def _humanize(err: Exception) -> str:
    text = str(err)
    return re.sub(r"\s+", " ", text).strip()


def identifiers(content: dict[str, Any]) -> set[tuple[str, str]]:
    """(portée, identifiant) des unique_id et id d'automatisation définis par un package.

    La portée suit la clé du registre d'entités (domaine + plateforme) : deux
    capteurs de plateformes différentes peuvent avoir le même unique_id.
    """
    found: set[tuple[str, str]] = set()

    def visit(node: Any, scope: str) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item, scope)
            return
        if not isinstance(node, dict):
            return
        if isinstance(node.get("platform"), str):
            scope = f"{scope.split('.')[0]}.{node['platform']}"
        if node.get("unique_id") is not None:
            found.add((scope, str(node["unique_id"])))
        for key, value in node.items():
            if scope.startswith("template") and key in _ENTITY_DOMAINS:
                visit(value, f"template.{key}")
            elif isinstance(value, (dict, list)):
                visit(value, scope)

    for key, value in content.items():
        domain = base_domain(key)
        if domain == "automation":
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and item.get("id") is not None:
                    found.add(("automation", str(item["id"])))
            continue
        visit(value, domain)
    return found


def duplicate_errors(content: dict[str, Any], others: dict[str, dict[str, Any]]) -> list[str]:
    """unique_id ou id d'automatisation déjà utilisés par un autre package."""
    mine = identifiers(content)
    errors = []
    for other_name, other_content in sorted(others.items()):
        for scope, uid in sorted(mine & identifiers(other_content)):
            what = "id d'automatisation" if scope == "automation" else f"unique_id ({scope})"
            errors.append(f"{what} « {uid} » déjà utilisé par le package « {other_name} »")
    return errors


def defined_entities(hass: HomeAssistant, content: dict[str, Any]) -> set[str]:
    """entity_id créés par un package : clés des domaines « à clés » + registre d'entités."""
    entity_ids: set[str] = set()
    for key, value in content.items():
        domain = base_domain(key)
        if domain in KEYED_DOMAINS and isinstance(value, dict):
            entity_ids.update(f"{domain}.{object_id}" for object_id in value)
    registry = er.async_get(hass)
    for scope, uid in identifiers(content):
        domain, platform = _registry_key(scope)
        if domain and (entity_id := registry.async_get_entity_id(domain, platform, uid)):
            entity_ids.add(entity_id)
    return entity_ids


def _registry_key(scope: str) -> tuple[str | None, str]:
    """Portée d'identifiers() → (domaine d'entité, plateforme) du registre.

    « automation » → (automation, automation) ; « template.sensor » → (sensor, template) ;
    « sensor.derivative » → (sensor, derivative). Une portée sans plateforme (unique_id
    d'une intégration configurée autrement) n'est pas résolue.
    """
    if scope == "automation":
        return "automation", "automation"
    head, _, tail = scope.partition(".")
    if not tail:
        return None, ""
    if head == "template":
        return tail, "template"
    return head, tail


def citing(entity_ids: set[str], texts: dict[str, str]) -> dict[str, list[str]]:
    """Packages (texte brut) qui citent ces entités."""
    result = {}
    for name, text in sorted(texts.items()):
        used = sorted(
            entity_id
            for entity_id in entity_ids
            if re.search(rf"(?<![\w.]){re.escape(entity_id)}(?![\w])", text)
        )
        if used:
            result[name] = used
    return result
