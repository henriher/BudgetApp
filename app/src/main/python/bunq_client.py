"""
Client API Bunq — authentification OAuth et récupération des transactions.

Flux d'authentification Bunq (3 étapes) :
  1. Installation  : génération clé RSA + POST /v1/installation
  2. Device-server : enregistrement de l'appareil + POST /v1/device-server
  3. Session       : création de session  + POST /v1/session-server
La session est mise en cache SQLite pour éviter de répéter les étapes 1-2.
"""
import json
import uuid
import base64
import requests
from datetime import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

import config


class BunqClient:
    """Client pour l'API REST Bunq."""

    def __init__(self, api_key: str = None, user_id: str = None,
                 account_id: str = None, db_manager=None):
        """
        :param api_key:     Clé API Bunq. Si None, utilise config.BUNQ_API_KEY.
        :param user_id:     ID utilisateur Bunq.
        :param account_id:  ID du compte monétaire à interroger.
        :param db_manager:  Instance DatabaseManager pour cacher la session RSA.
        """
        self.api_key = api_key or config.BUNQ_API_KEY
        self.user_id = user_id or config.BUNQ_USER_ID
        self.account_id = account_id or config.BUNQ_ACCOUNT_ID
        self.db_manager = db_manager

        self.base_url = f"{config.BUNQ_BASE_URL}/{config.BUNQ_API_VERSION}"
        self.session_token = None
        self.installation_token = None
        self.private_key = None

        # Tentative de restauration d'une session précédente depuis le cache
        if self.db_manager:
            self._charger_session_cache()

    # ------------------------------------------------------------------
    # Génération des headers HTTP communs
    # ------------------------------------------------------------------

    def _headers(self, token: str = None) -> dict:
        """Retourne les headers communs à toutes les requêtes Bunq."""
        h = {
            "Content-Type": "application/json",
            "User-Agent": "BudgetApp/1.0",
            "X-Bunq-Language": "fr_FR",
            "X-Bunq-Region": "nl_NL",
            "X-Bunq-Geolocation": "0 0 0 0 000",
            "X-Bunq-Client-Request-Id": str(uuid.uuid4()),
            "Cache-Control": "no-cache",
        }
        if token:
            h["X-Bunq-Client-Authentication"] = token
        return h

    # ------------------------------------------------------------------
    # Signature RSA des requêtes (obligatoire pour device-server et session)
    # ------------------------------------------------------------------

    def _signer(self, corps: str) -> str:
        """Signe le corps de la requête avec la clé RSA privée (PKCS1v15 + SHA256)."""
        if not self.private_key:
            raise RuntimeError("Clé privée RSA manquante — appelez _installer() d'abord")
        signature = self.private_key.sign(
            corps.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode("utf-8")

    # ------------------------------------------------------------------
    # Étape 1 — Installation (génération RSA + enregistrement clé publique)
    # ------------------------------------------------------------------

    def _installer(self):
        """
        Génère une paire de clés RSA 2048 bits et enregistre la clé publique
        auprès de Bunq. Retourne l'installation_token.
        """
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        cle_publique_pem = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")

        corps = json.dumps({"client_public_key": cle_publique_pem})
        reponse = requests.post(
            f"{self.base_url}/installation",
            headers=self._headers(),
            data=corps
        )
        reponse.raise_for_status()

        for item in reponse.json().get("Response", []):
            if "Token" in item:
                self.installation_token = item["Token"]["token"]
                break

        return self.installation_token

    # ------------------------------------------------------------------
    # Étape 2 — Enregistrement de l'appareil
    # ------------------------------------------------------------------

    def _enregistrer_appareil(self):
        """Enregistre cet appareil auprès de Bunq avec la clé API."""
        corps = json.dumps({
            "description": "BudgetApp Android",
            "secret": self.api_key,
            "permitted_ips": ["*"]
        })
        headers = self._headers(token=self.installation_token)
        headers["X-Bunq-Client-Signature"] = self._signer(corps)

        reponse = requests.post(
            f"{self.base_url}/device-server",
            headers=headers,
            data=corps
        )
        reponse.raise_for_status()
        return reponse.json()

    # ------------------------------------------------------------------
    # Étape 3 — Création de session
    # ------------------------------------------------------------------

    def _creer_session(self):
        """Crée une session Bunq et stocke le session_token."""
        corps = json.dumps({"secret": self.api_key})
        headers = self._headers(token=self.installation_token)
        headers["X-Bunq-Client-Signature"] = self._signer(corps)

        reponse = requests.post(
            f"{self.base_url}/session-server",
            headers=headers,
            data=corps
        )
        reponse.raise_for_status()

        for item in reponse.json().get("Response", []):
            if "Token" in item:
                self.session_token = item["Token"]["token"]
            elif "UserPerson" in item or "UserCompany" in item:
                cle_user = "UserPerson" if "UserPerson" in item else "UserCompany"
                if not self.user_id:
                    self.user_id = str(item[cle_user]["id"])

        # Persistance en cache SQLite pour les prochains démarrages
        if self.db_manager and self.session_token:
            cle_privee_pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode("utf-8")
            self.db_manager.sauvegarder_session(
                installation_token=self.installation_token,
                session_token=self.session_token,
                user_id=self.user_id,
                cle_privee_pem=cle_privee_pem
            )

        return self.session_token

    # ------------------------------------------------------------------
    # Restauration de session depuis le cache
    # ------------------------------------------------------------------

    def _charger_session_cache(self):
        """Restaure la session (tokens + clé RSA) depuis SQLite si disponible."""
        session = self.db_manager.charger_session()
        if not session:
            return

        self.installation_token = session.get("installation_token")
        self.session_token = session.get("session_token")
        if session.get("user_id"):
            self.user_id = session["user_id"]

        cle_pem = session.get("cle_privee_pem", "")
        if cle_pem:
            self.private_key = serialization.load_pem_private_key(
                cle_pem.encode("utf-8"),
                password=None,
                backend=default_backend()
            )

    def _session_valide(self) -> bool:
        """Vérifie que le session_token actuel est encore accepté par Bunq."""
        try:
            r = requests.get(
                f"{self.base_url}/user",
                headers=self._headers(token=self.session_token)
            )
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Point d'entrée public — Authentification
    # ------------------------------------------------------------------

    def authentifier(self) -> bool:
        """
        Authentification complète. Réutilise la session en cache si valide,
        sinon recommence le flux en 3 étapes.
        """
        if self.session_token and self._session_valide():
            return True

        self._installer()
        self._enregistrer_appareil()
        self._creer_session()
        return bool(self.session_token)

    # ------------------------------------------------------------------
    # Récupération des transactions
    # ------------------------------------------------------------------

    def recuperer_transactions(self, nombre: int = 50) -> list:
        """
        Récupère les dernières transactions du compte monétaire configuré.

        :param nombre: Nombre maximum de paiements à récupérer (max 200).
        :return: Liste de dicts au format interne normalisé.
        """
        if not self.session_token:
            self.authentifier()

        url = (f"{self.base_url}/user/{self.user_id}"
               f"/monetary-account/{self.account_id}/payment")
        headers = self._headers(token=self.session_token)
        reponse = requests.get(url, headers=headers, params={"count": nombre})

        # Ré-authentification automatique si la session a expiré
        if reponse.status_code == 401:
            self.session_token = None
            self.authentifier()
            headers = self._headers(token=self.session_token)
            reponse = requests.get(url, headers=headers, params={"count": nombre})

        reponse.raise_for_status()

        paiements = []
        for item in reponse.json().get("Response", []):
            if "Payment" in item:
                paiements.append(self._formater(item["Payment"]))

        return paiements

    def _formater(self, paiement: dict) -> dict:
        """Normalise un objet Payment brut Bunq vers le format interne."""
        montant = float(paiement.get("amount", {}).get("value", 0))
        return {
            "id": str(paiement.get("id", "")),
            "date": paiement.get("created", "")[:10],       # YYYY-MM-DD
            "datetime": paiement.get("created", ""),
            "montant": montant,
            "est_depense": montant < 0,
            "description": paiement.get("description", ""),
            "contrepartie": (paiement.get("counterparty_alias", {})
                             .get("display_name", "")),
            "type": paiement.get("type", ""),
            "sous_type": paiement.get("sub_type", ""),
            "categorie": None   # renseigné ensuite par BudgetManager
        }
