# Feuille de route

## Fait
- **0.5.0** : synchronisation Git (dépôt miroir, local ou distant privé, premier branchement automatique, refus ferme des dépôts publics).
- **0.4.0** : renommer un package (historique inclus, contrôle et retour arrière), refus des noms de package en conflit et du nom `secrets`.
- **0.1.0** : panneau réservé aux administrateurs, enregistrement contrôlé avec retour arrière automatique, historique et restauration, suppression restaurable, avis d'Entity Inventory, téléphone admin.
- **0.1.1** : l'avis d'Entity Inventory ne s'affiche plus pour un package qui ne cite aucune entité.
- **0.3.1** : boutons et résultats dans une barre collante au-dessus de l'éditeur, position de défilement conservée.
- **0.3.0** : rechargement ciblé sur les domaines modifiés, entités retirées annoncées, entités orphelines signalées après rechargement.
- **0.2.0** :
  - templates, automatisations, scripts et `unique_id` en double contrôlés avant l'écriture ;
  - liste des packages qui en dépendent, affichée avant une suppression ;
  - recherche dans la liste et menu compact.

## Pistes
- **Git en SSH** (clé et hôtes connus), si le HTTPS avec jeton ne suffit pas.
- **Historique Git dans le panneau** : afficher les derniers commits d'un package à côté de ses sauvegardes.
- **Actions inconnues** : vérifier, sans bloquer, que les actions appelées existent. Il faut tenir compte de celles que le package crée lui-même, comme ses scripts.
- **Comparer deux versions** : afficher les différences avant de restaurer une sauvegarde ou d'enregistrer.
- **Détecter les packages cassés** : signaler dans la liste ceux qui citent des entités qui n'existent plus, comme le fait la section `packages` d'Entity Inventory.
- **Mode `include_dir_merge_named`** : vérifier que le fichier commence bien par le nom du package.
- **Deferred Restart** : proposer un redémarrage différé quand un package l'exige, si l'intégration est installée.
- **Soumission à hacs/default** quand la version sera stabilisée. Mathieu soumet la PR depuis son compte.
