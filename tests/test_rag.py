"""Phase 3 : indexation de docs/ et recherche des passages (lire_programme)."""

import sqlite3
import zipfile
from pathlib import Path

import pytest

from agent.tools import Contexte, executer
from rag.arabe import normaliser, racine_legere, requete_fts
from rag.ingest import decouper, indexer, niveau_du_chemin
from rag.search import chercher

SCHEMA = Path("db/schema.sql").read_text(encoding="utf-8")


@pytest.fixture
def base():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@pytest.fixture
def base_indexee(base):
    indexer(base, Path("docs"))
    return base


# --- Arabe ---------------------------------------------------------------------

def test_normalisation_ignore_voyelles_hamza_et_ta_marbuta():
    assert normaliser("الفَاعِلُ") == normaliser("الفاعل")
    assert normaliser("أَرْنَبٌ") == normaliser("ارنب")
    assert normaliser("دَجَاجَةٌ") == normaliser("دجاجه")


def test_prefixes_retires():
    assert racine_legere("والفاعل") == "فاعل"
    assert racine_legere("الباء") == "باء"
    assert racine_legere("بال") == "بال"  # mot trop court : inchangé
    assert requete_fts("ما هو ؟") is None  # seulement des mots vides


# --- Découpage et niveaux ------------------------------------------------------

def test_decoupage_par_sections():
    texte = "# Doc\nintro\n## A\ntexte a\n### A1\ntexte a1\n## B\ntexte b\n"
    assert decouper(texte) == [("Doc", "intro"), ("A", "texte a"), ("A › A1", "texte a1"), ("B", "texte b")]


def test_passages_trop_longs_recoupes():
    texte = "## Long\n" + "\n\n".join("ا" * 600 for _ in range(5))
    passages = decouper(texte)
    assert len(passages) > 1 and all(len(t) <= 1500 for _, t in passages)


def test_niveau_deduit_du_nom():
    assert niveau_du_chemin(Path("programmes/cp_arabe.md")) == "P1"
    assert niveau_du_chemin(Path("cours/1ac_dawra1.md")) == "P2"
    assert niveau_du_chemin(Path("cours/P2/redaction.md")) == "P2"
    assert niveau_du_chemin(Path("cours/2ac_ancien.md")) == "tous"  # niveau abandonné
    assert niveau_du_chemin(Path("pedagogie.md")) == "tous"
    assert niveau_du_chemin(Path("cours/capitale.md")) == "tous"  # « cp » doit être un mot entier


# --- Recherche sur les vrais documents -----------------------------------------

@pytest.mark.parametrize("question, section", [
    ("حرف الباء", "حرف الباء (ب)"),
    ("الثَّاء", "حرف الثاء (ث)"),
    ("حرف الضاد", "حرف الضاد (ض)"),
])
def test_trois_notions_du_cp(base_indexee, question, section):
    resultats = chercher(base_indexee, question, "P1")
    assert section in resultats[0]["reference"]
    assert resultats[0]["reference"].startswith("docs/programmes/cp_arabe.md")


def test_notion_1ac(base_indexee):
    resultats = chercher(base_indexee, "والميزانُ الصَّرْفِيُّ", "P2")
    assert resultats[0]["reference"] == "docs/cours/1ac_dawra1.md — الميزان الصرفي والمجرد والمزيد"
    assert "الفاء والعين واللام" in resultats[0]["texte"]


def test_niveau_respecte(base_indexee):
    # Un élève de 1AC ne reçoit pas les fiches du CP, et inversement.
    assert all("cp_arabe" not in r["reference"] for r in chercher(base_indexee, "حرف الباء", "P2"))
    assert chercher(base_indexee, "النكرة والمعرفة", "P1") == [] or all(
        "1ac" not in r["reference"] for r in chercher(base_indexee, "النكرة والمعرفة", "P1"))


def test_reindexation_sans_doublons(base_indexee):
    n = base_indexee.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    indexer(base_indexee, Path("docs"))
    assert base_indexee.execute("SELECT COUNT(*) FROM passages").fetchone()[0] == n
    assert base_indexee.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0] == n


def test_document_word(base, tmp_path):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (f'<w:document xmlns:w="{w}"><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>المبتدأ والخبر</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>المبتدأ اسم مرفوع نبدأ به الجملة الاسمية.</w:t></w:r></w:p>'
           '</w:body></w:document>')
    docs = tmp_path / "docs" / "cours"
    docs.mkdir(parents=True)
    with zipfile.ZipFile(docs / "1ac_mobtada.docx", "w") as z:
        z.writestr("word/document.xml", xml)
    assert indexer(base, tmp_path / "docs") == 1
    r = chercher(base, "المبتدأ", "P2")
    assert r[0]["reference"] == "docs/cours/1ac_mobtada.docx — المبتدأ والخبر"


# --- L'outil lire_programme ----------------------------------------------------

def test_lire_programme_cite_ses_sources(base_indexee):
    ctx = Contexte(db=base_indexee, eleve_id=1, seance_id=None, profil="P2")
    sortie = executer(ctx, "lire_programme", {"notion": "إعراب الفعل المضارع"})
    assert sortie["passages"][0]["reference"].startswith("docs/cours/1ac_dawra1.md — إعراب الفعل المضارع")


def test_lire_programme_sans_resultat(base_indexee):
    ctx = Contexte(db=base_indexee, eleve_id=1, seance_id=None, profil="P2")
    sortie = executer(ctx, "lire_programme", {"notion": "البلاغة والعروض"})
    assert sortie["passages"] == [] and "Aucun passage" in sortie["message"]


def test_le_cours_passe_avant_la_liste_du_programme(base_indexee):
    # Le titre de section pèse plus : le cours « إعراب الفعل المضارع » passe devant la liste des leçons.
    resultats = chercher(base_indexee, "إعراب الفعل المضارع", "P2")
    assert resultats[0]["reference"].startswith("docs/cours/1ac_dawra1.md — إعراب الفعل المضارع")
    assert any("1ac_arabe.md" in r["reference"] for r in resultats)  # le programme reste trouvable


@pytest.mark.parametrize("question, lecon", [
    ("الضمير المتصل", "الضمير المتصل"),
    ("الاسم الموصول", "الاسم الموصول"),
    ("ظن وأخواتها", "أصلهما مبتدأ وخبر"),
    ("المبني للمجهول", "المبني للمجهول وأحكامه"),
    ("الفعل الأجوف", "المثال والأجوف"),
    ("جزم المضارع", "إعراب الفعل المضارع: جزمه"),
    ("اللفيف المفروق", "اللفيف المفروق واللفيف المقرون"),
])
def test_lecons_de_1ac_retrouvees(base_indexee, question, lecon):
    reference = chercher(base_indexee, question, "P2")[0]["reference"]
    assert reference.startswith("docs/cours/1ac_dawra") and lecon in reference


def test_les_23_lecons_de_1ac_ont_un_cours():
    titres = [l[3:].strip() for f in ("docs/cours/1ac_dawra1.md", "docs/cours/1ac_dawra2.md")
              for l in Path(f).read_text(encoding="utf-8").splitlines() if l.startswith("## ")]
    assert len(titres) == 23


def test_chaque_notion_a_exercices_a_un_cours(base_indexee):
    from agent.tools.donnees_exemple import NOTIONS

    for notion in NOTIONS:
        passages = chercher(base_indexee, notion, "P2")
        assert passages and passages[0]["reference"].startswith("docs/cours/1ac_dawra"), notion
