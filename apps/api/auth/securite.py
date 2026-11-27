"""Mots de passe, jetons de connexion, codes d'accès et limitation des essais."""

import hashlib
import hmac
import secrets
import sqlite3

from apps.api.db import dans, iso, maintenant

# Paramètres scrypt (recommandations OWASP).
_N, _R, _P = 2**14, 8, 1

DUREE_CONNEXION_PARENT_JOURS = 30
DUREE_CONNEXION_ELEVE_JOURS = 90
DUREE_CODE_MINUTES = 15
FENETRE_ESSAIS_MINUTES = 15
MAX_ESSAIS_CODE = 5       # par adresse IP
MAX_ESSAIS_PARENT = 10    # par adresse e-mail
MAX_ESSAIS_ENFANT = 10    # mot secret : par adresse IP et par prénom


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    empreinte = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${sel.hex()}${empreinte.hex()}"


def verifier_mot_de_passe(mot_de_passe: str, stocke: str) -> bool:
    try:
        _, n, r, p, sel, empreinte = stocke.split("$")
        calcule = hashlib.scrypt(
            mot_de_passe.encode(), salt=bytes.fromhex(sel), n=int(n), r=int(r), p=int(p)
        )
    except ValueError:
        return False
    return hmac.compare_digest(calcule.hex(), empreinte)


# Empreinte factice : vérifiée quand l'e-mail est inconnu, pour que le temps de réponse
# ne révèle pas si un compte existe.
EMPREINTE_FACTICE = hacher_mot_de_passe(secrets.token_hex(16))


def empreinte(valeur: str) -> str:
    return hashlib.sha256(valeur.encode()).hexdigest()


def ouvrir_connexion(
    db: sqlite3.Connection, *, parent_id: int | None = None, eleve_id: int | None = None
) -> str:
    """Crée une connexion et renvoie le jeton (seule son empreinte est stockée)."""
    jeton = secrets.token_urlsafe(32)
    jours = DUREE_CONNEXION_PARENT_JOURS if parent_id else DUREE_CONNEXION_ELEVE_JOURS
    db.execute(
        "INSERT INTO connexions (jeton_hash, parent_id, eleve_id, expire_le) VALUES (?, ?, ?, ?)",
        (empreinte(jeton), parent_id, eleve_id, dans(days=jours)),
    )
    return jeton


def prolonger_connexion(db: sqlite3.Connection, jeton: str, jours: int) -> None:
    """Session glissante : chaque visite repousse l'expiration (on ne se déconnecte pas en restant actif)."""
    db.execute("UPDATE connexions SET expire_le = ? WHERE jeton_hash = ?", (dans(days=jours), empreinte(jeton)))


def fermer_connexion(db: sqlite3.Connection, jeton: str) -> None:
    db.execute("DELETE FROM connexions WHERE jeton_hash = ?", (empreinte(jeton),))


def lire_connexion(db: sqlite3.Connection, jeton: str | None) -> sqlite3.Row | None:
    if not jeton:
        return None
    return db.execute(
        "SELECT parent_id, eleve_id FROM connexions WHERE jeton_hash = ? AND expire_le > ?",
        (empreinte(jeton), iso(maintenant())),
    ).fetchone()


def creer_code_acces(db: sqlite3.Connection, eleve_id: int) -> tuple[str, str]:
    """Génère un code à 6 chiffres, unique parmi les codes actifs. Remplace l'ancien code."""
    db.execute("DELETE FROM codes_acces WHERE expire_le <= ?", (iso(maintenant()),))
    db.execute("DELETE FROM codes_acces WHERE eleve_id = ?", (eleve_id,))
    expire_le = dans(minutes=DUREE_CODE_MINUTES)
    while True:
        code = f"{secrets.randbelow(10**6):06d}"
        try:
            db.execute(
                "INSERT INTO codes_acces (eleve_id, code_hash, expire_le) VALUES (?, ?, ?)",
                (eleve_id, empreinte(code), expire_le),
            )
            return code, expire_le
        except sqlite3.IntegrityError:
            continue  # code déjà actif pour un autre élève : on en tire un autre


def utiliser_code_acces(db: sqlite3.Connection, code: str) -> int | None:
    """Renvoie l'élève lié au code s'il est valide, et supprime le code (usage unique)."""
    ligne = db.execute(
        "SELECT eleve_id FROM codes_acces WHERE code_hash = ? AND expire_le > ?",
        (empreinte(code), iso(maintenant())),
    ).fetchone()
    if ligne is None:
        return None
    db.execute("DELETE FROM codes_acces WHERE eleve_id = ?", (ligne["eleve_id"],))
    return ligne["eleve_id"]


def trop_d_essais(db: sqlite3.Connection, cle: str, maximum: int) -> bool:
    depuis = dans(minutes=-FENETRE_ESSAIS_MINUTES)
    db.execute("DELETE FROM essais_echoues WHERE moment <= ?", (depuis,))
    (nombre,) = db.execute(
        "SELECT COUNT(*) FROM essais_echoues WHERE cle = ? AND moment > ?", (cle, depuis)
    ).fetchone()
    return nombre >= maximum


def noter_essai_echoue(db: sqlite3.Connection, cle: str) -> None:
    db.execute(
        "INSERT INTO essais_echoues (cle, moment) VALUES (?, ?)", (cle, iso(maintenant()))
    )
