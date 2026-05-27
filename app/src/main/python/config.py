"""
Configuration de l'application Budget.
Les valeurs sensibles (clé API) sont chargées depuis config.local.py (exclu du repo).
Sur Android, les credentials sont passés en paramètre depuis Kotlin via SharedPreferences.
"""
import os
import sys

# Détection de l'environnement d'exécution
IS_ANDROID = hasattr(sys, 'getandroidapilevel')

# --- Paramètres de budget ---
OBJECTIF_JOURNALIER = 15.0  # Objectif de dépenses journalières en euros

# Catégories avec mots-clés associés (insensible à la casse)
CATEGORIES = {
    "alimentation": [
        "supermarché", "lidl", "albert heijn", "jumbo", "aldi", "carrefour",
        "restaurant", "boulangerie", "mc donald", "burger", "sushi", "pizza",
        "delivery", "thuisbezorgd", "uber eats", "ah ", "dirk", "plus ",
        "frituur", "snackbar", "broodje", "slager"
    ],
    "transport": [
        "ns ", "trein", "ov-chipkaart", "ov chipkaart", "bus ", "metro",
        "tram", "uber", "bolt taxi", "parking", "essence", "shell", "bp ",
        "total energie", "tikkie ov", "connexxion", "gvb", "ret ", "htm "
    ],
    "logement": [
        "loyer", "huur", "energie", "electricité", "water", "gaz", "internet",
        "vodafone", "t-mobile", "kpn", "ziggo", "nuon", "vattenfall",
        "eneco", "essent", "gemeentebelasting", "waternet"
    ],
    "loisirs": [
        "cinema", "bioscoop", "netflix", "spotify", "steam", "concert",
        "musée", "museum", "parc", "pathé", "vue cinema", "ticketmaster",
        "eventbrite", "bol.com games", "playstation"
    ],
    "santé": [
        "pharmacie", "apotheek", "médecin", "huisarts", "dentiste",
        "tandarts", "ziekenhuis", "hôpital", "zorgverzekering", "cz ",
        "vgz ", "menzis", "achmea", "optiek", "brillen"
    ],
    "shopping": [
        "amazon", "bol.com", "zalando", "h&m", "zara", "primark", "ikea",
        "hema", "action ", "kruidvat", "etos", "mediamarkt", "coolblue",
        "wehkamp", "about you"
    ],
    "autre": []  # Catégorie par défaut si aucun mot-clé ne correspond
}

# --- Paramètres API Bunq ---
BUNQ_BASE_URL = "https://api.bunq.com"
BUNQ_API_VERSION = "v1"

# Initialisation des credentials (vides par défaut)
BUNQ_API_KEY = ""
BUNQ_USER_ID = ""
BUNQ_ACCOUNT_ID = ""

# --- Chargement de la config locale (uniquement hors Android) ---
if not IS_ANDROID:
    # Chemins candidats pour config.local.py (relatif au script ou parents)
    _dossier_courant = os.path.dirname(os.path.abspath(__file__))
    _chemins_candidats = [
        os.path.join(_dossier_courant, "config.local.py"),
        os.path.join(_dossier_courant, "..", "config.local.py"),
        os.path.join(_dossier_courant, "..", "..", "config.local.py"),
        os.path.join(_dossier_courant, "..", "..", "..", "config.local.py"),
    ]

    for _chemin in _chemins_candidats:
        _chemin = os.path.normpath(_chemin)
        if os.path.exists(_chemin):
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("config_local", _chemin)
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            BUNQ_API_KEY = getattr(_mod, "BUNQ_API_KEY", "")
            BUNQ_USER_ID = getattr(_mod, "BUNQ_USER_ID", "")
            BUNQ_ACCOUNT_ID = getattr(_mod, "BUNQ_ACCOUNT_ID", "")
            # Surcharge optionnelle de l'objectif journalier
            OBJECTIF_JOURNALIER = getattr(_mod, "OBJECTIF_JOURNALIER", OBJECTIF_JOURNALIER)
            break
