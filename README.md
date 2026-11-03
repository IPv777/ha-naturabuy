# NaturaBuy Monitor for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Intégration avancée et ultra-complète pour **Home Assistant** permettant de surveiller en temps réel les enchères et les ventes sur [NaturaBuy](https://www.naturabuy.fr/).

Développé pour traquer les meilleures opportunités (ex: carabines à culasse linéaire ou à verrou en calibre 30-06 à moins de 600 €) et notifier instantanément votre smartphone (**ThinkPhone**) avec photo, prix, et liens interactifs.

---

## 🎯 Fonctionnalités Avancées

* ⏱️ **Surveillance des fins d'enchères :** Soyez prévenu automatiquement X minutes avant la fin (par défaut 60 min / 1 heure) si l'enchère est toujours inférieure à votre budget maximum.
* 🆕 **Détection instantanée des nouveautés :** Notification immédiate dès qu'une nouvelle vente (enchère ou achat immédiat) correspondant à vos critères apparaît sur le site.
* 🚫 **Filtre Enchères sans prix de réserve (`PR=noPR`) :** Élimine les fausses bonnes affaires où le prix de départ est bas mais le prix de réserve inaccessible.
* 🔍 **Filtrage par mots-clés d'exclusion :** Élimine automatiquement les accessoires parasites (chargeurs, canons seuls, crosses, rails, étuis) pour ne garder que de véritables carabines complètes.
* 📱 **Notifications interactives ThinkPhone (Android) :**
  * Canal dédié haute priorité (`channel: "NaturaBuy Alertes"`).
  * Affichage de la photo grand format de l'arme.
  * Bouton d'action direct **"🎯 Voir sur NaturaBuy"** qui ouvre directement l'annonce dans votre navigateur.
  * Tag unique par annonce pour mettre à jour la notification en temps réel sans saturer le tiroir de notifications.
* 🚨 **Capteur Binaire Dédié (`binary_sensor`) :**
  * `binary_sensor.<nom>_alerte_fin_imminente` passe à `on` dès qu'une enchère sous le budget arrive dans la dernière heure.
  * Idéal pour déclencher des automatisations (allumer un voyant, annonce vocale Alexa/Google, etc.).
* 📊 **Tableau de bord Lovelace prêt à l'emploi :**
  * L'attribut `markdown_table` du capteur principal fournit un tableau prêt à afficher dans une carte Markdown avec liens cliquables et statuts.

---

## 📦 Installation via HACS

1. Dans Home Assistant, ouvrez **HACS** > 3 points en haut à droite > **Dépôts personnalisés**.
2. Ajoutez : `https://github.com/IPv777/ha-naturabuy`
3. Catégorie : **Intégration** (*Integration*).
4. Cliquez sur **Ajouter**, recherchez **NaturaBuy Monitor** et téléchargez.
5. Redémarrez Home Assistant.

---

## 🎨 Carte Dashboard Lovelace (Exemple)

Collez ce code dans une carte **Markdown** sur votre tableau de bord Home Assistant :

```yaml
type: markdown
title: 🎯 NaturaBuy - Ventes & Enchères
content: >
  {{ state_attr('sensor.naturabuy_carabines_culasse_lineaire_30_06_total_annonces', 'markdown_table') }}

  ---

  {{ state_attr('sensor.naturabuy_carabines_a_verrou_30_06_total_annonces', 'markdown_table') }}
```

---

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.
