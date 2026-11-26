# Package Keeper

[English](README.md) · **Français**

Enregistrez les **packages YAML proposés par une IA** sans File Editor ni SSH. Vous collez le package dans un panneau latéral, Package Keeper le vérifie, l'enregistre dans `/config/packages/` et contrôle la configuration de Home Assistant. **Si le package casse la configuration, l'ancienne version est remise automatiquement.**

C'est le complément d'[Entity Inventory](https://github.com/systemedomotiqueresilient/ha-entity-inventory) : Entity Inventory donne à l'IA la structure de votre installation, en lecture seule, et Package Keeper enregistre ce que l'IA propose. Les deux s'installent séparément.

## Ce que fait Package Keeper, et ce qu'il ne fait jamais

- Il écrit **uniquement** dans le dossier des packages et dans son dossier de sauvegardes (`/config/.package_keeper/backups`).
- Il **ne modifie jamais `configuration.yaml`**, ni aucun autre fichier.
- Il ne redémarre jamais Home Assistant tout seul.
- Le panneau et son API sont **réservés aux administrateurs**. Le contrôle est fait par le serveur, pas seulement par l'interface.
- Les `!secret` restent des références : leurs valeurs ne sont jamais affichées ni journalisées.

## Prérequis : activer les packages

Package Keeper a besoin que les packages soient activés dans `configuration.yaml`. Comme il ne modifie jamais ce fichier, c'est à vous d'ajouter ces lignes au début de `/config/configuration.yaml`, puis de redémarrer :

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Si une section `homeassistant:` existe déjà, ajoutez seulement la ligne `packages:` dedans, avec la même indentation que les autres lignes.

**Pour éditer `configuration.yaml` sans risque :**
1. **Installez l'application complémentaire Samba share**, si ce n'est pas déjà fait : *Paramètres → Modules complémentaires → Boutique*.
2. **Ouvrez le partage `config`** depuis votre ordinateur, par exemple `\\homeassistant.local\config` sous Windows.
3. **Faites une copie de `configuration.yaml`** avant toute modification.
4. **Modifiez le fichier avec un éditeur de texte** comme **Notepad++**. Enregistrez en UTF-8, et indentez avec des espaces, jamais des tabulations.
5. Dans Home Assistant, lancez **Outils de développement → YAML → Vérifier la configuration**, puis **redémarrez**.

Tant que les packages ne sont pas activés, le panneau affiche ces mêmes instructions.

## Installation

Avec HACS (dépôt personnalisé) : ajoutez `https://github.com/systemedomotiqueresilient/ha-package-keeper`, catégorie *Intégration*, installez, redémarrez, puis ajoutez l'intégration **Package Keeper**.

| Option | Défaut | Effet |
|---|---|---|
| Téléphone admin | prérempli si une autre intégration SDR en a déjà un | service `notify.mobile_app_*` ou entité `notify.*` prévenu en cas de modification |
| Prévenir à chaque modification | oui | une notification à chaque enregistrement, suppression ou restauration (un retour arrière automatique est toujours signalé) |
| Sauvegardes conservées par package | 10 | au-delà, les versions les plus anciennes sont supprimées |

## Utilisation

Le panneau **Package Keeper** apparaît dans la barre latérale, pour les administrateurs uniquement.

1. **Nouveau package** : donnez un nom de fichier (lettres minuscules, chiffres, `_`), puis collez le YAML proposé par l'IA. Suivez la convention d'Entity Inventory : **la pièce d'abord, puis la fonction** (`salon_derivees`, `appartement_temperature_moyenne`), et une première ligne de commentaire qui décrit le package.
2. **Vérifier** : le YAML est lu avec le chargeur de Home Assistant, avec les mêmes `!secret` et `!include`. Si **Entity Inventory** est installé, son action `validate` donne aussi son avis sur les entités et les actions. Cet avis est indicatif : une entité que le package crée lui-même n'existe pas encore et peut donc être signalée. À ce stade, rien n'est encore écrit.
3. **Enregistrer** : Package Keeper sauvegarde l'ancienne version, écrit le fichier de façon atomique, puis lance le contrôle de configuration, le même que le bouton *Vérifier la configuration*.
   - **Si un nouveau problème apparaît** (erreur YAML, intégration mal configurée, entité définie deux fois…), **la modification est annulée** et le problème est affiché.
   - Un problème qui existait déjà avant votre modification ne bloque pas l'enregistrement : sinon, on ne pourrait jamais réparer une configuration déjà cassée ailleurs.
   - **Avant même d'écrire**, Package Keeper contrôle ce que Home Assistant ne vérifie qu'au démarrage : les templates Jinja, les automatisations et les scripts, et les `unique_id` déjà utilisés par un autre package.
4. **Appliquer** : seuls les domaines réellement modifiés sont proposés. Par exemple, retirer une automatisation ne propose que `automation.reload`. Le panneau dit aussi quelles entités ne seront plus fournies et, après le rechargement, celles qui restent marquées « non fournies » dans *Paramètres → Entités*, où vous pouvez les supprimer.
   - pour les domaines qui se rechargent (automation, script, template, input_*…), un bouton **Recharger maintenant** suffit ;
   - pour les autres (`sensor` avec `platform: derivative`, `climate_template`…), le panneau indique qu'un **redémarrage** est nécessaire. Faites-le depuis *Paramètres → Système → Redémarrer*, ou avec Deferred Restart si vous l'utilisez.
5. **Historique** : chaque package garde ses versions précédentes, que l'on peut consulter et restaurer.
6. **Supprimer** : le fichier est déplacé dans les sauvegardes, après confirmation. Si d'autres packages utilisent les entités qu'il crée, ils sont listés avant la confirmation. Le package reste restaurable depuis la section *Supprimés* du panneau.
7. **Renommer** : déplace le package sous un nouveau nom ou dans un sous-dossier (`salon` → `rdc/salon_fenetres`), avec son historique, sans toucher à son contenu ni à ses entités : rien à recharger. Même contrôle de configuration et même retour arrière qu'un enregistrement. Un `!include` relatif qui ne pointerait plus nulle part depuis le nouveau dossier est refusé.
   - Avec `!include_dir_named`, Home Assistant nomme un package d'après son fichier **sans le dossier** : `salon/lumieres` et `cuisine/lumieres` s'écraseraient sans erreur. Package Keeper refuse donc un nom déjà porté par un autre fichier, à l'enregistrement d'un nouveau package comme au renommage.
8. **Rechercher** : le champ au-dessus de la liste filtre par nom et par description. Sur un écran étroit, la liste devient un menu déroulant.

## Synchronisation Git (0.5.0)

Désactivée par défaut, elle se règle dans les options de l'intégration. Chaque modification **acceptée** (après le contrôle de configuration) devient un commit ; une modification annulée ne l'est jamais.

- **Local** : dépôt miroir dans `/config/.package_keeper/git`, consultable par Samba. Le dossier des packages lui-même n'est jamais transformé en dépôt.
- **Distant** : envoi en plus vers un dépôt **privé** GitHub, Gitea, Forgejo ou GitLab en HTTPS, avec un jeton d'accès limité à ce dépôt (lecture et écriture du contenu), ou vers un dépôt local `file:///share/…` ou `file:///media/…` (un NAS monté, par exemple).
- **Dépôt public refusé**, sans exception : un package peut contenir un identifiant ou un mot de passe écrit en clair, par exemple par une IA qui n'aurait pas utilisé `!secret`. La visibilité est vérifiée à la configuration et avant chaque envoi ; un hébergeur dont Package Keeper ne sait pas lire la visibilité est refusé.
- **Premier branchement** : un dépôt vide reçoit l'état initial de vos packages ; un dépôt qui contient exactement vos packages est repris tel quel ; tout autre dépôt non vide met la synchronisation en pause, avec une réparation et une notification au téléphone admin.
- **Seuls les fichiers `.yaml` du dossier des packages** sont synchronisés. Jamais `secrets.yaml`.
- **Ne pointez pas l'application *Git pull* sur le même dépôt** : elle réécrirait `/config` à partir de ce que Package Keeper vient d'envoyer.
- Le capteur **Synchronisation Git** et un indicateur dans le panneau montrent l'état : à jour, commits en attente, en pause, erreur.
- Nécessite `git`, présent dans l'image officielle de Home Assistant (HAOS, Supervised, Container).

## Téléphone admin, commun aux intégrations SDR

Comme Entity Inventory, Sentinel Report, Deferred Restart et Partition Map, Package Keeper crée sa propre entité **Téléphone admin**, un capteur de diagnostic.

- **À l'installation**, le champ est prérempli avec le téléphone déjà choisi dans une autre intégration SDR. Package Keeper lit cette valeur sans jamais modifier l'autre intégration.
- **La valeur est copiée** dans Package Keeper : elle reste valable si l'autre intégration est supprimée.

## Développement

```bash
pip install -r requirements_test.txt
pytest --cov=custom_components/package_keeper
ruff check custom_components/
```

Licence MIT.
