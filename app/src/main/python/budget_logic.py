"""
Logique métier du suivi de budget.
Catégorisation automatique, calculs journaliers/mensuels, données widget.
"""
import json
from datetime import datetime, date, timedelta
from calendar import monthrange
from typing import Optional

import config
from database import DatabaseManager


class BudgetManager:
    """Calculs de budget et préparation des données pour l'interface."""

    def __init__(self, db_manager: DatabaseManager,
                 objectif_journalier: float = None):
        """
        :param db_manager:         Instance DatabaseManager partagée.
        :param objectif_journalier: Surcharge de l'objectif (défaut : config).
        """
        self.db = db_manager
        self.objectif_journalier = (
            objectif_journalier
            or float(self.db.get_parametre("objectif_journalier",
                                           config.OBJECTIF_JOURNALIER))
        )

    # ------------------------------------------------------------------
    # Catégorisation automatique
    # ------------------------------------------------------------------

    def categoriser_transaction(self, description: str,
                                contrepartie: str = "") -> str:
        """
        Détermine la catégorie d'une transaction par correspondance de mots-clés.
        :return: Nom de catégorie (str), 'autre' si aucune correspondance.
        """
        texte = (description + " " + contrepartie).lower()
        for categorie, mots_cles in config.CATEGORIES.items():
            if categorie == "autre":
                continue
            for mot in mots_cles:
                if mot.lower() in texte:
                    return categorie
        return "autre"

    def categoriser_et_sauvegarder(self, transactions: list) -> list:
        """
        Catégorise les transactions sans catégorie puis les persiste en base.
        :return: Liste enrichie avec le champ 'categorie' renseigné.
        """
        for t in transactions:
            if not t.get("categorie"):
                t["categorie"] = self.categoriser_transaction(
                    t.get("description", ""),
                    t.get("contrepartie", "")
                )
        self.db.sauvegarder_transactions(transactions)
        return transactions

    # ------------------------------------------------------------------
    # Calculs journaliers
    # ------------------------------------------------------------------

    def calcul_depenses_jour(self, jour: Optional[date] = None) -> dict:
        """
        Résumé des dépenses pour un jour donné.

        :param jour: Date à analyser (défaut : aujourd'hui).
        :return: dict{date, total_depenses, objectif, progression_pct,
                      statut, nb_transactions, par_categorie, restant}
        """
        if jour is None:
            jour = date.today()

        resume = self.db.get_resume_journalier(jour.strftime("%Y-%m-%d"))
        total = resume["total_depenses"]
        progression = (total / self.objectif_journalier * 100
                       if self.objectif_journalier > 0 else 0)

        # Statut proratisé selon l'heure de la journée
        heure = datetime.now().hour
        budget_proratise = self.objectif_journalier * (heure / 24)

        if total <= budget_proratise * 0.8:
            statut = "excellent"
        elif total <= self.objectif_journalier:
            statut = "ok"
        elif total <= self.objectif_journalier * 1.2:
            statut = "attention"
        else:
            statut = "depassement"

        return {
            "date": jour.strftime("%Y-%m-%d"),
            "total_depenses": round(total, 2),
            "objectif": self.objectif_journalier,
            "progression_pct": round(progression, 1),
            "statut": statut,
            "nb_transactions": resume["nb_transactions"],
            "par_categorie": resume["par_categorie"],
            "restant": round(self.objectif_journalier - total, 2)
        }

    # ------------------------------------------------------------------
    # Calculs mensuels
    # ------------------------------------------------------------------

    def calcul_depenses_mois(self, annee: int = None,
                              mois: int = None) -> dict:
        """
        Résumé des dépenses pour un mois complet.

        :param annee: Année (défaut : courante).
        :param mois:  Mois 1-12 (défaut : courant).
        :return: dict avec totaux, moyenne, projection, tendance…
        """
        aujourd_hui = date.today()
        annee = annee or aujourd_hui.year
        mois = mois or aujourd_hui.month

        premier_jour = date(annee, mois, 1)
        nb_jours_mois = monthrange(annee, mois)[1]
        dernier_jour = date(annee, mois, nb_jours_mois)

        transactions = self.db.get_transactions(
            date_debut=premier_jour.strftime("%Y-%m-%d"),
            date_fin=dernier_jour.strftime("%Y-%m-%d"),
            seulement_depenses=True
        )
        total = sum(abs(t["montant"]) for t in transactions)

        # Jours écoulés (partiel si mois en cours)
        if annee == aujourd_hui.year and mois == aujourd_hui.month:
            jours_ecoules = aujourd_hui.day
        else:
            jours_ecoules = nb_jours_mois

        objectif_mensuel = self.objectif_journalier * nb_jours_mois
        moyenne_journaliere = total / jours_ecoules if jours_ecoules > 0 else 0
        projection = moyenne_journaliere * nb_jours_mois

        # Agrégation par catégorie
        par_categorie: dict = {}
        for t in transactions:
            cat = t.get("categorie") or "autre"
            if cat not in par_categorie:
                par_categorie[cat] = {"total": 0.0, "nb": 0}
            par_categorie[cat]["total"] += abs(t["montant"])
            par_categorie[cat]["nb"] += 1
        for cat in par_categorie:
            par_categorie[cat]["total"] = round(par_categorie[cat]["total"], 2)

        return {
            "annee": annee,
            "mois": mois,
            "total_depenses": round(total, 2),
            "objectif_mensuel": round(objectif_mensuel, 2),
            "moyenne_journaliere": round(moyenne_journaliere, 2),
            "objectif_journalier": self.objectif_journalier,
            "projection_fin_mois": round(projection, 2),
            "jours_ecoules": jours_ecoules,
            "jours_dans_mois": nb_jours_mois,
            "nb_transactions": len(transactions),
            "par_categorie": par_categorie,
            "tendance": "hausse" if projection > objectif_mensuel else "baisse"
        }

    # ------------------------------------------------------------------
    # Solde de budget cumulé
    # ------------------------------------------------------------------

    def calcul_solde_budget(self) -> dict:
        """
        Solde entre budget prévu et dépenses réelles depuis le 1er du mois.
        Positif = économies, négatif = dépassement.
        """
        aujourd_hui = date.today()
        depenses_mois = self.calcul_depenses_mois()
        budget_prevu = self.objectif_journalier * aujourd_hui.day
        total_depense = depenses_mois["total_depenses"]
        solde = budget_prevu - total_depense

        return {
            "solde": round(solde, 2),
            "est_positif": solde >= 0,
            "budget_prevu": round(budget_prevu, 2),
            "total_depense": round(total_depense, 2)
        }

    # ------------------------------------------------------------------
    # Point d'entrée principal — données widget
    # ------------------------------------------------------------------

    def get_dashboard_data(self) -> dict:
        """
        Agrège toutes les données nécessaires au widget et à l'écran principal.
        Appelé depuis Kotlin via Chaquopy.

        :return: dict JSON-sérialisable couvrant : jour, mois, solde, top dépenses.
        """
        aujourd_hui = date.today()

        depenses_jour = self.calcul_depenses_jour()
        depenses_mois = self.calcul_depenses_mois()
        solde = self.calcul_solde_budget()

        # Transactions des 3 derniers jours pour le top dépenses
        date_debut = (aujourd_hui - timedelta(days=2)).strftime("%Y-%m-%d")
        recentes = self.db.get_transactions(
            date_debut=date_debut,
            date_fin=aujourd_hui.strftime("%Y-%m-%d"),
            seulement_depenses=True
        )
        top3 = sorted(recentes, key=lambda t: abs(t["montant"]), reverse=True)[:3]

        return {
            "meta": {
                "mise_a_jour": datetime.now().isoformat(),
                "objectif_journalier": self.objectif_journalier,
                "devise": "EUR"
            },
            "aujourd_hui": {
                "total_depenses": depenses_jour["total_depenses"],
                "objectif": depenses_jour["objectif"],
                "restant": depenses_jour["restant"],
                "progression_pct": depenses_jour["progression_pct"],
                "statut": depenses_jour["statut"],
                "nb_transactions": depenses_jour["nb_transactions"]
            },
            "mois_courant": {
                "total_depenses": depenses_mois["total_depenses"],
                "objectif": depenses_mois["objectif_mensuel"],
                "moyenne_journaliere": depenses_mois["moyenne_journaliere"],
                "projection": depenses_mois["projection_fin_mois"],
                "jours_restants": (depenses_mois["jours_dans_mois"]
                                   - depenses_mois["jours_ecoules"]),
                "tendance": depenses_mois["tendance"]
            },
            "solde_budget": {
                "montant": solde["solde"],
                "est_positif": solde["est_positif"]
            },
            "top_depenses_recentes": [
                {
                    "label": t.get("description") or t.get("contrepartie", ""),
                    "montant": round(abs(t["montant"]), 2),
                    "date": t["date"],
                    "categorie": t.get("categorie") or "autre"
                }
                for t in top3
            ],
            "repartition_categories": depenses_mois.get("par_categorie", {})
        }

    def get_dashboard_json(self, chemin_db: str = None) -> str:
        """
        Version JSON string de get_dashboard_data().
        Pratique pour les appels Kotlin : retourne directement une str parseable.

        :param chemin_db: Ignoré ici (db déjà injectée), présent pour compatibilité
                          avec l'appel direct depuis main.py.
        """
        return json.dumps(self.get_dashboard_data(), ensure_ascii=False)


# ------------------------------------------------------------------
# Fonction utilitaire standalone appelable directement depuis Kotlin
# ------------------------------------------------------------------

def get_dashboard_json_from_path(chemin_db: str) -> str:
    """
    Instancie DatabaseManager + BudgetManager à partir d'un chemin SQLite
    et retourne le dashboard JSON. Point d'entrée minimal pour Kotlin.
    """
    from database import DatabaseManager
    db = DatabaseManager(chemin_db=chemin_db)
    manager = BudgetManager(db_manager=db)
    return manager.get_dashboard_json()
