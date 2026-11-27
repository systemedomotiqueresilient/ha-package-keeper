"""Config flow et options flow de Package Keeper."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .admin_phone import (
    CONF_ADMIN_NOTIFY_TARGET,
    is_valid_target,
    normalize_target,
    suggest_admin_target,
)
from .const import (
    CONF_BACKUPS_KEPT,
    CONF_GIT_BRANCH,
    CONF_GIT_MODE,
    CONF_GIT_TOKEN,
    CONF_GIT_URL,
    CONF_GIT_USERNAME,
    CONF_NOTIFY_CHANGES,
    DEFAULT_BACKUPS_KEPT,
    DEFAULT_GIT_BRANCH,
    DEFAULT_GIT_USERNAME,
    DEFAULT_NOTIFY_CHANGES,
    DOMAIN,
    GIT_MODE_LOCAL,
    GIT_MODE_OFF,
    GIT_MODE_REMOTE,
)
from .git_sync import GitError, async_visibility, git_available, validate_branch, validate_remote


def _schema(hass: HomeAssistant, options: dict[str, Any], target: str | None) -> vol.Schema:
    suggested, choices = suggest_admin_target(hass, target)
    return vol.Schema(
        {
            vol.Optional(
                CONF_ADMIN_NOTIFY_TARGET, description={"suggested_value": suggested}
            ): SelectSelector(
                SelectSelectorConfig(
                    options=choices, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(
                CONF_NOTIFY_CHANGES,
                default=options.get(CONF_NOTIFY_CHANGES, DEFAULT_NOTIFY_CHANGES),
            ): BooleanSelector(),
            vol.Required(
                CONF_BACKUPS_KEPT,
                default=options.get(CONF_BACKUPS_KEPT, DEFAULT_BACKUPS_KEPT),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=50, step=1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _split(user_input: dict[str, Any]) -> tuple[dict[str, Any], str | None, dict[str, str]]:
    """(options, téléphone admin pour entry.data, erreurs)."""
    values = dict(user_input)
    raw = values.pop(CONF_ADMIN_NOTIFY_TARGET, None)
    errors: dict[str, str] = {}
    if raw and str(raw).strip() and not is_valid_target(raw):
        errors[CONF_ADMIN_NOTIFY_TARGET] = "invalid_target"
    values[CONF_BACKUPS_KEPT] = int(values.get(CONF_BACKUPS_KEPT, DEFAULT_BACKUPS_KEPT))
    return values, normalize_target(raw), errors


_MODE_LABELS = {
    "fr": {
        GIT_MODE_OFF: "désactivée",
        GIT_MODE_LOCAL: "dépôt local seulement",
        GIT_MODE_REMOTE: "dépôt local + dépôt distant",
    },
    "en": {
        GIT_MODE_OFF: "off",
        GIT_MODE_LOCAL: "local repository only",
        GIT_MODE_REMOTE: "local + remote repository",
    },
}


def _lang(hass: HomeAssistant) -> str:
    return "fr" if (hass.config.language or "").startswith("fr") else "en"


class PackageKeeperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout depuis l'interface (une seule instance)."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options, target, errors = _split(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Package Keeper",
                    data={CONF_ADMIN_NOTIFY_TARGET: target},
                    options=options,
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(self.hass, {}, None), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PackageKeeperOptionsFlow()


def _git_remote_schema(options: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_GIT_URL, default=options.get(CONF_GIT_URL, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(
                CONF_GIT_BRANCH, default=options.get(CONF_GIT_BRANCH, DEFAULT_GIT_BRANCH)
            ): TextSelector(),
            vol.Required(
                CONF_GIT_USERNAME, default=options.get(CONF_GIT_USERNAME, DEFAULT_GIT_USERNAME)
            ): TextSelector(),
            # Vide = garder le jeton déjà enregistré ; jamais réaffiché
            vol.Optional(CONF_GIT_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


class PackageKeeperOptionsFlow(OptionsFlow):
    """Menu des réglages ; un changement recharge l'entrée (la synchronisation Git repart).

    Un menu plutôt qu'un choix dans le formulaire : chaque écran se termine par le
    bon bouton (« Valider » quand c'est le dernier, un écran de plus seulement pour
    le dépôt distant).
    """

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._target: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        self._options = dict(entry.options)
        self._target = normalize_target(entry.data.get(CONF_ADMIN_NOTIFY_TARGET))
        mode = entry.options.get(CONF_GIT_MODE, GIT_MODE_OFF)
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "git_off", "git_local", "git_remote"],
            description_placeholders={"mode": _MODE_LABELS[_lang(self.hass)][mode]},
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Téléphone admin, notifications, sauvegardes."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options, target, errors = _split(user_input)
            if not errors:
                self._options |= options
                self._target = target
                return self._finish(token=None)
        return self.async_show_form(
            step_id="general",
            data_schema=_schema(self.hass, self._options, self._target),
            errors=errors,
        )

    async def async_step_git_off(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self._set_mode(GIT_MODE_OFF)

    async def async_step_git_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not await self.hass.async_add_executor_job(git_available):
            return self.async_abort(reason="git_missing")
        return self._set_mode(GIT_MODE_LOCAL)

    async def async_step_git_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not await self.hass.async_add_executor_job(git_available):
            return self.async_abort(reason="git_missing")
        return await self.async_step_git()

    def _set_mode(self, mode: str) -> ConfigFlowResult:
        """Désactivé ou local : plus de dépôt distant ni de jeton gardés."""
        self._options[CONF_GIT_MODE] = mode
        for key in (CONF_GIT_URL, CONF_GIT_BRANCH, CONF_GIT_USERNAME):
            self._options.pop(key, None)
        return self._finish(token="")

    async def async_step_git(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Dépôt distant : adresse, branche, identifiant, jeton ; refus ferme d'un dépôt public."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            token = (user_input.get(CONF_GIT_TOKEN) or "").strip() or entry.data.get(
                CONF_GIT_TOKEN, ""
            )
            try:
                url = validate_remote(user_input[CONF_GIT_URL])
                branch = validate_branch(user_input[CONF_GIT_BRANCH])
                username = (user_input.get(CONF_GIT_USERNAME) or "").strip()
                if url.startswith("https://"):
                    if not token:
                        raise GitError("token_required")
                    visibility = await async_visibility(self.hass, url, username, token)
                    if visibility == "public":
                        raise GitError("public_repo")
                    if visibility == "unknown":
                        raise GitError("visibility_unknown")
            except GitError as err:
                errors["base"] = err.code
            else:
                self._options |= {
                    CONF_GIT_MODE: GIT_MODE_REMOTE,
                    CONF_GIT_URL: url,
                    CONF_GIT_BRANCH: branch,
                    CONF_GIT_USERNAME: username or DEFAULT_GIT_USERNAME,
                }
                return self._finish(token=token)
        return self.async_show_form(
            step_id="git",
            data_schema=_git_remote_schema(dict(user_input or self._options or entry.options)),
            errors=errors,
            description_placeholders={
                "example": "https://github.com/ACCOUNT/REPOSITORY",
                "local": "file:///share/package_keeper.git",
            },
        )

    def _finish(self, token: str | None) -> ConfigFlowResult:
        """token None = inchangé ; "" = effacé (Git désactivé ou local)."""
        self._options.setdefault(CONF_GIT_MODE, GIT_MODE_OFF)
        data = {**self.config_entry.data, CONF_ADMIN_NOTIFY_TARGET: self._target}
        if token is not None:
            data[CONF_GIT_TOKEN] = token
            if not token:
                data.pop(CONF_GIT_TOKEN)
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        return self.async_create_entry(data=self._options)
