# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions selon [SemVer](https://semver.org/lang/fr/).

## [0.1.1] - 2026-11-20

### Corrigé
- **Plus d'« erreur probable » parasite d'Entity Inventory** pour un package qui ne cite aucune entité ni action, par exemple un simple `input_boolean`. Entity Inventory y répondait « Rien à vérifier », et le panneau l'affichait comme une erreur.

### Ajouté
- **Catégorie Marketplace** `computers_network.cloud_developer_tools` dans le manifest.

## [0.1.0] - 2026-11-20

Première version.

### Ajouté
- **Panneau latéral « Package Keeper »**, réservé aux administrateurs. Il permet de lister, créer, éditer, vérifier, enregistrer et supprimer des packages, et d'en consulter et restaurer l'historique.
- **API WebSocket `package_keeper/*`** : toutes les commandes passent par `require_admin`, et la suppression exige `confirm: true`.
- **Enregistrement sûr** :
  - le nom est vérifié (slug, sous-dossiers, aucun lien symbolique ni `..`) ;
  - la taille est limitée à 256 Ko ;
  - les `!include` hors de `/config` ou vers `.storage` sont refusés ;
  - le YAML est lu avec le chargeur de Home Assistant (`!secret` et `!include`) ;
  - l'ancienne version est sauvegardée, puis le fichier est écrit de façon atomique ;
  - le contrôle de configuration tient compte des erreurs **et** des avertissements ;
  - en cas de nouveau problème, l'ancienne version est remise automatiquement. Un problème qui existait déjà ne bloque pas.
- **Avis d'Entity Inventory** (`entity_inventory.validate`) s'il est installé. Il reste indicatif.
- **Plan d'application** : les actions de rechargement proposées (`<domaine>.reload`, `<plateforme>.reload`, `homeassistant.reload_core_config`) et les domaines qui demandent un redémarrage.
- **Sauvegardes** dans `/config/.package_keeper/backups/<package>/`, avec un nombre de versions conservées réglable. Un package supprimé reste restaurable.
- **Téléphone admin** (module commun `admin_phone.py` **1.1.0**, copié tel quel depuis `ha-sdr`, SHA-256 `32b3619e…e1f9`) :
  - capteur de diagnostic ;
  - valeur préremplie depuis les intégrations sœurs et rangée dans `entry.data` ;
  - notification à chaque modification (réglable) et à chaque retour arrière (toujours).
- **Textes en français et en anglais.** Si les packages ne sont pas activés, le panneau explique quoi ajouter à `configuration.yaml` et recommande Samba share et Notepad++. Package Keeper ne modifie jamais ce fichier.
