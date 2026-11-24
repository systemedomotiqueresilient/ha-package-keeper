# Feuille de route

## Fait
- **0.4.0** : renommer un package (historique inclus, contrôle et retour arrière), refus des noms de package en conflit et du nom `secrets`.
- **0.1.0** : panneau réservé aux administrateurs, enregistrement contrôlé avec retour arrière automatique, historique et restauration, suppression restaurable, avis d'Entity Inventory, téléphone admin.
- **0.1.1** : l'avis d'Entity Inventory ne s'affiche plus pour un package qui ne cite aucune entité.
- **0.3.1** : boutons et résultats dans une barre collante au-dessus de l'éditeur, position de défilement conservée.
- **0.3.0** : rechargement ciblé sur les domaines modifiés, entités retirées annoncées, entités orphelines signalées après rechargement.
- **0.2.0** :
  - templates, automatisations, scripts et `unique_id` en double contrôlés avant l'écriture ;
  - liste des packages qui en dépendent, affichée avant une suppression ;
  - recherche dans la liste et menu compact.

## Prévu : 0.5.0, synchronisation Git (décisions de Mathieu du 2026-11-24)
- **Git du système** (présent dans l'image officielle de Home Assistant), aucune dépendance Python. Indisponible avec un message clair si `git` est absent (installation Core).
- **Dépôt miroir** dans `/config/.package_keeper/git` : le dossier packages reste propre ; Package Keeper n'écrit toujours que dans le dossier des packages et dans `/config/.package_keeper`.
- **Modes** : désactivé (défaut), local seul, ou local + distant en HTTPS avec jeton (GitHub, Gitea, Forgejo, GitLab, partage local `file://`…). SSH plus tard si besoin.
- **Commit après acceptation définitive** (après le contrôle de configuration ; jamais pour une modification annulée), aussi pour suppression, restauration et renommage (`git mv`). Modifications faites hors Package Keeper commitées à part. Envoi en tâche de fond, file d'attente, nouvel essai plus tard en cas d'échec.
- **Premier branchement** : dépôt distant vide → premier commit de tous les packages ; contenu identique → reprise de l'historique ; dépôt non vide et différent → pause, notification au téléphone admin et réparation HA.
- **Dépôt public : refus ferme**, sans option pour le lever (vérification par l'API GitHub, Gitea et Forgejo). Un package peut contenir un identifiant ou un mot de passe écrit en clair par une IA qui n'aurait pas respecté la règle des `!secret`.
- **Seuls les `.yaml` du dossier packages** sont synchronisés ; jeton jamais dans les journaux, les erreurs ni la ligne de commande ; capteur « Synchronisation Git » ; notification une seule fois par type de panne. Mise en garde : ne pas pointer l'application *Git pull* sur le même dépôt.

## Pistes
- **Actions inconnues** : vérifier, sans bloquer, que les actions appelées existent. Il faut tenir compte de celles que le package crée lui-même, comme ses scripts.
- **Comparer deux versions** : afficher les différences avant de restaurer une sauvegarde ou d'enregistrer.
- **Détecter les packages cassés** : signaler dans la liste ceux qui citent des entités qui n'existent plus, comme le fait la section `packages` d'Entity Inventory.
- **Mode `include_dir_merge_named`** : vérifier que le fichier commence bien par le nom du package.
- **Deferred Restart** : proposer un redémarrage différé quand un package l'exige, si l'intégration est installée.
- **Soumission à hacs/default** quand la version sera stabilisée. Mathieu soumet la PR depuis son compte.
