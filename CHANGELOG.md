# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions selon [SemVer](https://semver.org/lang/fr/).

## [0.3.1] - 2026-11-21

### Corrigé
- **Panneau : plus besoin de redescendre en bas d'un long package.**
  - Les boutons (Vérifier, Enregistrer, Historique, Supprimer) et les résultats sont maintenant dans une barre collante, au-dessus de l'éditeur. Elle reste visible quand on fait défiler.
  - Un clic ne ramène plus en haut : la position de défilement est conservée.

## [0.3.0] - 2026-11-21

Tirée du premier test réel, sur le package `system_complet_tout_en_un` de Mathieu.

### Ajouté
- **Rechargement ciblé.** Seuls les domaines réellement modifiés (ajoutés, changés ou retirés) sont proposés au rechargement ou au redémarrage. Les commentaires et la mise en forme ne comptent pas.
  - Retirer une automatisation propose seulement `automation.reload`, au lieu des trois domaines du package.
  - Changer une consigne `input_number` dans un package qui contient aussi un `climate_template` propose `input_number.reload` au lieu d'un redémarrage.
  - Une plateforme retirée (par exemple `derivative`) est rechargée pour que ses entités disparaissent.
- **Entités retirées.** Le panneau dit, dès la vérification, quelles entités ne seront plus fournies. Après une suppression, il liste toutes celles du package.
- **Entités orphelines.** Après « Recharger maintenant », les entités retirées que Home Assistant garde marquées « non fournies » (`restored: true`) sont signalées, avec un lien vers *Paramètres → Entités*. Package Keeper ne les supprime pas lui-même.
- **API.** `package_keeper/reload` accepte `entities` et renvoie `orphans`. `save`, `delete` et `restore` renvoient `removed`.

## [0.2.0] - 2026-11-20

Testée sur 41 packages réels. Les quatre erreurs que le contrôle de configuration de Home Assistant laissait passer sont maintenant bloquées, ou signalées clairement pour la dernière.

### Ajouté
- **Contrôles faits avant toute écriture.** En cas d'erreur, le panneau affiche « rien n'a été écrit ». Sans ces contrôles, ces erreurs ne se voient qu'au démarrage ou dans les journaux.
  - **Templates Jinja** : ils sont compilés avec le moteur de Home Assistant, et le panneau indique le chemin de la clé fautive.
  - **Automatisations et scripts** : ils sont validés avec les fonctions de chargement de Home Assistant (déclencheur, condition ou action mal écrits).
  - **`unique_id` et id d'automatisation déjà utilisés par un autre package** : le contrôle compare au même domaine et à la même plateforme, et indique quel package les utilise déjà.
- **Avant une suppression**, le panneau liste les autres packages qui citent les entités créées par le package (API `package_keeper/dependents`) et demande une confirmation explicite.
- **Liste utilisable avec une centaine de packages** :
  - recherche par nom ou par description pendant la frappe, avec le compteur « x / y » ;
  - regroupement par sous-dossier ;
  - menu déroulant compact sur écran étroit.
- **L'avis d'Entity Inventory** (entités disparues, actions inconnues) s'affiche en tête du résultat, en orange. Il reste indicatif.

### Corrigé
- **Mode `include_dir_merge_named`** : le plan d'application et les contrôles portent sur le contenu des packages, et non plus sur leurs noms.

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
