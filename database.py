import psycopg
from psycopg.types.json import Json


def get_connection():
    connection = psycopg.connect(
        host="localhost",
        port=5432,
        dbname="cv_ai",
        user="postgres"
    )

    return connection


# ============================================================
# CANDIDATS
# ============================================================

def enregistrer_candidat(candidat, cv_filename):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO candidats
        (
            nom,
            email,
            telephone,
            adresse,
            profil,
            cv_filename
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        candidat.get("nom", ""),
        candidat.get("email", ""),
        candidat.get("telephone", ""),
        candidat.get("adresse", ""),
        candidat.get("profil", ""),
        cv_filename
    ))

    candidat_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()

    return candidat_id


def mettre_a_jour_candidat(candidat_id, candidat, cv_filename):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE candidats
        SET
            nom = %s,
            email = %s,
            telephone = %s,
            adresse = %s,
            profil = %s,
            cv_filename = %s,
            date_analyse = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (
        candidat.get("nom", ""),
        candidat.get("email", ""),
        candidat.get("telephone", ""),
        candidat.get("adresse", ""),
        candidat.get("profil", ""),
        cv_filename,
        candidat_id
    ))

    connection.commit()

    cursor.close()
    connection.close()


def candidat_existe(email):

    if not email:
        return None

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM candidats
        WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
        LIMIT 1
    """, (
        email,
    ))

    resultat = cursor.fetchone()

    cursor.close()
    connection.close()

    if resultat:
        return resultat[0]

    return None


# ============================================================
# FORMATIONS
# ============================================================

def enregistrer_formations(candidat_id, formations):

    if not formations:
        return

    connection = get_connection()
    cursor = connection.cursor()

    for formation in formations:

        cursor.execute("""
            INSERT INTO formations
            (
                candidat_id,
                diplome,
                etablissement,
                annee_debut,
                annee_fin
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            candidat_id,
            formation.get("diplome", ""),
            formation.get("etablissement", ""),
            formation.get("annee_debut", ""),
            formation.get("annee_fin", "")
        ))

    connection.commit()

    cursor.close()
    connection.close()


def supprimer_formations_candidat(candidat_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM formations
        WHERE candidat_id = %s
    """, (
        candidat_id,
    ))

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# EXPERIENCES
# ============================================================

def enregistrer_experiences(candidat_id, experiences):

    if not experiences:
        return

    connection = get_connection()
    cursor = connection.cursor()

    for experience in experiences:

        cursor.execute("""
            INSERT INTO experiences
            (
                candidat_id,
                poste,
                entreprise,
                date_debut,
                date_fin,
                description
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            candidat_id,
            experience.get("poste", ""),
            experience.get("entreprise", ""),
            experience.get("date_debut", ""),
            experience.get("date_fin", ""),
            experience.get("description", "")
        ))

    connection.commit()

    cursor.close()
    connection.close()


def supprimer_experiences_candidat(candidat_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM experiences
        WHERE candidat_id = %s
    """, (
        candidat_id,
    ))

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# COMPETENCES
# ============================================================

def enregistrer_competences(candidat_id, competences):

    if not competences:
        return

    connection = get_connection()
    cursor = connection.cursor()

    for competence in competences:

        if not competence:
            continue

        cursor.execute("""
            INSERT INTO competences
            (
                candidat_id,
                competence
            )
            VALUES (%s, %s)
        """, (
            candidat_id,
            competence
        ))

    connection.commit()

    cursor.close()
    connection.close()


def supprimer_competences_candidat(candidat_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM competences
        WHERE candidat_id = %s
    """, (
        candidat_id,
    ))

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# LANGUES
# ============================================================

def enregistrer_langues(candidat_id, langues):

    if not langues:
        return

    connection = get_connection()
    cursor = connection.cursor()

    for langue in langues:

        cursor.execute("""
            INSERT INTO langues
            (
                candidat_id,
                langue,
                niveau
            )
            VALUES (%s, %s, %s)
        """, (
            candidat_id,
            langue.get("langue", ""),
            langue.get("niveau", "")
        ))

    connection.commit()

    cursor.close()
    connection.close()


def supprimer_langues_candidat(candidat_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM langues
        WHERE candidat_id = %s
    """, (
        candidat_id,
    ))

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# RECUPERER UN CANDIDAT
# ============================================================

def recuperer_candidat(candidat_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            nom,
            email,
            telephone,
            adresse,
            profil,
            cv_filename,
            date_analyse
        FROM candidats
        WHERE id = %s
    """, (
        candidat_id,
    ))

    candidat = cursor.fetchone()

    if candidat is None:

        cursor.close()
        connection.close()

        return None

    resultat = {
        "id": candidat[0],
        "nom": candidat[1],
        "email": candidat[2],
        "telephone": candidat[3],
        "adresse": candidat[4],
        "profil": candidat[5],
        "cv_filename": candidat[6],
        "date_analyse": candidat[7],
        "formations": [],
        "experiences": [],
        "competences": [],
        "langues": []
    }

    # -------------------------
    # FORMATIONS
    # -------------------------

    cursor.execute("""
        SELECT
            diplome,
            etablissement,
            annee_debut,
            annee_fin
        FROM formations
        WHERE candidat_id = %s
        ORDER BY id
    """, (
        candidat_id,
    ))

    for formation in cursor.fetchall():

        resultat["formations"].append({
            "diplome": formation[0],
            "etablissement": formation[1],
            "annee_debut": formation[2],
            "annee_fin": formation[3]
        })

    # -------------------------
    # EXPERIENCES
    # -------------------------

    cursor.execute("""
        SELECT
            poste,
            entreprise,
            date_debut,
            date_fin,
            description
        FROM experiences
        WHERE candidat_id = %s
        ORDER BY id
    """, (
        candidat_id,
    ))

    for experience in cursor.fetchall():

        resultat["experiences"].append({
            "poste": experience[0],
            "entreprise": experience[1],
            "date_debut": experience[2],
            "date_fin": experience[3],
            "description": experience[4]
        })

    # -------------------------
    # COMPETENCES
    # -------------------------

    cursor.execute("""
        SELECT
            competence
        FROM competences
        WHERE candidat_id = %s
        ORDER BY id
    """, (
        candidat_id,
    ))

    for competence in cursor.fetchall():

        resultat["competences"].append(
            competence[0]
        )

    # -------------------------
    # LANGUES
    # -------------------------

    cursor.execute("""
        SELECT
            langue,
            niveau
        FROM langues
        WHERE candidat_id = %s
        ORDER BY id
    """, (
        candidat_id,
    ))

    for langue in cursor.fetchall():

        resultat["langues"].append({
            "langue": langue[0],
            "niveau": langue[1]
        })

    cursor.close()
    connection.close()

    return resultat


# ============================================================
# LISTE DES CANDIDATS
# ============================================================

def lister_candidats():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            nom,
            email,
            telephone,
            cv_filename,
            date_analyse
        FROM candidats
        ORDER BY date_analyse DESC
    """)

    candidats = cursor.fetchall()

    cursor.close()
    connection.close()

    resultat = []

    for candidat in candidats:

        resultat.append({
            "id": candidat[0],
            "nom": candidat[1],
            "email": candidat[2],
            "telephone": candidat[3],
            "cv_filename": candidat[4],
            "date_analyse": candidat[5]
        })

    return resultat


def lister_candidats_complets():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM candidats
        ORDER BY id
    """)

    candidats = cursor.fetchall()

    cursor.close()
    connection.close()

    resultats = []

    for candidat in candidats:

        candidat_complet = recuperer_candidat(
            candidat[0]
        )

        if candidat_complet is not None:

            resultats.append(
                candidat_complet
            )

    return resultats


# ============================================================
# RECHERCHE CANDIDATS
# ============================================================

def rechercher_candidats(recherche):

    connection = get_connection()
    cursor = connection.cursor()

    terme = "%" + recherche + "%"

    cursor.execute("""
        SELECT DISTINCT
            c.id,
            c.nom,
            c.email,
            c.telephone,
            c.cv_filename,
            c.date_analyse
        FROM candidats c

        LEFT JOIN competences comp
            ON comp.candidat_id = c.id

        LEFT JOIN formations f
            ON f.candidat_id = c.id

        LEFT JOIN experiences e
            ON e.candidat_id = c.id

        WHERE
            c.nom ILIKE %s
            OR c.email ILIKE %s
            OR c.telephone ILIKE %s
            OR c.adresse ILIKE %s
            OR c.profil ILIKE %s
            OR comp.competence ILIKE %s
            OR f.diplome ILIKE %s
            OR f.etablissement ILIKE %s
            OR e.poste ILIKE %s
            OR e.entreprise ILIKE %s
            OR e.description ILIKE %s

        ORDER BY c.date_analyse DESC
    """, (
        terme,
        terme,
        terme,
        terme,
        terme,
        terme,
        terme,
        terme,
        terme,
        terme,
        terme
    ))

    candidats = cursor.fetchall()

    cursor.close()
    connection.close()

    resultat = []

    for candidat in candidats:

        resultat.append({
            "id": candidat[0],
            "nom": candidat[1],
            "email": candidat[2],
            "telephone": candidat[3],
            "cv_filename": candidat[4],
            "date_analyse": candidat[5]
        })

    return resultat


# ============================================================
# OFFRES
# ============================================================

def enregistrer_offre(offre):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO offres (
            titre,
            entreprise,
            description,
            missions,
            competences_obligatoires,
            competences_souhaitees,
            niveau_etude,
            experience,
            type_contrat,
            localisation,
            salaire,
            langues,
            date_limite,
            statut
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        RETURNING id
    """, (
        offre.get("titre"),
        offre.get("entreprise"),
        offre.get("description"),
        offre.get("missions"),
        offre.get("competences_obligatoires"),
        offre.get("competences_souhaitees"),
        offre.get("niveau_etude"),
        offre.get("experience"),
        offre.get("type_contrat"),
        offre.get("localisation"),
        offre.get("salaire"),
        offre.get("langues"),
        offre.get("date_limite"),
        offre.get("statut", "active")
    ))

    offre_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()

    return offre_id


def lister_offres():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            titre,
            entreprise,
            description,
            missions,
            competences_obligatoires,
            competences_souhaitees,
            niveau_etude,
            experience,
            type_contrat,
            localisation,
            salaire,
            langues,
            date_limite,
            statut,
            date_creation
        FROM offres
        ORDER BY date_creation DESC
    """)

    resultats = cursor.fetchall()

    cursor.close()
    connection.close()

    offres = []

    for ligne in resultats:

        offres.append({
            "id": ligne[0],
            "titre": ligne[1],
            "entreprise": ligne[2],
            "description": ligne[3],
            "missions": ligne[4],
            "competences_obligatoires": ligne[5],
            "competences_souhaitees": ligne[6],
            "niveau_etude": ligne[7],
            "experience": ligne[8],
            "type_contrat": ligne[9],
            "localisation": ligne[10],
            "salaire": ligne[11],
            "langues": ligne[12],
            "date_limite": ligne[13],
            "statut": ligne[14],
            "date_creation": ligne[15]
        })

    return offres


def recuperer_offre(offre_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            titre,
            entreprise,
            description,
            missions,
            competences_obligatoires,
            competences_souhaitees,
            niveau_etude,
            experience,
            type_contrat,
            localisation,
            salaire,
            langues,
            date_limite,
            statut,
            date_creation
        FROM offres
        WHERE id = %s
    """, (
        offre_id,
    ))

    offre = cursor.fetchone()

    cursor.close()
    connection.close()

    if offre is None:
        return None

    return {
        "id": offre[0],
        "titre": offre[1],
        "entreprise": offre[2],
        "description": offre[3],
        "missions": offre[4],
        "competences_obligatoires": offre[5],
        "competences_souhaitees": offre[6],
        "niveau_etude": offre[7],
        "experience": offre[8],
        "type_contrat": offre[9],
        "localisation": offre[10],
        "salaire": offre[11],
        "langues": offre[12],
        "date_limite": offre[13],
        "statut": offre[14],
        "date_creation": offre[15]
    }


# ============================================================
# MATCHING
# ============================================================

def enregistrer_matching(matching):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO matching_candidats_offres (
            candidat_id,
            offre_id,
            score,
            statut,
            competences_correspondantes,
            competences_manquantes,
            analyse_ia,
            details_matching,
            date_analyse
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (
            candidat_id,
            offre_id
        )
        DO UPDATE SET
            score = EXCLUDED.score,
            statut = EXCLUDED.statut,
            competences_correspondantes =
                EXCLUDED.competences_correspondantes,
            competences_manquantes =
                EXCLUDED.competences_manquantes,
            analyse_ia =
                EXCLUDED.analyse_ia,
            details_matching =
                EXCLUDED.details_matching,
            date_analyse =
                CURRENT_TIMESTAMP
        RETURNING id
    """, (
        matching["candidat_id"],
        matching["offre_id"],
        matching.get("score"),
        matching.get("statut", "non_analyse"),
        matching.get("competences_correspondantes", ""),
        matching.get("competences_manquantes", ""),
        matching.get("analyse_ia", ""),
        Json(
            matching.get(
                "details_matching",
                {}
            )
        )
    ))

    matching_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()

    return matching_id


def lister_matchings_offre(offre_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            m.id,
            m.candidat_id,
            c.nom,
            c.email,
            m.offre_id,
            m.score,
            m.statut,
            m.competences_correspondantes,
            m.competences_manquantes,
            m.analyse_ia,
            m.details_matching,
            m.date_analyse
        FROM matching_candidats_offres m

        INNER JOIN candidats c
            ON c.id = m.candidat_id

        WHERE m.offre_id = %s

        ORDER BY m.score DESC NULLS LAST
    """, (
        offre_id,
    ))

    resultats = cursor.fetchall()

    cursor.close()
    connection.close()

    matchings = []

    for ligne in resultats:

        matchings.append({
            "id": ligne[0],
            "candidat_id": ligne[1],
            "candidat_nom": ligne[2],
            "candidat_email": ligne[3],
            "offre_id": ligne[4],
            "score": float(ligne[5])
                if ligne[5] is not None
                else None,
            "statut": ligne[6],
            "competences_correspondantes": ligne[7],
            "competences_manquantes": ligne[8],
            "analyse_ia": ligne[9],
            "details_matching": ligne[10],
            "date_analyse": ligne[11]
        })

    return matchings