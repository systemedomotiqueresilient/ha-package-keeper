# Package Keeper : consignes pour les agents

Intégration Home Assistant (domaine `package_keeper`). Elle enregistre les packages YAML proposés par une IA depuis un panneau latéral réservé aux administrateurs, avec un contrôle de configuration et un retour arrière automatique. C'est le complément d'Entity Inventory, qui reste en lecture seule.

## Règles
- **On n'écrit QUE dans le dossier des packages et dans `/config/.package_keeper`** (sauvegardes, et depuis la 0.5.0 le dépôt Git miroir `git/`). Un envoi Git ne part que vers le dépôt choisi par l'occupant : HTTPS privé, ou `file://` sous `/share` ou `/media`. On ne modifie jamais `configuration.yaml` : si les packages ne sont pas activés, on explique comment faire (Samba share, puis Notepad++).
- **Toute écriture passe par `PackageManager`** : sauvegarde, écriture atomique, contrôle de configuration, puis restauration en cas de nouveau problème.
- **Toutes les commandes WebSocket portent `@websocket_api.require_admin`.** Le panneau est enregistré avec `require_admin=True`.
- **Dépôt Git public : refus ferme**, sans option (décision de Mathieu). Le jeton ne va jamais sur la ligne de commande ni dans un journal.
- **Niveaux de log** : WARNING seulement pour un vrai problème à remonter (Bug Beacon en fait une réparation) ; un comportement prévu (retour arrière, échec réseau Git) est en INFO.
- **Aucun contenu de package ni valeur de secret dans les journaux.** Le panneau insère tout texte venant d'un fichier avec `textContent`, jamais en HTML.
- **Pas de suppression définitive** : un package supprimé est déplacé dans les sauvegardes.
- **Aucune donnée personnelle dans le dépôt public**, ni dans les README, les tests ou les messages de commit. Les commits utilisent l'adresse GitHub noreply.
- **Ne jamais modifier le code de Sentinel ni de Spook.**
- **Mathieu pousse lui-même les commits** (à partir d'un patch ou d'un bundle).

## Module commun `admin_phone.py`
- **Référence** : dépôt privé `systemedomotiqueresilient/ha-sdr`. Le fichier est copié **tel quel** et n'est jamais modifié ici. Le test `test_module_copy_and_versions` vérifie son SHA-256.
- **Convention** :
  - capteur de diagnostic, unique_id `<entry_id>_admin_notify_target` ;
  - valeur rangée dans `entry.data["admin_notify_target"]` ;
  - envoi par `async_notify_admin`.
- **Synchronisation entre agents** : carnet Evernote dédié (00 : le protocole, 01 : la spécification, 02 : le journal, où l'on ajoute ses entrées à la fin).

## Versions
La version doit être identique dans `manifest.json`, `const.py` (`VERSION`), `VERSION` et `PANEL_VERSION` en tête de `frontend/package-keeper-panel.js` (sinon le panneau se croit périmé et recharge la page). Un test le vérifie. Il faut aussi tenir à jour `CHANGELOG.md` et `ROADMAP.md`.

## Vérifications
```bash
python3 -m pytest -q --cov=custom_components/package_keeper   # couverture ≥ 50 %
ruff check custom_components/
cd ../ha-core && python3 -m script.hassfest --action validate --integration-path ../ha-package-keeper/custom_components/package_keeper
node --check custom_components/package_keeper/frontend/package-keeper-panel.js
```
