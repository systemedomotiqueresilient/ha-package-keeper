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


def _git_mode_schema(options: dict[str, Any]) -> dict:
    return {
        vol.Required(
            CONF_GIT_MODE, default=options.get(CONF_GIT_MODE, GIT_MODE_OFF)
        ): SelectSelector(
            SelectSelectorConfig(
                options=[GIT_MODE_OFF, GIT_MODE_LOCAL, GIT_MODE_REMOTE],
                translation_key="git_mode",
                mode=SelectSelectorMode.LIST,
            )
        )
    }


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
    """Réglages ; un changement recharge l'entrée (la synchronisation Git repart)."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._target: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        target = normalize_target(entry.data.get(CONF_ADMIN_NOTIFY_TARGET))
        errors: dict[str, str] = {}
        if user_input is not None:
            options, target, errors = _split(user_input)
            mode = options.get(CONF_GIT_MODE, GIT_MODE_OFF)
            if mode != GIT_MODE_OFF and not await self.hass.async_add_executor_job(git_available):
                errors[CONF_GIT_MODE] = "git_missing"
            if not errors:
                self._options = {**entry.options, **options}
                self._target = target
                if mode == GIT_MODE_REMOTE:
                    return await self.async_step_git()
                for key in (CONF_GIT_URL, CONF_GIT_BRANCH, CONF_GIT_USERNAME):
                    self._options.pop(key, None)
                return self._finish(token=None if mode == GIT_MODE_LOCAL else "")
        schema = _schema(self.hass, dict(entry.options), target).extend(
            _git_mode_schema(dict(entry.options))
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

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
        """token None = inchangé ; "" = effacé (mode désactivé)."""
        data = {**self.config_entry.data, CONF_ADMIN_NOTIFY_TARGET: self._target}
        if token is not None:
            data[CONF_GIT_TOKEN] = token
            if not token:
                data.pop(CONF_GIT_TOKEN)
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        # La synchronisation Git repart avec les nouveaux réglages
        self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return self.async_create_entry(data=self._options)
