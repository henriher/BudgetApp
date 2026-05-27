"""
Gestion de la base de données SQLite locale.
Stocke les transactions, la session Bunq (tokens + clé RSA) et les paramètres.
"""
import os
import sys
import sqlite3
from typing import Optional


class DatabaseManager:
    """Gestionnaire SQLite — toutes les opérations de persistance."""

    def __init__(self, chemin_db: str = None):
        """
        :param chemin_db: Chemin absolu vers le fichier .db.
                          Sur Android, DOIT être fourni par Kotlin (stockage privé).
                          En standalone, utilise la racine du projet si omis.
        """
        if chemin_db:
            self.chemin_db = chemin_db
        elif hasattr(sys, "getandroidapilevel"):
            raise ValueError(
                "Sur Android, le chemin de la base doit être passé explicitement depuis Kotlin."
            )
        else:
            # Mode standalone VS Code : fichier à la racine du projet
            self.chemin_db = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "budget.db")
            )

        self.init_database()

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------

    def _connexion(self) -> sqlite3.Connection:
        """Ouvre et retourne une connexion SQLite (row_factory activé)."""
        conn = sqlite3.connect(self.chemin_db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------------
    # Initialisation du schéma
    # ------------------------------------------------------------------

    def init_database(self):
        """Crée les tables et index si non existants (idempotent)."""
        with self._connexion() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id          TEXT PRIMARY KEY,
                    date        TEXT NOT NULL,
                    datetime    TEXT NOT NULL,
                    montant     REAL NOT NULL,
                    est_depense INTEGER NOT NULL DEFAULT 1,
                    description TEXT,
                    contrepartie TEXT,
                    type        TEXT,
                    sous_type   TEXT,
                    categorie   TEXT,
                    cree_le     TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_date
                    ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_transactions_categorie
                    ON transactions(categorie);

                -- Cache de la session Bunq (tokens + clé RSA privée)
                CREATE TABLE IF NOT EXISTS session_bunq (
                    id                  INTEGER PRIMARY KEY,
                    installation_token  TEXT,
                    session_token       TEXT,
                    user_id             TEXT,
                    cle_privee_pem      TEXT,
                    mis_a_jour_le       TEXT DEFAULT (datetime('now'))
                );

                -- Paramètres clé/valeur génériques (objectif, préférences…)
                CREATE TABLE IF NOT EXISTS parametres (
                    cle         TEXT PRIMARY KEY,
                    valeur      TEXT NOT NULL,
                    mis_a_jour_le TEXT DEFAULT (datetime('now'))
                );
            """)

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    def sauvegarder_transactions(self, transactions: list) -> int:
        """
        Insère ou remplace une liste de transactions.
        :return: Nombre de lignes effectivement modifiées.
        """
        modifiees = 0
        with self._connexion() as conn:
            for t in transactions:
                c = conn.execute(
                    """INSERT OR REPLACE INTO transactions
                       (id, date, datetime, montant, est_depense,
                        description, contrepartie, type, sous_type, categorie)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        t["id"], t["date"], t["datetime"],
                        t["montant"], 1 if t.get("est_depense") else 0,
                        t.get("description"), t.get("contrepartie"),
                        t.get("type"), t.get("sous_type"), t.get("categorie")
                    )
                )
                modifiees += c.rowcount
        return modifiees

    def get_transactions(self,
                         date_debut: str = None,
                         date_fin: str = None,
                         categorie: str = None,
                         seulement_depenses: bool = False) -> list:
        """
        Retourne les transactions filtrées par date, catégorie et/ou sens.

        :param date_debut: Format YYYY-MM-DD (inclus).
        :param date_fin:   Format YYYY-MM-DD (inclus).
        :param categorie:  Filtre exact sur la colonne categorie.
        :param seulement_depenses: Si True, exclut les entrées d'argent.
        """
        conditions, params = [], []

        if date_debut:
            conditions.append("date >= ?")
            params.append(date_debut)
        if date_fin:
            conditions.append("date <= ?")
            params.append(date_fin)
        if categorie:
            conditions.append("categorie = ?")
            params.append(categorie)
        if seulement_depenses:
            conditions.append("est_depense = 1")

        clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._connexion() as conn:
            rows = conn.execute(
                f"SELECT * FROM transactions {clause} ORDER BY datetime DESC",
                params
            ).fetchall()
        return [dict(r) for r in rows]

    def get_resume_journalier(self, date: str) -> dict:
        """
        Agrège les dépenses pour une date YYYY-MM-DD.
        :return: dict{date, total_depenses, nb_transactions, par_categorie}
        """
        with self._connexion() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(ABS(montant)), 0) AS total,
                          COUNT(*) AS nb
                   FROM transactions
                   WHERE date = ? AND est_depense = 1""",
                (date,)
            ).fetchone()

            cats = conn.execute(
                """SELECT categorie,
                          SUM(ABS(montant)) AS total,
                          COUNT(*) AS nb
                   FROM transactions
                   WHERE date = ? AND est_depense = 1
                   GROUP BY categorie""",
                (date,)
            ).fetchall()

        par_categorie = {
            (r["categorie"] or "autre"): {
                "total": round(r["total"], 2),
                "nb": r["nb"]
            }
            for r in cats
        }

        return {
            "date": date,
            "total_depenses": round(row["total"], 2),
            "nb_transactions": row["nb"],
            "par_categorie": par_categorie
        }

    # ------------------------------------------------------------------
    # Session Bunq
    # ------------------------------------------------------------------

    def sauvegarder_session(self, installation_token: str, session_token: str,
                             user_id: str, cle_privee_pem: str):
        """Écrase la session existante par la nouvelle (une seule ligne)."""
        with self._connexion() as conn:
            conn.execute("DELETE FROM session_bunq")
            conn.execute(
                """INSERT INTO session_bunq
                   (installation_token, session_token, user_id, cle_privee_pem, mis_a_jour_le)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (installation_token, session_token, user_id, cle_privee_pem)
            )

    def charger_session(self) -> Optional[dict]:
        """Retourne la session mise en cache, ou None si absente."""
        with self._connexion() as conn:
            row = conn.execute(
                "SELECT * FROM session_bunq ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Paramètres clé/valeur
    # ------------------------------------------------------------------

    def get_parametre(self, cle: str, defaut=None):
        """Lit un paramètre. Retourne defaut si inexistant."""
        with self._connexion() as conn:
            row = conn.execute(
                "SELECT valeur FROM parametres WHERE cle = ?", (cle,)
            ).fetchone()
        return row["valeur"] if row else defaut

    def set_parametre(self, cle: str, valeur: str):
        """Insère ou met à jour un paramètre."""
        with self._connexion() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO parametres (cle, valeur, mis_a_jour_le)
                   VALUES (?, ?, datetime('now'))""",
                (cle, str(valeur))
            )
