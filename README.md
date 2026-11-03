# NaturaBuy Monitor for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Intégration complète pour **Home Assistant** permettant de surveiller en temps réel les enchères et les nouvelles ventes sur [NaturaBuy](https://www.naturabuy.fr/).

Développé pour surveiller les annonces ciblées (ex: carabines à culasse linéaire ou à verrou en 30-06 sous 600 €) et notifier instantanément vos smartphones avec lien direct et photo.

---

## 🎯 Fonctionnalités

* ⏱️ **Surveillance des fins d'enchères :** Soyez prévenu automatiquement X minutes avant la fin (par défaut 60 min / 1 heure) si l'enchère est toujours inférieure à votre budget maximum.
* 🆕 **Détection des nouvelles annonces :** Notification immédiate dès qu'une nouvelle vente (enchère ou achat immédiat) correspondant à vos critères apparaît sur le site.
* 📱 **Notifications interactives et enrichies :** Envoi vers vos téléphones (Home Assistant Companion App) avec le prix, l'état, la photo de l'article et un **lien cliquable** qui ouvre directement la fiche NaturaBuy !
* 🔍 **Multi-surveillances (Multi-Watches) :** Configurez autant de recherches que vous le souhaitez avec des critères indépendants (URL de catégorie, filtres de prix min/max, type de vente).
* 📊 **Capteurs détaillés pour votre tableau de bord :**
  * `sensor.<nom>_total_annonces` : Nombre d'annonces correspondant aux critères.
  * `sensor.<nom>_encheres_actives` : Nombre d'enchères en cours sous le prix plafond.
  * `sensor.<nom>_prochaine_fin` : Titre de la prochaine enchère à se terminer (avec prix, temps restant, lien, image).
  * `sensor.<nom>_derniere_annonce` : Titre du dernier objet mis en vente.
* ⚡ **Événements Home Assistant :** Émet `naturabuy_new_listing` et `naturabuy_auction_ending_soon` pour déclencher vos propres automatisations personnalisées.
* 🔄 **Service d'actualisation manuelle :** Service `naturabuy.refresh` pour forcer une vérification immédiate.

---

## 📦 Installation

### Option 1 : Via HACS (Recommandé)

1. Ouvrez **HACS** dans votre Home Assistant.
2. Cliquez sur les 3 points verticaux en haut à droite > **Dépôts personnalisés** (*Custom repositories*).
3. Ajoutez l'URL du dépôt : `https://github.com/IPv777/ha-naturabuy`
4. Choisissez la catégorie : **Intégration** (*Integration*).
5. Cliquez sur **Ajouter**, recherchez **NaturaBuy Monitor** et cliquez sur **Télécharger**.
6. Redémarrez Home Assistant.

### Option 2 : Installation manuelle

Copiez le dossier `custom_components/naturabuy` dans le répertoire `config/custom_components/` de votre Home Assistant, puis redémarrez Home Assistant.

---

## ⚙️ Configuration

1. Rendez-vous dans **Paramètres** > **Appareils et services** > **Ajouter une intégration**.
2. Recherchez **NaturaBuy**.
3. Renseignez vos paramètres :
   * **Nom de la surveillance** : ex. `Carabines linéaires 30-06 < 600€`
   * **URL NaturaBuy** : L'URL de la catégorie ou recherche souhaitée (ex: `https://www.naturabuy.fr/Carabines-culasse-lineaire-30-06-critere-152850.html`)
   * **Prix maximum (€)** : ex. `600`
   * **Prix minimum (€)** : (optionnel, ex: `0`)
   * **Type de vente** : `Toutes`, `Enchères uniquement`, ou `Achat Immédiat uniquement`
   * **Alerte avant la fin** : `60` minutes
   * **Téléphones à notifier** : Sélectionnez un ou plusieurs services de notification (ex: `notify.mobile_app_...` ou `notify.notifs_tous_les_telephones`)
   * **Intervalle de scan** : ex. `10` minutes

Vous pouvez modifier ces paramètres à tout moment en cliquant sur **Configurer** sur l'intégration.

---

## 💡 Événements émis (pour Automatisations)

L'intégration déclenche des événements sur le bus Home Assistant :

### 1. `naturabuy_new_listing`
Déclenché à chaque nouvel article détecté sous le prix maximum.

```yaml
alias: "Alerte nouvelle carabine NaturaBuy"
trigger:
  - platform: event
    event_type: naturabuy_new_listing
action:
  - service: notify.notify
    data:
      title: "Nouvelle arme détectée !"
      message: "{{ trigger.event.data.title }} à {{ trigger.event.data.price_str }}"
      data:
        url: "{{ trigger.event.data.url }}"
```

### 2. `naturabuy_auction_ending_soon`
Déclenché lorsque l'enchère arrive à moins de X minutes du terme et reste sous le budget fixé.

---

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.
