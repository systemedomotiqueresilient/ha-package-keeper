// Package Keeper : panneau latéral (administrateurs uniquement).
// JavaScript sans dépendance ni compilation. Tout texte venant d'un fichier est
// inséré avec textContent, jamais en HTML.

// Doit être identique à VERSION (const.py) : un test le vérifie
const PANEL_VERSION = "0.5.1";

const TEXTS = {
  fr: {
    title: "Package Keeper",
    intro: "Collez le package proposé par l'IA, vérifiez-le, puis enregistrez-le. En cas d'erreur de configuration, l'ancienne version est remise automatiquement.",
    packages: "Packages",
    newPackage: "Nouveau package",
    deleted: "Supprimés (restaurables)",
    none: "Aucun package pour l'instant.",
    name: "Nom du fichier (lettres minuscules, chiffres, _)",
    namePlaceholder: "ex. salon_derivees (la pièce, puis la fonction)",
    check: "Vérifier",
    save: "Enregistrer",
    history: "Historique",
    del: "Supprimer",
    rename: "Renommer",
    renamePrompt: "Nouveau nom pour « {name} » (lettres minuscules, chiffres, _ ; sous-dossier possible avec /). Les entités ne changent pas.",
    close: "Fermer",
    view: "Voir",
    restore: "Restaurer",
    reload: "Recharger maintenant",
    confirmDelete: "Supprimer « {name} » ? Une sauvegarde est conservée : vous pourrez le restaurer.",
    confirmDeleteUsed: "Attention : d'autres packages utilisent des entités créées par « {name} » :\n\n{list}\n\nIls ne fonctionneront plus correctement. Supprimer quand même ? (Une sauvegarde est conservée.)",
    search: "Rechercher (nom ou description)",
    count: "{shown} / {total}",
    noMatch: "Aucun package ne correspond.",
    choose: "Choisir un package…",
    rootFolder: "Dossier principal",
    confirmRestore: "Remplacer « {name} » par la version du {date} ?",
    checked: "Vérification réussie : le package est lisible. Rien n'a encore été enregistré.",
    saved: "Package « {name} » enregistré. La configuration est valide.",
    restored: "Package « {name} » restauré. La configuration est valide.",
    deletedOk: "Package « {name} » supprimé. Une sauvegarde est conservée.",
    renamedOk: "Package « {old} » renommé en « {name} », avec son historique. Les entités sont inchangées : rien à recharger.",
    rolledBack: "Modification annulée : la configuration ne passait plus le contrôle de Home Assistant. L'ancienne version a été remise.",
    reloadHint: "À recharger pour prendre effet :",
    restartHint: "Redémarrage de Home Assistant nécessaire pour : {list}. Paramètres → Système → Redémarrer (ou Deferred Restart si vous l'utilisez).",
    reloaded: "Rechargé : {list}.",
    removedCheck: "Si vous enregistrez, ces entités ne seront plus fournies : {list}",
    removedDone: "Ces entités ne sont plus fournies par le package : {list}",
    orphans: "Toujours présentes dans Home Assistant, marquées « non fournies » : {list}. Vous pouvez les supprimer :",
    orphansLink: "Paramètres → Entités",
    advice: "À vérifier avant d'aller plus loin — avis d'Entity Inventory (une entité créée par ce package lui-même n'existe pas encore et peut être signalée à tort)",
    adviceErrors: "Erreurs probables",
    adviceWarnings: "Avertissements",
    backups: "Versions sauvegardées de « {name} »",
    noBackup: "Aucune sauvegarde.",
    unsaved: "Modifications non enregistrées : les abandonner ?",
    outdated: "Package Keeper a été mis à jour ({old} → {new}) : rechargez la page pour utiliser la nouvelle version du panneau.",
    reloadPage: "Recharger la page",
    disabledTitle: "Les packages ne sont pas activés",
    disabledText: "Package Keeper ne modifie jamais configuration.yaml. Ajoutez vous-même ces lignes au début de /config/configuration.yaml, puis redémarrez Home Assistant :",
    disabledHow: "Pour éditer configuration.yaml : installez l'application complémentaire Samba share (Paramètres → Modules complémentaires) si ce n'est pas déjà fait, ouvrez le partage « config » depuis votre ordinateur, puis modifiez le fichier avec un éditeur de texte comme Notepad++ (en UTF-8, sans tabulations). Faites une sauvegarde avant.",
    mergeMode: "Mode « include_dir_merge_named » : chaque fichier doit commencer par le nom du package, puis son contenu en retrait.",
    folder: "Dossier : {dir}",
    git: { ok: "Git : à jour", pending: "Git : {n} en attente", paused: "Git : en pause", error: "Git : erreur", unavailable: "Git : absent" },
    gitHint: "Synchronisation Git, détail dans le capteur « Synchronisation Git » et dans Paramètres → Réparations.",
    errors: {
      invalid_name: "Nom invalide : lettres minuscules, chiffres et _ uniquement (sous-dossier possible avec /).",
      symlink: "Ce chemin passe par un lien symbolique : refusé.",
      empty: "Le package est vide.",
      too_large: "Le package est trop volumineux (256 Ko au maximum).",
      yaml_error: "YAML illisible.",
      include_outside: "Un !include pointe hors de /config : refusé.",
      not_found: "Introuvable.",
      same_name: "C'est déjà le nom de ce package.",
      already_exists: "Un package porte déjà ce nom.",
      name_conflict: "Home Assistant nomme un package d'après son fichier, sans le dossier : ce nom est déjà pris par un autre package, les deux s'écraseraient.",
      packages_disabled: "Les packages ne sont pas activés dans configuration.yaml.",
      config_invalid: "La configuration de Home Assistant ne passait plus le contrôle.",
      invalid_content: "Le package contient des erreurs que Home Assistant ne signalerait qu'au démarrage. Rien n'a été écrit.",
      unknown: "Erreur inattendue.",
    },
  },
  en: {
    title: "Package Keeper",
    intro: "Paste the package proposed by the AI, check it, then save it. If the configuration breaks, the previous version is put back automatically.",
    packages: "Packages",
    newPackage: "New package",
    deleted: "Deleted (restorable)",
    none: "No package yet.",
    name: "File name (lowercase letters, digits, _)",
    namePlaceholder: "e.g. living_room_derivatives (area first, then purpose)",
    check: "Check",
    save: "Save",
    history: "History",
    del: "Delete",
    rename: "Rename",
    renamePrompt: "New name for “{name}” (lowercase letters, digits, _; subfolder allowed with /). Entities do not change.",
    close: "Close",
    view: "View",
    restore: "Restore",
    reload: "Reload now",
    confirmDelete: "Delete “{name}”? A backup is kept: you will be able to restore it.",
    confirmDeleteUsed: "Warning: other packages use entities created by “{name}”:\n\n{list}\n\nThey will no longer work properly. Delete anyway? (A backup is kept.)",
    search: "Search (name or description)",
    count: "{shown} / {total}",
    noMatch: "No package matches.",
    choose: "Choose a package…",
    rootFolder: "Main folder",
    confirmRestore: "Replace “{name}” with the version from {date}?",
    checked: "Check passed: the package is readable. Nothing has been saved yet.",
    saved: "Package “{name}” saved. The configuration is valid.",
    restored: "Package “{name}” restored. The configuration is valid.",
    deletedOk: "Package “{name}” deleted. A backup is kept.",
    renamedOk: "Package “{old}” renamed to “{name}”, with its history. Entities are unchanged: nothing to reload.",
    rolledBack: "Change cancelled: the configuration no longer passed Home Assistant's check. The previous version was put back.",
    reloadHint: "Reload to apply:",
    restartHint: "Home Assistant restart required for: {list}. Settings → System → Restart (or Deferred Restart if you use it).",
    reloaded: "Reloaded: {list}.",
    removedCheck: "If you save, these entities will no longer be provided: {list}",
    removedDone: "These entities are no longer provided by the package: {list}",
    orphans: "Still present in Home Assistant, marked “not provided”: {list}. You can remove them:",
    orphansLink: "Settings → Entities",
    advice: "Check before going further — Entity Inventory advice (an entity created by this package itself does not exist yet and may be wrongly reported)",
    adviceErrors: "Likely errors",
    adviceWarnings: "Warnings",
    backups: "Saved versions of “{name}”",
    noBackup: "No backup.",
    unsaved: "Unsaved changes: discard them?",
    outdated: "Package Keeper was updated ({old} → {new}): reload the page to use the new version of the panel.",
    reloadPage: "Reload the page",
    disabledTitle: "Packages are not enabled",
    disabledText: "Package Keeper never modifies configuration.yaml. Add these lines yourself at the top of /config/configuration.yaml, then restart Home Assistant:",
    disabledHow: "To edit configuration.yaml: install the Samba share add-on (Settings → Add-ons) if not done yet, open the “config” share from your computer, then edit the file with a text editor such as Notepad++ (UTF-8, no tabs). Make a backup first.",
    mergeMode: "“include_dir_merge_named” mode: each file must start with the package name, followed by its indented content.",
    folder: "Folder: {dir}",
    git: { ok: "Git: up to date", pending: "Git: {n} waiting", paused: "Git: paused", error: "Git: error", unavailable: "Git: missing" },
    gitHint: "Git synchronisation, details in the “Git synchronisation” sensor and in Settings → Repairs.",
    errors: {
      invalid_name: "Invalid name: lowercase letters, digits and _ only (subfolder allowed with /).",
      symlink: "This path goes through a symbolic link: refused.",
      empty: "The package is empty.",
      too_large: "The package is too large (256 KB maximum).",
      yaml_error: "Unreadable YAML.",
      include_outside: "An !include points outside /config: refused.",
      not_found: "Not found.",
      same_name: "This is already the package's name.",
      already_exists: "A package already has this name.",
      name_conflict: "Home Assistant names a package after its file, without the folder: this name is already used by another package, one would overwrite the other.",
      packages_disabled: "Packages are not enabled in configuration.yaml.",
      config_invalid: "Home Assistant's configuration no longer passed the check.",
      invalid_content: "The package contains errors Home Assistant would only report at startup. Nothing was written.",
      unknown: "Unexpected error.",
    },
  },
};

const PACKAGES_SNIPPET = "homeassistant:\n  packages: !include_dir_named packages\n";

const STYLE = `
  :host { display: block; height: 100%; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, sans-serif); }
  .top { display: flex; align-items: center; gap: 12px; height: var(--header-height, 56px); padding: 0 16px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, white); font-size: 20px; }
  .wrap { display: grid; grid-template-columns: minmax(220px, 300px) 1fr; gap: 16px; padding: 16px; box-sizing: border-box; height: calc(100% - var(--header-height, 56px)); }
  @media (max-width: 800px) { .wrap { grid-template-columns: 1fr; height: auto; } }
  .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); padding: 16px; overflow: auto; }
  h2 { font-size: 16px; margin: 0 0 8px; }
  .muted { color: var(--secondary-text-color); font-size: 13px; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { padding: 8px; border-radius: 8px; cursor: pointer; }
  li:hover, li.active { background: var(--secondary-background-color); }
  li .n { font-family: var(--code-font-family, monospace); font-size: 14px; }
  li .d { font-size: 12px; color: var(--secondary-text-color); }
  button { font: inherit; border: none; border-radius: 8px; padding: 8px 14px; cursor: pointer; background: var(--primary-color); color: var(--text-primary-color, white); }
  button.flat { background: transparent; color: var(--primary-color); border: 1px solid var(--divider-color); }
  button.danger { background: var(--error-color); }
  button:disabled { opacity: .5; cursor: default; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
  input[type=text], input[type=search] { font: inherit; width: 100%; box-sizing: border-box; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font-family: var(--code-font-family, monospace); }
  textarea { width: 100%; min-height: 420px; box-sizing: border-box; font-family: var(--code-font-family, monospace); font-size: 13px; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  .editor { margin-top: 8px; min-height: 420px; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; }
  .msg { padding: 10px 12px; border-radius: 8px; margin: 8px 0; white-space: pre-wrap; }
  .ok { background: rgba(67,160,71,.15); }
  .err { background: rgba(219,68,55,.15); }
  .info { background: var(--secondary-background-color); }
  .warn { background: rgba(255,152,0,.18); border-left: 4px solid var(--warning-color, #ff9800); }
  .search { margin-bottom: 4px; }
  .top .version { font-size: 14px; opacity: .7; }
  .outdated { margin: 12px 16px 0; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .top .git { font-size: 13px; padding: 2px 8px; border-radius: 10px; background: rgba(255,255,255,.18); }
  .top .git.error, .top .git.paused { background: var(--error-color, #db4437); }
  .toolbar { position: sticky; top: -16px; z-index: 2; background: var(--card-background-color); margin: 0 -16px; padding: 4px 16px 8px; border-bottom: 1px solid var(--divider-color); }
  .toolbar .bar { margin: 8px 0 4px; }
  .results { max-height: 40vh; overflow: auto; }
  .folder { font-size: 12px; font-weight: 500; color: var(--secondary-text-color); margin: 10px 0 2px; text-transform: uppercase; }
  select { font: inherit; width: 100%; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  pre { white-space: pre-wrap; font-family: var(--code-font-family, monospace); font-size: 12px; margin: 6px 0 0; }
  .dialog { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 10; }
  .dialog .card { width: min(700px, 92vw); max-height: 80vh; }
`;

class PackageKeeperPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = { overview: null, current: null, isNew: false, newName: "", text: "", original: "", result: null, busy: false, filter: "" };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._editor && this._editor.tagName === "HA-CODE-EDITOR") this._editor.hass = hass;
    if (first) this._init();
  }

  set narrow(value) {
    const changed = this._narrow !== value;
    this._narrow = value;
    if (changed && this._root) this._render();
  }
  set panel(_value) {}

  get t() {
    const lang = (this._hass?.language || "en").startsWith("fr") ? "fr" : "en";
    return TEXTS[lang];
  }

  _fmt(text, values = {}) {
    return text.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? "");
  }

  _el(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "onclick") el.addEventListener("click", value);
      else if (key === "text") el.textContent = value;
      else if (value === true) el.setAttribute(key, "");
      else if (value !== false && value != null) el.setAttribute(key, value);
    }
    for (const child of children) if (child) el.append(child);
    return el;
  }

  async _ws(type, data = {}) {
    return this._hass.callWS({ type: `package_keeper/${type}`, ...data });
  }

  async _init() {
    this.shadowRoot.innerHTML = "";
    this.shadowRoot.append(this._el("style", { text: STYLE }));
    this._root = this._el("div");
    this.shadowRoot.append(this._root);
    // Une mise à jour s'accompagne d'un redémarrage de HA : à la reconnexion,
    // et quand l'onglet redevient visible, on revérifie la version.
    this._hass.connection?.addEventListener?.("ready", () => this._refresh());
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && this.isConnected) this._refresh();
    });
    await this._refresh();
  }

  async _refresh() {
    try {
      this._state.overview = await this._ws("overview");
      this._checkVersion(this._state.overview.version);
    } catch (err) {
      this._state.result = { ok: false, error: "unknown", detail: err.message };
    }
    this._render();
  }

  // Après une mise à jour, le navigateur garde l'ancien panneau en mémoire tant
  // que la page n'est pas rechargée. Sans modification en cours, on recharge une
  // fois tout seul ; sinon (ou si le cache résiste), on affiche un bandeau.
  _checkVersion(serverVersion) {
    if (!serverVersion || serverVersion === PANEL_VERSION) {
      this._state.outdated = null;
      return;
    }
    const key = `package-keeper-reloaded-${serverVersion}`;
    let alreadyTried = true;
    try {
      alreadyTried = sessionStorage.getItem(key) === "1";
      if (!alreadyTried && !this._dirty()) sessionStorage.setItem(key, "1");
    } catch (_err) {
      alreadyTried = true; // stockage indisponible : pas de rechargement automatique
    }
    if (!alreadyTried && !this._dirty()) {
      window.location.reload();
      return;
    }
    this._state.outdated = serverVersion;
  }

  _dirty() {
    return this._state.text !== this._state.original;
  }

  async _open(name) {
    if (this._dirty() && !confirm(this.t.unsaved)) return;
    const { text } = await this._ws("read", { name });
    Object.assign(this._state, { current: name, isNew: false, text, original: text, result: null });
    this._render();
  }

  _new() {
    if (this._dirty() && !confirm(this.t.unsaved)) return;
    Object.assign(this._state, { current: "", isNew: true, newName: "", text: "", original: "", result: null });
    this._render();
  }

  async _run(kind) {
    const s = this._state;
    const name = s.isNew ? s.newName.trim() : s.current;
    s.busy = true;
    this._render();
    try {
      if (kind === "delete") {
        const { dependents } = await this._ws("dependents", { name });
        const used = Object.entries(dependents || {}).map(([pkg, ids]) => `• ${pkg} : ${ids.join(", ")}`);
        const question = used.length
          ? this._fmt(this.t.confirmDeleteUsed, { name, list: used.join("\n") })
          : this._fmt(this.t.confirmDelete, { name });
        if (!confirm(question)) return;
        s.result = await this._ws("delete", { name, confirm: true });
        if (s.result.ok) Object.assign(s, { current: null, isNew: false, text: "", original: "" });
      } else if (kind === "rename") {
        const answer = prompt(this._fmt(this.t.renamePrompt, { name }), name);
        if (answer === null || !answer.trim() || answer.trim() === name) return;
        s.result = await this._ws("rename", { name, new_name: answer.trim() });
        if (s.result.ok) s.current = s.result.name; // modifications non enregistrées conservées
      } else {
        s.result = await this._ws("save", { name, text: s.text, dry_run: kind === "check" });
        if (s.result.ok && kind === "save") Object.assign(s, { current: name, isNew: false, original: s.text });
      }
      await this._refresh();
    } catch (err) {
      s.result = { ok: false, error: err.code || "unknown", detail: err.message };
    } finally {
      s.busy = false;
      this._render();
    }
  }

  async _reload(services) {
    try {
      const entities = this._state.result?.removed || [];
      const { reloaded, orphans } = await this._ws("reload", { services, entities });
      this._state.result = { ...this._state.result, reload: [], reloadedNow: reloaded, orphans };
    } catch (err) {
      this._state.result = { ok: false, error: "unknown", detail: err.message };
    }
    this._render();
  }

  async _history(name) {
    const { backups } = await this._ws("backups", { name });
    const t = this.t;
    const box = this._el("div", { class: "card" }, this._el("h2", { text: this._fmt(t.backups, { name }) }));
    const preview = this._el("pre");
    if (!backups.length) box.append(this._el("p", { class: "muted", text: t.noBackup }));
    const list = this._el("ul");
    for (const b of backups) {
      const date = new Date(b.date).toLocaleString(this._hass.language);
      const row = this._el("li", {},
        this._el("div", { class: "n", text: `${date} · ${b.reason}` }),
        this._el("div", { class: "bar" },
          this._el("button", { class: "flat", text: t.view, onclick: async () => {
            preview.textContent = (await this._ws("read_backup", { name, backup: b.id })).text;
          } }),
          this._el("button", { text: t.restore, onclick: async () => {
            if (!confirm(this._fmt(t.confirmRestore, { name, date }))) return;
            dialog.remove();
            this._state.result = await this._ws("restore", { name, backup: b.id });
            if (this._state.result.ok) {
              const { text } = await this._ws("read", { name });
              Object.assign(this._state, { current: name, isNew: false, text, original: text });
            }
            await this._refresh();
          } }),
        ),
      );
      list.append(row);
    }
    box.append(list, preview, this._el("div", { class: "bar" },
      this._el("button", { class: "flat", text: t.close, onclick: () => dialog.remove() })));
    const dialog = this._el("div", { class: "dialog" }, box);
    dialog.addEventListener("click", (ev) => { if (ev.target === dialog) dialog.remove(); });
    this.shadowRoot.append(dialog);
  }

  _makeEditor() {
    const s = this._state;
    const onChange = (value) => {
      s.text = value;
    };
    if (customElements.get("ha-code-editor")) {
      const editor = document.createElement("ha-code-editor");
      editor.mode = "yaml";
      editor.hass = this._hass;
      editor.value = s.text;
      editor.addEventListener("value-changed", (ev) => onChange(ev.detail.value));
      this._editor = editor;
      return this._el("div", { class: "editor" }, editor);
    }
    const area = this._el("textarea", { spellcheck: "false" });
    area.value = s.text;
    area.addEventListener("input", () => onChange(area.value));
    this._editor = area;
    return area;
  }

  _renderResult() {
    const r = this._state.result;
    if (!r) return null;
    const t = this.t;
    const box = this._el("div");
    if (r.advice && (r.advice.errors || r.advice.warnings)) {
      const adv = this._el("div", { class: "msg warn", text: t.advice });
      for (const [key, label] of [["errors", t.adviceErrors], ["warnings", t.adviceWarnings]]) {
        if (r.advice[key]?.length) adv.append(this._el("pre", { text: `${label} :\n- ${r.advice[key].join("\n- ")}` }));
      }
      box.append(adv);
    }
    if (r.ok) {
      const key = { checked: "checked", saved: "saved", restored: "restored", deleted: "deletedOk", renamed: "renamedOk" }[r.action] || "saved";
      box.append(this._el("div", { class: "msg ok", text: this._fmt(t[key], { name: r.name, old: r.renamed_from }) }));
    } else {
      const text = r.rolled_back ? t.rolledBack : t.errors[r.error] || t.errors.unknown;
      const msg = this._el("div", { class: "msg err", text });
      if (r.detail) msg.append(this._el("pre", { text: r.detail }));
      box.append(msg);
    }
    if (r.ok && r.removed?.length) {
      const key = r.action === "checked" ? "removedCheck" : "removedDone";
      box.append(this._el("div", { class: "msg info", text: this._fmt(t[key], { list: r.removed.join(", ") }) }));
    }
    if (r.orphans?.length) {
      box.append(this._el("div", { class: "msg warn" },
        this._el("span", { text: `${this._fmt(t.orphans, { list: r.orphans.join(", ") })} ` }),
        this._el("a", { href: "/config/entities", text: t.orphansLink })));
    }
    if (r.ok && r.action !== "checked") {
      if (r.reload?.length) {
        box.append(this._el("div", { class: "msg info" },
          this._el("span", { text: `${t.reloadHint} ${r.reload.join(", ")} ` }),
          this._el("button", { class: "flat", text: t.reload, onclick: () => this._reload(r.reload) })));
      }
      if (r.reloadedNow?.length) box.append(this._el("div", { class: "msg ok", text: this._fmt(t.reloaded, { list: r.reloadedNow.join(", ") }) }));
      if (r.restart?.length) box.append(this._el("div", { class: "msg info", text: this._fmt(t.restartHint, { list: r.restart.join(", ") }) }));
    }
    return box;
  }

  _matches() {
    const all = this._state.overview?.packages || [];
    const words = this._state.filter.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return all;
    return all.filter((p) => {
      const hay = `${p.name} ${p.description || ""}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }

  _renderList() {
    const t = this.t;
    const s = this._state;
    const all = s.overview?.packages || [];
    const box = this._el("div");
    if (!all.length) {
      if (s.overview) box.append(this._el("p", { class: "muted", text: t.none }));
      return box;
    }
    const search = this._el("input", { type: "search", class: "search", placeholder: t.search, "aria-label": t.search });
    search.value = s.filter;
    const counter = this._el("div", { class: "muted" });
    const holder = this._el("div");
    const fill = () => {
      const shown = this._matches();
      counter.textContent = this._fmt(t.count, { shown: shown.length, total: all.length });
      holder.innerHTML = "";
      if (!shown.length) {
        holder.append(this._el("p", { class: "muted", text: t.noMatch }));
        return;
      }
      if (this._narrow) {
        const select = this._el("select", { "aria-label": t.choose });
        select.append(this._el("option", { value: "", text: t.choose }));
        for (const p of shown) {
          const option = this._el("option", { value: p.name, text: p.description ? `${p.name} — ${p.description}` : p.name });
          if (p.name === s.current) option.selected = true;
          select.append(option);
        }
        select.addEventListener("change", () => select.value && this._open(select.value));
        holder.append(select);
        return;
      }
      const folders = new Map();
      for (const p of shown) {
        const folder = p.name.includes("/") ? p.name.slice(0, p.name.lastIndexOf("/")) : "";
        if (!folders.has(folder)) folders.set(folder, []);
        folders.get(folder).push(p);
      }
      const several = folders.size > 1 || !folders.has("");
      for (const [folder, items] of [...folders].sort(([a], [b]) => a.localeCompare(b))) {
        if (several) holder.append(this._el("div", { class: "folder", text: folder || t.rootFolder }));
        const list = this._el("ul");
        for (const p of items) {
          list.append(this._el("li", { class: p.name === s.current ? "active" : "", onclick: () => this._open(p.name) },
            this._el("div", { class: "n", text: p.name }),
            p.description ? this._el("div", { class: "d", text: p.description }) : null));
        }
        holder.append(list);
      }
    };
    search.addEventListener("input", () => {
      s.filter = search.value;
      fill();
    });
    box.append(search, counter, holder);
    fill();
    return box;
  }

  _gitChip() {
    const git = this._state.overview?.git;
    if (!git || git.mode === "off" || !this.t.git[git.status]) return null;
    const text = this._fmt(this.t.git[git.status], { n: git.pending || 0 });
    return this._el("span", { class: `git ${git.status}`, title: this.t.gitHint, text });
  }

  _render() {
    if (!this._root) return;
    const t = this.t;
    const s = this._state;
    const o = s.overview;
    // Un nouveau rendu ne doit pas ramener l'utilisateur en haut de la page
    const scrolls = [...this._root.querySelectorAll(".card")].map((card) => card.scrollTop);
    const pageScroll = this.scrollTop;
    queueMicrotask(() => {
      [...this._root.querySelectorAll(".card")].forEach((card, index) => {
        if (scrolls[index]) card.scrollTop = scrolls[index];
      });
      if (pageScroll) this.scrollTop = pageScroll;
    });
    this._root.innerHTML = "";
    this._root.append(this._el("div", { class: "top" },
      this._el("span", { text: t.title }),
      this._el("span", { class: "version", text: `v${PANEL_VERSION}` }),
      this._gitChip()));
    if (s.outdated) {
      this._root.append(this._el("div", { class: "msg warn outdated" },
        this._el("span", { text: `${this._fmt(t.outdated, { old: PANEL_VERSION, new: s.outdated })} ` }),
        this._el("button", { text: t.reloadPage, onclick: () => window.location.reload() })));
    }
    const wrap = this._el("div", { class: "wrap" });
    this._root.append(wrap);

    if (o && !o.enabled) {
      wrap.style.gridTemplateColumns = "1fr";
      wrap.append(this._el("div", { class: "card" },
        this._el("h2", { text: t.disabledTitle }),
        this._el("p", { text: t.disabledText }),
        this._el("pre", { text: PACKAGES_SNIPPET }),
        this._el("p", { class: "muted", text: t.disabledHow })));
      return;
    }

    // Liste
    const side = this._el("div", { class: "card" },
      this._el("h2", { text: t.packages }),
      o ? this._el("div", { class: "muted", text: this._fmt(t.folder, { dir: o.directory }) }) : null,
      this._el("div", { class: "bar" }, this._el("button", { text: t.newPackage, onclick: () => this._new() })));
    side.append(this._renderList());
    if (o?.deleted?.length) {
      side.append(this._el("h2", { text: t.deleted }));
      const del = this._el("ul");
      for (const name of o.deleted) del.append(this._el("li", { onclick: () => this._history(name) }, this._el("div", { class: "n", text: name })));
      side.append(del);
    }
    wrap.append(side);

    // Éditeur
    const main = this._el("div", { class: "card" });
    main.append(this._el("p", { class: "muted", text: t.intro }));
    if (o?.mode === "include_dir_merge_named") main.append(this._el("div", { class: "msg info", text: t.mergeMode }));
    if (s.current !== null) {
      if (s.isNew) {
        const input = this._el("input", { type: "text", placeholder: t.namePlaceholder, "aria-label": t.name });
        input.value = s.newName;
        input.addEventListener("input", () => { s.newName = input.value; });
        main.append(this._el("div", { class: "muted", text: t.name }), input);
      } else {
        main.append(this._el("h2", { text: `${s.current}.yaml` }));
      }
      // Boutons et résultats dans une barre collante, au-dessus de l'éditeur :
      // toujours visibles, même dans un long package
      const busy = s.busy;
      const toolbar = this._el("div", { class: "toolbar" },
        this._el("div", { class: "bar" },
          this._el("button", { class: "flat", text: t.check, disabled: busy, onclick: () => this._run("check") }),
          this._el("button", { text: t.save, disabled: busy, onclick: () => this._run("save") }),
          s.isNew ? null : this._el("button", { class: "flat", text: t.history, disabled: busy, onclick: () => this._history(s.current) }),
          s.isNew ? null : this._el("button", { class: "flat", text: t.rename, disabled: busy, onclick: () => this._run("rename") }),
          s.isNew ? null : this._el("button", { class: "danger", text: t.del, disabled: busy, onclick: () => this._run("delete") })));
      const result = this._renderResult();
      if (result) toolbar.append(this._el("div", { class: "results" }, result));
      main.append(toolbar, this._makeEditor());
    } else {
      const result = this._renderResult();
      if (result) main.append(result);
    }
    wrap.append(main);
  }
}

customElements.define("package-keeper-panel", PackageKeeperPanel);
