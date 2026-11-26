-- Schéma de la base du tuteur IA.
-- Données minimales (public mineur) : pour l'élève, uniquement prénom, profil et résultats.
-- Toutes les dates sont en UTC, au format ISO 8601 (AAAA-MM-JJTHH:MM:SS+00:00).

PRAGMA foreign_keys = ON;

-- Comptes parents.
CREATE TABLE IF NOT EXISTS parents (
    id                INTEGER PRIMARY KEY,
    email             TEXT    NOT NULL UNIQUE,
    mot_de_passe_hash TEXT    NOT NULL,
    consentement_le   TEXT    NOT NULL,          -- date du consentement donné à l'inscription
    cree_le           TEXT    NOT NULL
);

-- Sous-comptes élèves : ni e-mail, ni mot de passe, ni nom de famille.
CREATE TABLE IF NOT EXISTS eleves (
    id        INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
    prenom    TEXT    NOT NULL CHECK (length(prenom) BETWEEN 1 AND 30),
    profil    TEXT    NOT NULL CHECK (profil IN ('P1', 'P2')),  -- style : P1 enfant, P2 adolescent
    palier    TEXT,                            -- identifiant du palier dans le parcours (NULL : pas encore positionné)
    exercices_par_seance INTEGER NOT NULL DEFAULT 10,  -- nombre proposé à l'enfant, réglé par le parent
    cree_le   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eleves_parent ON eleves(parent_id);

-- Notions du programme (arabe uniquement).
CREATE TABLE IF NOT EXISTS notions (
    id                  INTEGER PRIMARY KEY,
    matiere             TEXT NOT NULL DEFAULT 'arabe' CHECK (matiere = 'arabe'),
    niveau              TEXT NOT NULL CHECK (niveau IN ('P1', 'P2')),
    intitule            TEXT NOT NULL,
    reference_programme TEXT,                     -- lien vers le passage du programme
    UNIQUE (niveau, intitule)
);

-- Séances de travail.
CREATE TABLE IF NOT EXISTS seances (
    id       INTEGER PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    debut    TEXT    NOT NULL,
    fin      TEXT,
    fin_raison TEXT CHECK (fin_raison IN ('eleve', 'temps', 'nouvelle')),  -- qui a terminé la séance
    journal  TEXT    NOT NULL DEFAULT '[]',       -- échanges au format JSON, consultables par le parent
    tokens_entree INTEGER NOT NULL DEFAULT 0,     -- consommation de l'API, pour mesurer le coût
    tokens_sortie INTEGER NOT NULL DEFAULT 0,
    cout_dollars REAL NOT NULL DEFAULT 0,         -- coût réel en dollars (cache compris)
    -- Séance sans IA (agent/seance_locale.py) : mode 'local', nombre d'exercices choisi, exercice en cours,
    -- aide déjà donnée sur cet exercice (0 rien, 1 indice, 2 explication), exercices terminés.
    mode TEXT NOT NULL DEFAULT 'ia' CHECK (mode IN ('ia', 'local')),
    objectif INTEGER,
    exercice_en_cours TEXT,
    aide_donnee INTEGER NOT NULL DEFAULT 0,
    exercices_faits INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_seances_eleve ON seances(eleve_id);

-- Chaque réponse de l'élève à un exercice.
CREATE TABLE IF NOT EXISTS tentatives (
    id          INTEGER PRIMARY KEY,
    eleve_id    INTEGER NOT NULL REFERENCES eleves(id)  ON DELETE CASCADE,
    notion_id   INTEGER NOT NULL REFERENCES notions(id),
    seance_id   INTEGER          REFERENCES seances(id) ON DELETE SET NULL,
    exercice    TEXT    NOT NULL,                 -- identifiant de l'exercice (banque d'exercices)
    reponse     TEXT    NOT NULL,
    verdict     TEXT    NOT NULL CHECK (verdict IN ('juste', 'partiel', 'faux')),
    type_erreur TEXT,
    cree_le     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tentatives_eleve ON tentatives(eleve_id, cree_le);

-- Niveau de maîtrise par notion et date de prochaine révision (répétition espacée).
CREATE TABLE IF NOT EXISTS maitrise (
    eleve_id           INTEGER NOT NULL REFERENCES eleves(id)  ON DELETE CASCADE,
    notion_id          INTEGER NOT NULL REFERENCES notions(id),
    niveau             REAL    NOT NULL DEFAULT 0 CHECK (niveau BETWEEN 0 AND 1),
    prochaine_revision TEXT,
    PRIMARY KEY (eleve_id, notion_id)
);

-- Tests de positionnement et de passage de palier (sans l'agent : correction automatique).
CREATE TABLE IF NOT EXISTS tests_palier (
    id              INTEGER PRIMARY KEY,
    eleve_id        INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    type            TEXT    NOT NULL CHECK (type IN ('positionnement', 'passage')),
    etat            TEXT    NOT NULL,              -- JSON : questions, réponses, palier en cours
    statut          TEXT    NOT NULL CHECK (statut IN ('en_cours', 'a_confirmer', 'echoue', 'confirme', 'refuse', 'abandonne')),
    palier_propose  TEXT,                          -- identifiant du palier proposé, si le parent confirme
    score           REAL,
    cree_le         TEXT    NOT NULL,
    fini_le         TEXT
);
CREATE INDEX IF NOT EXISTS idx_tests_eleve ON tests_palier(eleve_id, statut);

-- Alertes pour le parent (détresse exprimée par l'élève).
CREATE TABLE IF NOT EXISTS alertes (
    id        INTEGER PRIMARY KEY,
    eleve_id  INTEGER NOT NULL REFERENCES eleves(id)  ON DELETE CASCADE,
    seance_id INTEGER          REFERENCES seances(id) ON DELETE SET NULL,
    type      TEXT    NOT NULL CHECK (type IN ('detresse')),
    extrait   TEXT    NOT NULL,                   -- message de l'élève (données personnelles masquées)
    cree_le   TEXT    NOT NULL,
    vue_le    TEXT                                -- date de lecture par le parent
);
CREATE INDEX IF NOT EXISTS idx_alertes_eleve ON alertes(eleve_id, vue_le);

-- Bilans envoyés aux parents.
CREATE TABLE IF NOT EXISTS rapports (
    id            INTEGER PRIMARY KEY,
    eleve_id      INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    periode_debut TEXT    NOT NULL,
    periode_fin   TEXT    NOT NULL,
    texte         TEXT    NOT NULL,
    cree_le       TEXT    NOT NULL
);

-- Tables techniques ---------------------------------------------------------

-- Connexions ouvertes (parent ou appareil d'un élève). Seule l'empreinte du jeton est stockée.
CREATE TABLE IF NOT EXISTS connexions (
    jeton_hash TEXT    PRIMARY KEY,
    parent_id  INTEGER REFERENCES parents(id) ON DELETE CASCADE,
    eleve_id   INTEGER REFERENCES eleves(id)  ON DELETE CASCADE,
    expire_le  TEXT    NOT NULL,
    CHECK ((parent_id IS NULL) <> (eleve_id IS NULL))
);

-- Code d'accès à 6 chiffres, à usage unique, pour relier l'appareil d'un élève.
-- Un seul code actif par élève : en générer un nouveau remplace l'ancien.
CREATE TABLE IF NOT EXISTS codes_acces (
    eleve_id  INTEGER PRIMARY KEY REFERENCES eleves(id) ON DELETE CASCADE,
    code_hash TEXT    NOT NULL UNIQUE,
    expire_le TEXT    NOT NULL
);

-- Essais de connexion échoués, pour limiter les tentatives répétées.
CREATE TABLE IF NOT EXISTS essais_echoues (
    cle    TEXT NOT NULL,                         -- ex. « code:<adresse IP> » ou « parent:<email> »
    moment TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_essais_cle ON essais_echoues(cle, moment);

-- Passages des programmes et des cours (docs/), reconstruits à chaque indexation (rag/ingest.py).
CREATE TABLE IF NOT EXISTS passages (
    id      INTEGER PRIMARY KEY,
    source  TEXT NOT NULL,                        -- fichier, ex. docs/programmes/cp_arabe.md
    titre   TEXT NOT NULL,                        -- titres de section, ex. « 5. Fiches › 2. حرف الباء »
    niveau  TEXT NOT NULL CHECK (niveau IN ('P1', 'P2', 'tous')),
    texte   TEXT NOT NULL,
    version TEXT NOT NULL                         -- empreinte du fichier indexé
);
-- Index de recherche plein texte (texte arabe normalisé : sans voyelles, sans préfixes).
-- Le titre de section a plus de poids que le texte dans le classement (voir rag/search.py).
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(titre, contenu);

-- Réponses de l'IA aux questions posées pendant une séance sans IA, réutilisées pour la même question
-- (texte normalisé) sur le même exercice : un appel payant n'est fait qu'une fois.
CREATE TABLE IF NOT EXISTS reponses_ia (
    exercice     TEXT    NOT NULL,
    question     TEXT    NOT NULL,
    reponse      TEXT    NOT NULL,
    utilisations INTEGER NOT NULL DEFAULT 0,
    cree_le      TEXT    NOT NULL,
    PRIMARY KEY (exercice, question)
);

-- Appareil de la famille (ordinateur ou tablette de la maison) : autorisé une fois par le parent, il affiche
-- les prénoms des enfants ; chaque enfant entre en touchant son prénom, sans code. Ne donne aucun droit parent.
CREATE TABLE IF NOT EXISTS appareils_famille (
    jeton_hash TEXT    PRIMARY KEY,
    parent_id  INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
    expire_le  TEXT    NOT NULL
);
