"""Coût réel des appels à l'API Claude, en dollars, d'après le champ « usage » de chaque réponse.

Avec le cache, la plus grande partie de l'entrée est relue depuis le cache (cache_read_input_tokens) :
« input_tokens » seul sous-estime fortement la consommation.
"""

# Claude Opus 5.5, en dollars par million de tokens (tarifs publics de l'API).
PRIX_PAR_MILLION = {
    "input_tokens": 4.00,
    "cache_creation_input_tokens": 5.00,  # écriture dans le cache : 1,25 × l'entrée
    "cache_read_input_tokens": 0.20,      # relecture depuis le cache
    "output_tokens": 20.00,
}


def cout(usage) -> float:
    return sum((getattr(usage, champ, 0) or 0) * prix for champ, prix in PRIX_PAR_MILLION.items()) / 1_000_000
