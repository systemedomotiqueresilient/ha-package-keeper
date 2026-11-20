# Package Keeper

**English** · [Français](README.fr.md)

Save the **YAML packages proposed by an AI** without File Editor or SSH. You paste the package into a sidebar panel, and Package Keeper checks it, saves it to `/config/packages/` and runs Home Assistant's configuration check. **If the package breaks the configuration, the previous version is put back automatically.**

It complements [Entity Inventory](https://github.com/systemedomotiqueresilient/ha-entity-inventory): Entity Inventory gives the AI the structure of your installation, read-only, and Package Keeper saves what the AI proposes. They are installed separately.

## What Package Keeper does, and never does

- It writes **only** to the packages folder and to its backup folder (`/config/.package_keeper/backups`).
- It **never modifies `configuration.yaml`**, or any other file.
- It never restarts Home Assistant on its own.
- The panel and its API are **restricted to administrators**. The check is done by the server, not just by the interface.
- `!secret` tags stay references: their values are never shown or logged.

## Prerequisite: enable packages

Package Keeper needs packages to be enabled in `configuration.yaml`. Since it never modifies that file, you add these lines yourself at the top of `/config/configuration.yaml`, then restart:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

If a `homeassistant:` section already exists, only add the `packages:` line inside it, with the same indentation as the other lines.

**To edit `configuration.yaml` safely:**
1. **Install the Samba share add-on** if not done yet: *Settings → Add-ons → Add-on store*.
2. **Open the `config` share** from your computer, for example `\\homeassistant.local\config` on Windows.
3. **Make a copy of `configuration.yaml`** before any change.
4. **Edit the file with a text editor** such as **Notepad++**. Save as UTF-8, and indent with spaces, never tabs.
5. In Home Assistant, run **Developer tools → YAML → Check configuration**, then **restart**.

As long as packages are not enabled, the panel shows these same instructions.

## Installation

With HACS (custom repository): add `https://github.com/systemedomotiqueresilient/ha-package-keeper`, category *Integration*, install, restart, then add the **Package Keeper** integration.

| Option | Default | Effect |
|---|---|---|
| Admin phone | pre-filled if another SDR integration already has one | `notify.mobile_app_*` service or `notify.*` entity notified of changes |
| Notify every change | yes | a notification for each save, deletion or restore (an automatic rollback is always notified) |
| Backups kept per package | 10 | older versions are deleted beyond this number |

## Usage

The **Package Keeper** panel appears in the sidebar, for administrators only.

1. **New package**: give a file name (lowercase letters, digits, `_`), then paste the YAML proposed by the AI.
2. **Check**: the YAML is read with Home Assistant's loader, using the same `!secret` and `!include`. If **Entity Inventory** is installed, its `validate` action also gives its advice on entities and actions. That advice is indicative: an entity the package creates itself does not exist yet and may be reported. Nothing is written at this stage.
3. **Save**: Package Keeper backs up the previous version, writes the file atomically, then runs the configuration check, the same as the *Check configuration* button.
   - **If a new problem appears** (YAML error, misconfigured integration, entity defined twice…), **the change is cancelled** and the problem is shown.
   - A problem that already existed before your change does not block saving: otherwise a configuration already broken elsewhere could never be fixed.
   - **Before writing anything**, Package Keeper checks what Home Assistant only checks at startup: Jinja templates, automations and scripts, and `unique_id` values already used by another package.
4. **Apply**:
   - for domains that can be reloaded (automation, script, template, input_*…), a **Reload now** button is enough;
   - for the others (`sensor` with `platform: derivative`, `climate_template`…), the panel says a **restart** is needed. Do it from *Settings → System → Restart*, or with Deferred Restart if you use it.
5. **History**: each package keeps its previous versions, which you can view and restore.
6. **Delete**: the file is moved to the backups, after confirmation. If other packages use the entities it creates, they are listed before the confirmation. It can still be restored from the panel's *Deleted* section.
7. **Search**: the field above the list filters by name and description. On a narrow screen, the list becomes a drop-down menu.

## Admin phone, shared by the SDR integrations

Like Entity Inventory, Sentinel Report, Deferred Restart and Partition Map, Package Keeper creates its own **Admin phone** entity, a diagnostic sensor.

- **At installation**, the field is pre-filled with the phone already chosen in another SDR integration. Package Keeper reads that value without ever modifying the other integration.
- **The value is copied** into Package Keeper: it stays valid if the other integration is removed.

## Development

```bash
pip install -r requirements_test.txt
pytest --cov=custom_components/package_keeper
ruff check custom_components/
```

MIT licence.
