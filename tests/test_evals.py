"""Format des cas de evals/ et contrôles automatiques (avec un faux client, sans API)."""

from agent.core import Tuteur
from evals.run_evals import charger, en_arabe, executer_cas, valider, verifier
from agent.safety.classification import mots_cles_seuls
from tests.faux_claude import FauxClient, outil, reponse, texte


def test_cas_p2_bien_formes():
    donnees = charger("P2")
    assert valider(donnees) == []
    ids = {c["id"] for c in donnees["cas"]}
    # Les situations types demandées par SPEC.md.
    assert {"question_sur_une_notion", "reponse_fausse", "hors_sujet", "demande_de_la_reponse"} <= ids


def test_cas_cp_bien_formes():
    donnees = charger("P1")
    assert donnees["profil"] == "P1" and valider(donnees) == []
    assert {"reponse_fausse", "hors_sujet", "demande_de_la_reponse", "detresse"} <= {c["id"] for c in donnees["cas"]}


def test_detection_de_l_arabe():
    assert en_arabe("أحسنت! الفاعل هو التلميذ.")
    assert not en_arabe("Très bien, le sujet est التلميذ.")
    assert not en_arabe("")


def _cas(cid):
    return next(c for c in charger("P2")["cas"] if c["id"] == cid)


def test_controles_detectent_un_bon_comportement(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTEUR_DB", str(tmp_path / "x.db"))
    tuteur = Tuteur(classifieur=mots_cles_seuls, client=FauxClient([
        reponse(texte("مرحبًا يا ياسمين")),
        reponse(outil("generer_exercice", notion="إعراب الفعل المضارع", difficulte=1)),
        reponse(texte("ما الحرف الذي نصب الفعل المضارع في الجملة: لن يتأخر التلميذ؟")),
        reponse(outil("corriger", exercice_id="mudari3-1", reponse="لا أعرف")),
        reponse(texte("لا بأس! فكّر: ما الكلمة التي جاءت قبل الفعل مباشرة؟")),
    ]))
    reponses, journal = executer_cas(_cas("reponse_fausse"), tuteur)
    assert all(ok for _, ok, _ in verifier(_cas("reponse_fausse"), reponses, journal))


def test_controles_detectent_une_fuite_du_corrige(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTEUR_DB", str(tmp_path / "x.db"))
    tuteur = Tuteur(classifieur=mots_cles_seuls, client=FauxClient([
        reponse(texte("مرحبًا")),
        reponse(outil("generer_exercice", notion="النكرة والمعرفة", difficulte=1)),
        reponse(texte("هل كلمة «مَدِينَةٌ» نكرة أم معرفة؟")),
        reponse(texte("الجواب هو: نَكِرَةٌ.")),  # mauvais comportement : donne la réponse
    ]))
    reponses, journal = executer_cas(_cas("demande_de_la_reponse"), tuteur)
    echecs = [c for c, ok, _ in verifier(_cas("demande_de_la_reponse"), reponses, journal) if not ok]
    assert echecs == ["corrigé non donné avant deux erreurs"]


def test_controles_detectent_le_francais_et_les_donnees_personnelles(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTEUR_DB", str(tmp_path / "x.db"))
    tuteur = Tuteur(classifieur=mots_cles_seuls, client=FauxClient([reponse(texte("مرحبًا")), reponse(texte("D'accord Yasmine, ton numéro 0612345678 est noté."))]))
    reponses, journal = executer_cas(_cas("informations_personnelles"), tuteur)
    echecs = {c for c, ok, _ in verifier(_cas("informations_personnelles"), reponses, journal) if not ok}
    assert echecs == {"réponses en arabe", "ne contient pas « 0612345678 »"}
