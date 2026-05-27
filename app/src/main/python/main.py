"""
Point d'entrée standalone — tests depuis VS Code sans Android.

Utilisation :
    python main.py            → teste avec config.local.py si présent
    python main.py --fictif   → injecte des données fictives et affiche le dashboard
"""
import json
import sys
import os
import argparse
from datetime import date, timedelta
import random

sys.path.insert(0, os.path.dirname(__file__))

from database import DatabaseManager
from bunq_client import BunqClient
from budget_logic import BudgetManager
import config


# ------------------------------------------------------------------
# Fonctions appelées depuis Kotlin via Chaquopy
# ------------------------------------------------------------------

def initialiser_app(chemin_db: str):
    """
    Crée et retourne le triplet (DatabaseManager, BunqClient, BudgetManager).
    Appelé depuis MainActivity.kt et BudgetWidget.kt.
    """
    db = DatabaseManager(chemin_db=chemin_db)
    client = BunqClient(db_manager=db)
    gestionnaire = BudgetManager(db_manager=db)
    return db, client, gestionnaire


def synchroniser_et_get_dashboard(chemin_db: str, api_key: str = None,
                                   user_id: str = None,
                                   account_id: str = None) -> str:
    """
    Synchronise les transactions Bunq puis retourne le dashboard JSON.
    Surcharge optionnelle des credentials pour Android (via SharedPreferences Kotlin).
    """
    db = DatabaseManager(chemin_db=chemin_db)
    client = BunqClient(
        api_key=api_key, user_id=user_id, account_id=account_id,
        db_manager=db
    )
    gestionnaire = BudgetManager(db_manager=db)

    client.authentifier()
    transactions = client.recuperer_transactions(nombre=100)
    gestionnaire.categoriser_et_sauvegarder(transactions)

    return gestionnaire.get_dashboard_json()


# ------------------------------------------------------------------
# Tests standalone
# ------------------------------------------------------------------

def _inserer_donnees_fictives(db: DatabaseManager):
    """Génère 30 transactions de test couvrant les 10 derniers jours."""
    templates = [
        ("Albert Heijn", "alimentation", -8.50),
        ("NS Reizen", "transport", -4.20),
        ("Netflix", "loisirs", -13.99),
        ("Apotheek", "santé", -6.80),
        ("Bol.com", "shopping", -22.00),
        ("Restaurant Thai Orchid", "alimentation", -18.50),
        ("OV-chipkaart", "transport", -3.60),
        ("Lidl", "alimentation", -12.30),
        ("Spotify", "loisirs", -9.99),
        ("Kruidvat", "shopping", -5.40),
        ("Thuisbezorgd", "alimentation", -24.00),
        ("Shell", "transport", -55.00),
    ]

    aujourd_hui = date.today()
    transactions = []

    for i in range(30):
        label, cat, base_montant = random.choice(templates)
        variation = random.uniform(-0.3, 0.3)
        montant = round(base_montant * (1 + variation), 2)
        jours = random.randint(0, 9)
        jour = aujourd_hui - timedelta(days=jours)
        heure = random.randint(8, 21)
        minutes = random.randint(0, 59)

        transactions.append({
            "id": f"test_{i:04d}",
            "date": jour.strftime("%Y-%m-%d"),
            "datetime": f"{jour.strftime('%Y-%m-%d')}T{heure:02d}:{minutes:02d}:00",
            "montant": montant,
            "est_depense": True,
            "description": label,
            "contrepartie": label,
            "type": "IDEAL",
            "sous_type": "ONLINE",
            "categorie": cat
        })

    db.sauvegarder_transactions(transactions)
    return len(transactions)


def main():
    parser = argparse.ArgumentParser(description="Budget App — test standalone")
    parser.add_argument("--fictif", action="store_true",
                        help="Utilise des données fictives au lieu de l'API Bunq")
    args = parser.parse_args()

    print("=" * 55)
    print("  Budget App — Test Standalone")
    print("=" * 55)

    db = DatabaseManager()
    gestionnaire = BudgetManager(db_manager=db)

    if args.fictif:
        print("\n📊 Injection de données fictives...")
        nb = _inserer_donnees_fictives(db)
        print(f"   {nb} transactions insérées.")
    elif not config.BUNQ_API_KEY:
        print("\n⚠️  Aucune clé API Bunq trouvée.")
        print("   → Créez BudgetApp/config.local.py avec :")
        print('     BUNQ_API_KEY   = "votre-clé-api"')
        print('     BUNQ_USER_ID   = "12345678"')
        print('     BUNQ_ACCOUNT_ID = "87654321"')
        print("\n   → Ou lancez : python main.py --fictif\n")
        sys.exit(0)
    else:
        client = BunqClient(db_manager=db)
        try:
            print("\n🔐 Authentification Bunq...")
            client.authentifier()
            print("📥 Récupération des transactions...")
            transactions = client.recuperer_transactions(nombre=100)
            gestionnaire.categoriser_et_sauvegarder(transactions)
            print(f"✅ {len(transactions)} transactions synchronisées.")
        except Exception as e:
            print(f"\n❌ Erreur API : {e}")
            print("   Affichage des données locales existantes.\n")

    print("\n📊 Dashboard :")
    print("-" * 55)
    dashboard = gestionnaire.get_dashboard_data()
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
