# Budget App — Contexte et historique de conception

## Objectif du projet

Application Android de suivi de budget personnel avec :
- Objectif de **15 €/jour** de dépenses
- Récupération automatique des transactions via l'**API Bunq** (néobanque néerlandaise)
- Stockage local **SQLite** sur le téléphone
- **Widget écran d'accueil** Android (mini tableau de bord 3×4 icônes)

---

## Stack technique choisie

| Couche | Technologie | Rôle |
|---|---|---|
| Logique métier | Python 3.11 via **Chaquopy** | API Bunq, SQLite, calculs budget |
| Coquille Android | **Kotlin** | MainActivity, Widget, boilerplate |
| Persistance | **SQLite** | Stockage local sur le téléphone |
| API | **Bunq REST** `/v1/user/{id}/monetary-account/{id}/payment` |
| Build | **Android Studio** + Gradle 8.2 |
| Éditeur | **VS Code** (développement Python standalone) |

---

## Fichiers générés (session initiale)

```
BudgetApp/
├── .gitignore
├── config.local.py.example          ← modèle config locale (gitignored)
├── build.gradle                      ← config projet Gradle
├── settings.gradle
└── app/
    ├── build.gradle                  ← config Chaquopy + pip (requests, cryptography)
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/budget/app/
        │   ├── MainActivity.kt       ← init Chaquopy, appel Python, trigger widget
        │   └── BudgetWidget.kt       ← AppWidgetProvider, RemoteViews
        ├── python/
        │   ├── config.py             ← paramètres, catégories, chargement clé API
        │   ├── bunq_client.py        ← auth 3 étapes RSA + récupération transactions
        │   ├── database.py           ← SQLite CRUD (transactions, session, params)
        │   ├── budget_logic.py       ← calculs + get_dashboard_data()
        │   └── main.py               ← point d'entrée standalone VS Code
        └── res/
            ├── drawable/widget_background.xml
            ├── layout/activity_main.xml
            ├── layout/widget_budget.xml
            ├── values/colors.xml
            ├── values/strings.xml
            ├── values/themes.xml
            └── xml/budget_widget_info.xml
```

---

## Décisions architecturales clés

### 1. Séparation Python / Kotlin
- **Python** : toute la logique métier (API, calculs, base de données)
- **Kotlin** : uniquement le shell Android (cycle de vie, widget, intent)
- Les modules Python sont **testables sans Android** depuis VS Code

### 2. Gestion de la clé API Bunq
- La clé n'est **jamais hardcodée** dans le code
- En standalone : lue depuis `config.local.py` (gitignored, auto-détecté par `config.py`)
- Sur Android : à passer depuis Kotlin (SharedPreferences chiffrées) via paramètre

### 3. Point de contact Kotlin → Python
```
Python.getInstance()
  .getModule("budget_logic")
  .callAttr("get_dashboard_json_from_path", cheminDB)  // retourne String JSON
```
Fonction unique, pas de couplage fort entre les deux couches.

### 4. Authentification Bunq (3 étapes)
1. **Installation** : génération RSA 2048 bits + `POST /v1/installation`
2. **Device-server** : `POST /v1/device-server` (signé PKCS1v15/SHA256)
3. **Session** : `POST /v1/session-server` → `session_token`
- La session (tokens + clé RSA privée PEM) est **cachée en SQLite** pour éviter de répéter les étapes 1-2 à chaque démarrage.

### 5. Widget
- Taille : 3 colonnes × 4 lignes (`targetCellWidth/Height` Android 12+, `minWidth/Height` pour compatibilité)
- Layout `widget_budget.xml` : structure **placeholder** — les visuels détaillés (barres de progression, graphiques, icônes catégories) sont **à définir dans un second temps**
- Rafraîchissement auto toutes les 30 min (`updatePeriodMillis = 1800000`)

### 6. Catégorisation automatique
- Matching par mots-clés sur `description + contrepartie` de chaque transaction
- Catégories : `alimentation`, `transport`, `logement`, `loisirs`, `santé`, `shopping`, `autre`
- Extensible dans `config.py → CATEGORIES`

---

## Schéma SQLite

```sql
transactions (id, date, datetime, montant, est_depense, description,
              contrepartie, type, sous_type, categorie, cree_le)

session_bunq (id, installation_token, session_token, user_id,
              cle_privee_pem, mis_a_jour_le)

parametres   (cle, valeur, mis_a_jour_le)
```

---

## Structure du dashboard (`get_dashboard_data()`)

```json
{
  "meta":              { "mise_a_jour", "objectif_journalier", "devise" },
  "aujourd_hui":       { "total_depenses", "objectif", "restant",
                         "progression_pct", "statut", "nb_transactions" },
  "mois_courant":      { "total_depenses", "objectif", "moyenne_journaliere",
                         "projection", "jours_restants", "tendance" },
  "solde_budget":      { "montant", "est_positif" },
  "top_depenses_recentes": [ { "label", "montant", "date", "categorie" } ],
  "repartition_categories": { "alimentation": { "total", "nb" }, ... }
}
```

`statut` (aujourd'hui) : `"excellent"` | `"ok"` | `"attention"` | `"depassement"`

---

## Commandes de démarrage rapide

```bash
# Installer les dépendances Python
pip install requests cryptography

# Tester sans clé API (données fictives)
python app/src/main/python/main.py --fictif

# Tester avec l'API Bunq réelle
cp config.local.py.example config.local.py
# → renseigner BUNQ_API_KEY, BUNQ_USER_ID, BUNQ_ACCOUNT_ID
python app/src/main/python/main.py
```

---

## À faire (prochaines étapes)

- [ ] Définir les visuels détaillés du widget (`widget_budget.xml`)
- [ ] Ajouter la synchronisation Bunq en arrière-plan (WorkManager Kotlin)
- [ ] Stocker la clé API côté Android dans `EncryptedSharedPreferences`
- [ ] Tester l'authentification Bunq sandbox avant production
- [ ] Gérer la pagination de l'API Bunq (param `older_id` pour scroll infini)
- [ ] Ajouter des icônes de catégories dans le widget
- [ ] Notifications push si dépassement de l'objectif journalier
