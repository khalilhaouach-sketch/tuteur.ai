"""Complète la banque des lettres du CP (agent/tools/exercices_cp.yaml) : plus de 10 exercices par lettre.

Les 3 premiers exercices de chaque lettre (écrits à la main) sont gardés ; les suivants sont produits ici à partir
d'un petit tableau de mots vocalisés, relisible par le professeur. Le fichier YAML reste la seule source utilisée
par le tuteur : on peut ensuite le corriger à la main (relancer ce script réécrit les exercices générés).

    python3 -m scripts.generer_exercices_lettres
"""

import hashlib
from pathlib import Path

import yaml

FICHIER = Path(__file__).resolve().parent.parent / "agent" / "tools" / "exercices_cp.yaml"
FATHA, DAMMA, KASRA = "َ", "ُ", "ِ"

# lettre : (nom vocalisé, 3 mots qui commencent par la lettre, 1 mot qui finit par la lettre)
LETTRES = {
    "م": ("المِيمِ", ["مَوْزٌ", "مَدْرَسَةٌ", "مَاءٌ"], "قَلَمٌ"),
    "ب": ("البَاءِ", ["بَابٌ", "بَيْتٌ", "بَطَّةٌ"], "كِتَابٌ"),
    "ر": ("الرَّاءِ", ["رِيشٌ", "رُمَّانٌ", "رَأْسٌ"], "قَمَرٌ"),
    "د": ("الدَّالِ", ["دَجَاجَةٌ", "دِيكٌ", "دُبٌّ"], "وَلَدٌ"),
    "س": ("السِّينِ", ["سَيَّارَةٌ", "سَمَكٌ", "سِكِّينٌ"], "شَمْسٌ"),
    "ل": ("اللَّامِ", ["لَيْمُونٌ", "لَبَنٌ", "لُعْبَةٌ"], "جَمَلٌ"),
    "ن": ("النُّونِ", ["نَمْلَةٌ", "نَمِرٌ", "نَارٌ"], "حِصَانٌ"),
    "ت": ("التَّاءِ", ["تُفَّاحٌ", "تَمْرٌ", "تِلْمِيذٌ"], "بَيْتٌ"),
    "ف": ("الفَاءِ", ["فِيلٌ", "فَأْرٌ", "فَرَاشَةٌ"], "خَرُوفٌ"),
    "ك": ("الكَافِ", ["كُرَةٌ", "كِتَابٌ", "كَلْبٌ"], "دِيكٌ"),
    "ع": ("العَيْنِ", ["عَيْنٌ", "عِنَبٌ", "عُصْفُورٌ"], "ضِفْدَعٌ"),
    "ه": ("الهَاءِ", ["هِلَالٌ", "هَدِيَّةٌ", "هُدْهُدٌ"], "وَجْهٌ"),
    "ج": ("الجِيمِ", ["جَمَلٌ", "جَزَرٌ", "جِسْرٌ"], "ثَلْجٌ"),
    "ح": ("الحَاءِ", ["حِصَانٌ", "حَلِيبٌ", "حُوتٌ"], "تُفَّاحٌ"),
    "ق": ("القَافِ", ["قَمَرٌ", "قَلَمٌ", "قِطٌّ"], "صُنْدُوقٌ"),
    "ص": ("الصَّادِ", ["صَقْرٌ", "صُنْدُوقٌ", "صَابُونٌ"], "قَمِيصٌ"),
    "أ": ("الهَمْزَةِ", ["أَرْنَبٌ", "أَسَدٌ", "إِبْرِيقٌ"], "مَاءٌ"),
    "و": ("الوَاوِ", ["وَلَدٌ", "وَرْدَةٌ", "وِسَادَةٌ"], "دَلْوٌ"),
    "ي": ("اليَاءِ", ["يَدٌ", "يَمَامَةٌ", "يَقْطِينٌ"], "كُرْسِيٌّ"),
    "ز": ("الزَّايِ", ["زَرَافَةٌ", "زَيْتُونٌ", "زَهْرَةٌ"], "خُبْزٌ"),
    "ش": ("الشِّينِ", ["شَمْسٌ", "شَجَرَةٌ", "شُبَّاكٌ"], "رِيشٌ"),
    "ط": ("الطَّاءِ", ["طَائِرَةٌ", "طَبْلٌ", "طَمَاطِمُ"], "مُشْطٌ"),
    "خ": ("الخَاءِ", ["خُبْزٌ", "خَرُوفٌ", "خِيَارٌ"], "بِطِّيخٌ"),
    "غ": ("الغَيْنِ", ["غُرَابٌ", "غَزَالٌ", "غَيْمَةٌ"], "دِمَاغٌ"),
    "ث": ("الثَّاءِ", ["ثَعْلَبٌ", "ثَوْبٌ", "ثَلْجٌ"], "لَيْثٌ"),
    "ذ": ("الذَّالِ", ["ذِئْبٌ", "ذَهَبٌ", "ذُرَةٌ"], "تِلْمِيذٌ"),
    "ض": ("الضَّادِ", ["ضِفْدَعٌ", "ضَوْءٌ", "ضِرْسٌ"], "بَيْضٌ"),
    "ظ": ("الظَّاءِ", ["ظَرْفٌ", "ظِلٌّ", "ظَبْيٌ"], "حَظٌّ"),
}
# Ordre des notions dans exercices_cp.yaml.
NOTION = {"م": "حرف الميم", "ب": "حرف الباء", "ر": "حرف الراء", "د": "حرف الدال", "س": "حرف السين",
          "ل": "حرف اللام", "ن": "حرف النون", "ت": "حرف التاء", "ف": "حرف الفاء", "ك": "حرف الكاف",
          "ع": "حرف العين", "ه": "حرف الهاء", "ج": "حرف الجيم", "ح": "حرف الحاء", "ق": "حرف القاف",
          "ص": "حرف الصاد", "أ": "حرف الهمزة", "و": "حرف الواو", "ي": "حرف الياء", "ز": "حرف الزاي",
          "ش": "حرف الشين", "ط": "حرف الطاء", "خ": "حرف الخاء", "غ": "حرف الغين", "ث": "حرف الثاء",
          "ذ": "حرف الذال", "ض": "حرف الضاد", "ظ": "حرف الظاء"}

HARAKAT = [(FATHA, "فَتْحَةٌ", "فتحة"), (DAMMA, "ضَمَّةٌ", "ضمة"), (KASRA, "كَسْرَةٌ", "كسرة")]
MADD = [("بِالأَلِفِ", "ا"), ("بِالوَاوِ", "و"), ("بِاليَاءِ", "ي")]
INDICE_HARAKAT = "الفَتْحَةُ وَالضَّمَّةُ فَوْقَ الحَرْفِ، وَالكَسْرَةُ تَحْتَهُ."
INDICE_MADD = "المَدُّ بِالأَلِفِ بَعْدَ الفَتْحَةِ، وَبِالوَاوِ بَعْدَ الضَّمَّةِ، وَبِاليَاءِ بَعْدَ الكَسْرَةِ."


def syllabe(lettre: str, haraka: str) -> str:
    if lettre == "أ":
        return {FATHA: "أَ", DAMMA: "أُ", KASRA: "إِ"}[haraka]
    return lettre + haraka


def syllabe_longue(lettre: str, i: int) -> str:
    if lettre == "أ":
        return ["آ", "أُو", "إِي"][i]
    return syllabe(lettre, HARAKAT[i][0]) + MADD[i][1]


def debut(mot: str) -> str:
    """Première lettre du mot avec sa voyelle (« مَ » pour « مَوْزٌ »)."""
    return mot[0] + (mot[1] if len(mot) > 1 and mot[1] in (FATHA, DAMMA, KASRA) else "")


def melanger(choix: list[str], graine: str) -> list[str]:
    """Ordre des boutons stable (mêmes fichiers à chaque génération) mais pas toujours le même."""
    return sorted(choix, key=lambda c: hashlib.sha256((graine + c).encode()).hexdigest())


def confusions(notion: dict) -> list[str]:
    """Les deux lettres proches, d'après le premier exercice (écrit à la main)."""
    return list(notion["exercices"][0]["erreurs"])


def exercices_generes(lettre: str, voisines: list[str]) -> list[dict]:
    nom, mots, mot_fin = LETTRES[lettre]
    lettre_mot = lambda v: "أ" if v in "أإآ" else v  # noqa: E731
    sortie = []

    def ajouter(difficulte, enonce_sans_choix, choix, bonne, erreurs, indice, explication, vocaliser=False):
        choix = melanger(choix, enonce_sans_choix)
        ex = {"difficulte": difficulte, "enonce": f"{enonce_sans_choix} ({' / '.join(choix)})",
              "reponses": [bonne], "erreurs": erreurs, "indice": indice, "explication": explication}
        if vocaliser:
            ex = {"difficulte": difficulte, "voyelles_obligatoires": True, **{k: v for k, v in ex.items() if k != "difficulte"}}
        sortie.append(ex)

    # 1. Quelle est la première lettre de ce mot ? (mots 2 et 3 ; le mot 1 est dans l'exercice écrit à la main)
    for mot in mots[1:]:
        s = debut(mot)
        haraka = s[1:]
        autres = [v + haraka for v in voisines]
        ajouter(1, f"مَا الحَرْفُ الأَوَّلُ فِي كَلِمَةِ «{mot}»؟", [s] + autres, s,
                {v: f"خلط بين «{lettre}» و«{v}»" for v in voisines},
                f"اِسْمَعِ الصَّوْتَ الأَوَّلَ فِي «{mot}».", f"الحَرْفُ الأَوَّلُ فِي «{mot}» هُوَ «{s}»: حَرْفُ {nom}.")

    # 2. Quel mot commence par cette lettre ? (les autres mots commencent par une lettre proche)
    for i, mot in enumerate(mots):
        intrus = [LETTRES[lettre_mot(v)][1][i] for v in voisines]
        ajouter(1, f"أَيُّ كَلِمَةٍ تَبْدَأُ بِحَرْفِ {nom}؟", [mot] + intrus, mot,
                {m: f"خلط بين «{lettre}» و«{v}»" for m, v in zip(intrus, voisines)},
                "اِسْمَعِ الصَّوْتَ الأَوَّلَ فِي كُلِّ كَلِمَةٍ.", f"«{mot}» تَبْدَأُ بِحَرْفِ {nom}.")

    # 3. Quelle est la voyelle sur cette syllabe ?
    for haraka, nom_h, sans in HARAKAT:
        s = syllabe(lettre, haraka)
        position = "تَحْتَ" if haraka == KASRA else "عَلَى"
        sortie.append({"difficulte": 2, "enonce": f"مَا الحَرَكَةُ عَلَى «{s}»؟ (فَتْحَةٌ / ضَمَّةٌ / كَسْرَةٌ)",
                       "reponses": [nom_h], "erreurs": {a: "خلط بين الحركات" for _, _, a in HARAKAT if a != sans},
                       "indice": INDICE_HARAKAT, "explication": f"{position} «{s}» {nom_h}."})
        # 4. Quelle syllabe porte cette voyelle ?
        syllabes = [syllabe(lettre, h) for h, _, _ in HARAKAT]
        ajouter(2, f"أَيُّ مَقْطَعٍ فِيهِ {nom_h}؟", syllabes, s,
                {x: "خلط بين الحركات" for x in syllabes if x != s}, INDICE_HARAKAT,
                f"فِي «{s}» {nom_h}.", vocaliser=True)

    # 5. Les syllabes longues (المد)
    longues = [syllabe_longue(lettre, i) for i in range(3)]
    for i, (avec, _) in enumerate(MADD):
        sortie.append({"difficulte": 3, "voyelles_obligatoires": True,
                       "enonce": f"اِخْتَرِ المَقْطَعَ الَّذِي فِيهِ مَدٌّ {avec}: ({' / '.join(longues)})",
                       "reponses": [longues[i]], "erreurs": {x: "خلط بين حروف المد" for x in longues if x != longues[i]},
                       "indice": INDICE_MADD, "explication": f"المَقْطَعُ الَّذِي فِيهِ مَدٌّ {avec} هُوَ «{longues[i]}»."})

    # 6. Où est la lettre dans le mot ? (au début / à la fin)
    for mot, ou, autre in [(mots[0], "فِي البِدَايَةِ", "فِي النِّهَايَةِ"), (mot_fin, "فِي النِّهَايَةِ", "فِي البِدَايَةِ")]:
        sortie.append({"difficulte": 2, "enonce": f"أَيْنَ حَرْفُ {nom} فِي كَلِمَةِ «{mot}»؟ (فِي البِدَايَةِ / فِي النِّهَايَةِ)",
                       "reponses": [ou], "erreurs": {autre: "خطأ في موضع الحرف"},
                       "indice": "اِسْمَعِ الكَلِمَةَ: هَلْ تَسْمَعُ الحَرْفَ أَوَّلًا أَمْ آخِرًا؟",
                       "explication": f"حَرْفُ {nom} {ou} كَلِمَةِ «{mot}»."})
    return sortie


def main() -> None:
    texte = FICHIER.read_text(encoding="utf-8")
    entete = "".join(l for l in texte.splitlines(keepends=True) if l.startswith("#"))
    donnees = yaml.safe_load(texte)
    par_notion = {v: k for k, v in NOTION.items()}
    total = 0
    for numero, notion in enumerate(donnees["notions"], start=1):
        lettre = par_notion[notion["notion"]]
        manuels = notion["exercices"][:3]
        deja = {e["enonce"] for e in manuels}
        nouveaux = [e for e in exercices_generes(lettre, confusions(notion)) if e["enonce"] not in deja]
        for i, ex in enumerate(nouveaux, start=len(manuels) + 1):
            ex["id"] = f"cp-{numero:02d}-{i}"
        notion["exercices"] = manuels + [{"id": e.pop("id"), **e} for e in nouveaux]
        total += len(notion["exercices"])
    corps = yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=1000)
    FICHIER.write_text(entete + "\n" + corps, encoding="utf-8")
    print(f"{len(donnees['notions'])} lettres, {total} exercices.")


if __name__ == "__main__":
    main()
