"""Enregistrement : contrôles, retour arrière, suppression, restauration, rechargement."""

from __future__ import annotations

from pathlib import Path

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.package_keeper.admin_phone import CONF_ADMIN_NOTIFY_TARGET
from custom_components.package_keeper.manager import PackageManager

GOOD = """\
# Fenêtre virtuelle du salon
input_boolean:
  fenetre_salon_virtuelle:
    name: Fenêtre salon virtuelle
"""
# Clé inconnue : le contrôle de configuration de Home Assistant la refuse
BROKEN = """\
input_boolean:
  fenetre_salon_virtuelle:
    nom_inconnu: 3
    name: [pas, une, chaine]
"""


def _manager(entry: MockConfigEntry) -> PackageManager:
    return entry.runtime_data


def _phone(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_pixel_9", handler)
    return calls


async def test_check_does_not_write(hass: HomeAssistant, entry, config_dir: Path) -> None:
    outcome = await _manager(entry).async_save("salon", GOOD, dry_run=True)
    assert outcome.ok and outcome.action == "checked"
    assert not (config_dir / "packages" / "salon.yaml").exists()
    assert not list((config_dir / "packages").iterdir())  # pas de fichier temporaire oublié


async def test_save_new_package(hass: HomeAssistant, entry, config_dir: Path) -> None:
    await async_setup_component(hass, "input_boolean", {})
    outcome = await _manager(entry).async_save("salon", GOOD)
    assert outcome.ok, outcome
    assert (config_dir / "packages" / "salon.yaml").read_text(encoding="utf-8") == GOOD
    assert outcome.reload == ["input_boolean.reload"]
    assert outcome.restart == []
    assert outcome.backup is None  # nouveau fichier : rien à sauvegarder
    overview = await _manager(entry).async_overview()
    assert overview["enabled"] and overview["directory"] == "/config/packages"
    assert overview["packages"][0]["description"] == "Fenêtre virtuelle du salon"


async def test_restart_needed_for_yaml_platform(hass: HomeAssistant, entry) -> None:
    text = "sensor:\n  - platform: derivative\n    source: sensor.x\n    name: Pente\n"
    outcome = await _manager(entry).async_save("pente", text, dry_run=True)
    assert outcome.ok
    assert outcome.restart == ["sensor (derivative)"]


async def test_yaml_error_writes_nothing(hass: HomeAssistant, entry, config_dir: Path) -> None:
    outcome = await _manager(entry).async_save("salon", "input_boolean:\n  x: [\n")
    assert not outcome.ok and outcome.error == "yaml_error"
    assert ".pk-tmp" not in (outcome.detail or "")
    assert not list((config_dir / "packages").iterdir())


async def test_broken_config_is_rolled_back(hass: HomeAssistant, entry, config_dir: Path) -> None:
    hass.config_entries.async_update_entry(
        entry, data={CONF_ADMIN_NOTIFY_TARGET: "notify.mobile_app_pixel_9"}
    )
    calls = _phone(hass)
    manager = _manager(entry)
    assert (await manager.async_save("salon", GOOD)).ok

    outcome = await manager.async_save("salon", BROKEN)
    await hass.async_block_till_done()
    assert not outcome.ok and outcome.rolled_back and outcome.error == "config_invalid"
    assert "input_boolean" in outcome.detail
    # L'ancienne version est remise, la version cassée n'est nulle part en place
    assert (config_dir / "packages" / "salon.yaml").read_text(encoding="utf-8") == GOOD
    assert outcome.backup  # la version d'avant a quand même été sauvegardée
    titles = [c.data["title"] for c in calls]
    assert any("annulée" in t or "cancelled" in t for t in titles)


async def test_duplicate_key_is_rolled_back(hass: HomeAssistant, entry, config_dir: Path) -> None:
    """Deux packages qui définissent la même entité : conflit détecté, annulé."""
    assert (await _manager(entry).async_save("salon", GOOD)).ok
    outcome = await _manager(entry).async_save("doublon", GOOD)
    assert outcome.rolled_back and "duplicate" in outcome.detail
    assert not (config_dir / "packages" / "doublon.yaml").exists()


async def test_new_broken_package_removed(hass: HomeAssistant, entry, config_dir: Path) -> None:
    outcome = await _manager(entry).async_save("casse", BROKEN)
    assert outcome.rolled_back
    assert not (config_dir / "packages" / "casse.yaml").exists()


async def test_existing_error_does_not_block(hass: HomeAssistant, entry, config_dir: Path) -> None:
    """Une configuration déjà cassée ailleurs ne doit pas empêcher d'enregistrer."""
    broken_elsewhere = BROKEN.replace("fenetre_salon_virtuelle", "autre_chose")
    (config_dir / "packages" / "deja_casse.yaml").write_text(broken_elsewhere, encoding="utf-8")
    outcome = await _manager(entry).async_save("salon", GOOD)
    assert outcome.ok, outcome


async def test_delete_then_restore(hass: HomeAssistant, entry, config_dir: Path) -> None:
    manager = _manager(entry)
    assert (await manager.async_save("salon", GOOD)).ok
    outcome = await manager.async_delete("salon")
    assert outcome.ok and outcome.backup
    assert not (config_dir / "packages" / "salon.yaml").exists()
    assert (await manager.async_overview())["deleted"] == ["salon"]

    (backup,) = [b for b in await manager.async_backups("salon") if b["reason"] == "deleted"]
    outcome = await manager.async_restore("salon", backup["id"])
    assert outcome.ok and outcome.action == "restored"
    assert (config_dir / "packages" / "salon.yaml").read_text(encoding="utf-8") == GOOD
    assert (await manager.async_overview())["deleted"] == []
    assert (await manager.async_delete("absent")).error == "not_found"


async def test_packages_disabled(hass: HomeAssistant, entry, config_dir: Path) -> None:
    (config_dir / "configuration.yaml").write_text("default_config:\n", encoding="utf-8")
    manager = _manager(entry)
    assert (await manager.async_save("salon", GOOD)).error == "packages_disabled"
    overview = await manager.async_overview()
    assert overview["enabled"] is False and overview["packages"] == []
    # configuration.yaml n'a pas été touché
    assert (config_dir / "configuration.yaml").read_text(encoding="utf-8") == "default_config:\n"


async def test_include_outside_config_refused(hass: HomeAssistant, entry) -> None:
    outcome = await _manager(entry).async_save("x", "sensor: !include ../../../etc/passwd\n")
    assert outcome.error == "include_outside"
    outcome = await _manager(entry).async_save("x", "sensor: !include ../.storage/auth\n")
    assert outcome.error == "include_outside"


async def test_secret_never_resolved_in_output(hass: HomeAssistant, entry, config_dir: Path) -> None:
    text = "input_text:\n  mdp:\n    name: !secret mot_de_passe\n"
    manager = _manager(entry)
    outcome = await manager.async_save("mdp", text)
    assert "ne-doit-jamais-sortir" not in str(outcome.as_dict())
    assert await manager.async_read("mdp") == text
    missing = await manager.async_save("mdp2", "input_text:\n  a:\n    name: !secret absent\n")
    assert missing.error == "yaml_error"
    assert "ne-doit-jamais-sortir" not in (missing.detail or "")


async def test_entity_inventory_advice(hass: HomeAssistant, entry) -> None:
    async def validate(call: ServiceCall) -> dict:
        if "light" not in call.data["yaml"]:
            return {"valid": False, "errors": ["Rien à vérifier"], "warnings": [],
                    "entities_checked": 0, "actions_checked": 0}
        return {"valid": False, "errors": ["entité inconnue : light.x"], "warnings": [],
                "entities_checked": 1, "actions_checked": 0}

    hass.services.async_register(
        "entity_inventory", "validate", validate, supports_response=SupportsResponse.ONLY
    )
    outcome = await _manager(entry).async_save("salon", GOOD, dry_run=True)
    assert outcome.ok and outcome.advice == {}  # rien de cité : pas d'avis parasite

    with_light = GOOD + "automation:\n  - triggers: []\n    actions:\n      - action: light.turn_on\n        target:\n          entity_id: light.x\n"
    outcome = await _manager(entry).async_save("salon", with_light, dry_run=True)
    assert outcome.ok  # indicatif : n'empêche rien
    assert outcome.advice == {"errors": ["entité inconnue : light.x"]}
    assert (await _manager(entry).async_overview())["entity_inventory"] is True


async def test_phone_notified_on_change(hass: HomeAssistant, entry) -> None:
    hass.config_entries.async_update_entry(
        entry, data={CONF_ADMIN_NOTIFY_TARGET: "notify.mobile_app_pixel_9"}
    )
    calls = _phone(hass)
    assert (await _manager(entry).async_save("salon", GOOD)).ok
    await hass.async_block_till_done()
    assert len(calls) == 1 and "salon" in calls[0].data["message"]

    hass.config_entries.async_update_entry(entry, options={**entry.options, "notify_changes": False})
    assert (await _manager(entry).async_save("salon", GOOD + "\n")).ok
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_reload_only_reload_actions(hass: HomeAssistant, entry) -> None:
    called: list[str] = []
    hass.services.async_register("input_boolean", "reload", lambda c: called.append("ib"))
    hass.services.async_register("light", "turn_off", lambda c: called.append("off"))
    done = await _manager(entry).async_reload(
        ["input_boolean.reload", "light.turn_off", "absent.reload"]
    )
    assert done == ["input_boolean.reload"] and called == ["ib"]


# --- 0.2.0 : contrôles que Home Assistant ne fait qu'au démarrage ----------


async def test_broken_template_refused(hass: HomeAssistant, entry, config_dir: Path) -> None:
    text = (
        "template:\n  - sensor:\n      - name: Essai\n        unique_id: essai_tpl\n"
        "        state: \"{{ states('sensor.x') | float(0 }}\"\n"
    )
    outcome = await _manager(entry).async_save("tpl", text)
    assert outcome.error == "invalid_content" and "Template invalide" in outcome.detail
    assert "state" in outcome.detail  # chemin de la clé fautive
    assert not (config_dir / "packages" / "tpl.yaml").exists()
    ok = text.replace("float(0 }}", "float(0) }}")
    assert (await _manager(entry).async_save("tpl", ok, dry_run=True)).ok


async def test_invalid_automation_and_script_refused(hass: HomeAssistant, entry) -> None:
    automation = (
        "automation:\n  - id: essai_auto\n    alias: Essai\n    triggers:\n"
        "      - trigger: heure_fixe\n    actions: []\n"
    )
    outcome = await _manager(entry).async_save("auto", automation, dry_run=True)
    assert outcome.error == "invalid_content" and "Automatisation « Essai »" in outcome.detail

    script = "script:\n  essai:\n    sequence:\n      - delay: pas_une_duree\n"
    outcome = await _manager(entry).async_save("scr", script, dry_run=True)
    assert outcome.error == "invalid_content" and "Script « essai »" in outcome.detail

    good = (
        "automation old:\n  - id: essai_ok\n    triggers:\n      - trigger: time\n"
        "        at: '22:00:00'\n    actions: []\nscript:\n  essai:\n    sequence: []\n"
    )
    assert (await _manager(entry).async_save("ok", good, dry_run=True)).ok


async def test_duplicate_unique_id_refused(hass: HomeAssistant, entry, config_dir: Path) -> None:
    derivee = (
        "sensor:\n  - platform: derivative\n    source: sensor.x\n    name: Pente\n"
        "    unique_id: pente_x\n"
        "template:\n  - sensor:\n      - name: A\n        unique_id: meme_id\n        state: '1'\n"
        "automation:\n  - id: auto_1\n    triggers: []\n    actions: []\n"
    )
    manager = _manager(entry)
    assert (await manager.async_save("derivee", derivee)).ok
    # Re-enregistrer le même package n'est pas un doublon
    assert (await manager.async_save("derivee", derivee + "\n")).ok

    outcome = await manager.async_save("copie", derivee, dry_run=True)
    assert outcome.error == "invalid_content"
    for uid in ("pente_x", "meme_id", "auto_1"):
        assert f"« {uid} » déjà utilisé par le package « derivee »" in outcome.detail

    # Même unique_id mais autre domaine ou autre plateforme : pas un conflit
    other = (
        "template:\n  - binary_sensor:\n      - name: B\n        unique_id: meme_id\n"
        "        state: 'on'\n"
        "sensor:\n  - platform: statistics\n    source: sensor.x\n    name: Stat\n"
        "    unique_id: pente_x\n    state_characteristic: mean\n    max_age:\n      hours: 1\n"
    )
    assert (await manager.async_save("autre", other, dry_run=True)).ok


async def test_dependents_before_delete(hass: HomeAssistant, entry, config_dir: Path) -> None:
    manager = _manager(entry)
    assert (await manager.async_save("salon", GOOD)).ok
    user = (
        "automation:\n  - id: utilise_salon\n    triggers:\n      - trigger: state\n"
        "        entity_id: input_boolean.fenetre_salon_virtuelle\n    actions: []\n"
    )
    assert (await manager.async_save("utilisateur", user)).ok
    assert await manager.async_dependents("salon") == {
        "utilisateur": ["input_boolean.fenetre_salon_virtuelle"]
    }
    assert await manager.async_dependents("utilisateur") == {}


async def test_merge_mode_body(hass: HomeAssistant, entry, config_dir: Path) -> None:
    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n  packages: !include_dir_merge_named packages\n", encoding="utf-8"
    )
    text = "salon:\n  input_boolean:\n    fenetre_merge:\n      name: Fenêtre\n"
    outcome = await _manager(entry).async_save("salon", text)
    assert outcome.ok, outcome
    assert outcome.restart == ["input_boolean"] or outcome.reload == ["input_boolean.reload"]


# --- 0.3.0 : rechargement ciblé, entités retirées et orphelines --------------

PACK = """\
template:
  - sensor:
      - name: Uptime
        unique_id: pk_uptime
        state: "1"
script:
  pk_notifier:
    sequence: []
automation:
  - id: pk_cpu
    alias: CPU
    triggers: []
    actions: []
  - id: pk_disque
    alias: Disque
    triggers: []
    actions: []
"""


def _reload_services(hass: HomeAssistant) -> list[str]:
    called: list[str] = []
    for domain in ("automation", "script", "template", "derivative"):
        hass.services.async_register(domain, "reload", lambda c, d=domain: called.append(d))
    return called


async def test_targeted_reload_and_removed(hass: HomeAssistant, entry) -> None:
    _reload_services(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "automation", "automation", "pk_disque", suggested_object_id="system_disque"
    )
    registry.async_get_or_create("sensor", "template", "pk_uptime", suggested_object_id="up")
    manager = _manager(entry)

    first = await manager.async_save("system", PACK)
    assert first.reload == ["automation.reload", "script.reload", "template.reload"]
    assert first.removed == []

    # Seule une automatisation retirée : seul automation.reload est proposé
    v2 = PACK.replace(
        "  - id: pk_disque\n    alias: Disque\n    triggers: []\n    actions: []\n", ""
    )
    checked = await manager.async_save("system", v2, dry_run=True)
    assert checked.reload == ["automation.reload"] and checked.restart == []
    assert checked.removed == ["automation.system_disque"]
    saved = await manager.async_save("system", v2)
    assert saved.reload == ["automation.reload"]
    assert saved.removed == ["automation.system_disque"]

    # Un domaine entier retiré se recharge aussi
    v3 = v2.split("script:")[0]
    outcome = await manager.async_save("system", v3, dry_run=True)
    assert outcome.reload == ["automation.reload", "script.reload"]

    # Rien de changé : rien à recharger
    same = await manager.async_save("system", v2 + "# commentaire\n", dry_run=True)
    assert same.reload == [] and same.restart == []


async def test_removed_platform_counts(hass: HomeAssistant, entry) -> None:
    _reload_services(hass)
    manager = _manager(entry)
    text = "sensor:\n  - platform: derivative\n    source: sensor.x\n    unique_id: d1\n"
    assert (await manager.async_save("pente", text)).ok
    outcome = await manager.async_save("pente", "input_boolean:\n  b:\n    name: B\n", dry_run=True)
    assert "derivative.reload" in outcome.reload  # l'ancienne plateforme doit être déchargée


async def test_orphans_after_reload(hass: HomeAssistant, entry, hass_ws_client) -> None:
    registry = er.async_get(hass)
    gone = registry.async_get_or_create(
        "automation", "automation", "pk_x", suggested_object_id="ancienne"
    ).entity_id
    alive = registry.async_get_or_create(
        "automation", "automation", "pk_y", suggested_object_id="vivante"
    ).entity_id
    hass.states.async_set(gone, "unavailable", {"restored": True})
    hass.states.async_set(alive, "on")
    hass.services.async_register("automation", "reload", lambda c: None)

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "package_keeper/reload",
            "services": ["automation.reload"],
            "entities": [gone, alive, "automation.inconnue"],
        }
    )
    reply = await client.receive_json()
    assert reply["result"] == {"reloaded": ["automation.reload"], "orphans": [gone]}


async def test_delete_lists_removed(hass: HomeAssistant, entry) -> None:
    manager = _manager(entry)
    assert (await manager.async_save("salon", GOOD)).ok
    outcome = await manager.async_delete("salon")
    assert outcome.removed == ["input_boolean.fenetre_salon_virtuelle"]
