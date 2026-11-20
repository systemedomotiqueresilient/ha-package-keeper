# Feuille de route

## Fait
- **0.1.0** : panneau réservé aux administrateurs, enregistrement contrôlé avec retour arrière automatique, historique et restauration, suppression restaurable, avis d'Entity Inventory, téléphone admin.
- **0.1.1** : l'avis d'Entity Inventory ne s'affiche plus pour un package qui ne cite aucune entité.
- **0.2.0** :
  - templates, automatisations, scripts et `unique_id` en double contrôlés avant l'écriture ;
  - liste des packages qui en dépendent, affichée avant une suppression ;
  - recherche dans la liste et menu compact.

## Pistes
- **Actions inconnues** : vérifier, sans bloquer, que les actions appelées existent. Il faut tenir compte de celles que le package crée lui-même, comme ses scripts.
- **Comparer deux versions** : afficher les différences avant de restaurer une sauvegarde ou d'enregistrer.
- **Détecter les packages cassés** : signaler dans la liste ceux qui citent des entités qui n'existent plus, comme le fait la section `packages` d'Entity Inventory.
- **Mode `include_dir_merge_named`** : vérifier que le fichier commence bien par le nom du package.
- **Deferred Restart** : proposer un redémarrage différé quand un package l'exige, si l'intégration est installée.
- **Soumission à hacs/default** quand la version sera stabilisée. Mathieu soumet la PR depuis son compte.
