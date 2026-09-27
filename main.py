from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor



import pymupdf
import os

# from ai import analyser_cv

from ai import (
    analyser_cv,
    analyser_matching
)



from database import (
    get_connection,
    enregistrer_candidat,
    mettre_a_jour_candidat,
    enregistrer_formations,
    enregistrer_experiences,
    enregistrer_competences,
    enregistrer_langues,
    supprimer_formations_candidat,
    supprimer_experiences_candidat,
    supprimer_competences_candidat,
    supprimer_langues_candidat,
    lister_candidats,
    lister_candidats_complets,
    recuperer_candidat,
    rechercher_candidats,
    candidat_existe,
    enregistrer_offre,
    lister_offres,
    recuperer_offre,
    enregistrer_matching,
    lister_matchings_offre
)







app = FastAPI()

UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

templates = Jinja2Templates(directory="templates")


class OffreCreate(BaseModel):
    titre: str
    description: str


@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/dashboard/stats")
async def dashboard_stats():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM candidats")
    total_candidats = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM candidats WHERE cv_filename IS NOT NULL AND cv_filename <> ''")
    total_cv_analyzes = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM offres")
    total_offres = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM matching_candidats_offres")
    total_matchings = cursor.fetchone()[0] or 0

    cursor.close()
    connection.close()

    return {
        "success": True,
        "stats": {
            "total_candidats": total_candidats,
            "total_cv_analyzes": total_cv_analyzes,
            "total_offres": total_offres,
            "total_matchings": total_matchings,
        }
    }


@app.get("/api/dashboard/matchings")
async def dashboard_matchings():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            CASE
                WHEN score >= 90 THEN '90-100'
                WHEN score >= 75 THEN '75-89'
                WHEN score >= 50 THEN '50-74'
                ELSE '0-49'
            END AS bucket,
            COUNT(*) AS total
        FROM matching_candidats_offres
        WHERE score IS NOT NULL
        GROUP BY bucket
        ORDER BY MIN(score)
    """)

    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    labels = {
        '90-100': '90–100%',
        '75-89': '75–89%',
        '50-74': '50–74%',
        '0-49': '0–49%'
    }

    series = []
    for bucket, total in rows:
        series.append({
            "label": labels.get(bucket, bucket),
            "value": int(total)
        })

    ordered = ["90-100", "75-89", "50-74", "0-49"]
    final = []
    for bucket in ordered:
        existing = next((item for item in series if item["label"] == labels[bucket]), None)
        if existing:
            final.append(existing)

    if not final:
        final = [
            {"label": "0–49%", "value": 0},
            {"label": "50–74%", "value": 0},
            {"label": "75–89%", "value": 0},
            {"label": "90–100%", "value": 0},
        ]

    return {"success": True, "series": final}


@app.get("/api/dashboard/candidats-par-offre")
async def dashboard_candidats_par_offre():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT o.titre, COUNT(m.id) AS total
        FROM offres o
        LEFT JOIN matching_candidats_offres m
            ON m.offre_id = o.id
        GROUP BY o.id, o.titre
        ORDER BY total DESC, o.titre ASC
    """)

    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    series = []
    for titre, total in rows:
        series.append({
            "titre": titre or "Offre sans titre",
            "nombre": int(total or 0)
        })

    return {"success": True, "series": series}


@app.get("/api/dashboard/recent-analyses")
async def dashboard_recent_analyses():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            c.nom AS candidat,
            o.titre AS offre,
            m.score,
            m.date_analyse
        FROM matching_candidats_offres m
        LEFT JOIN candidats c ON c.id = m.candidat_id
        LEFT JOIN offres o ON o.id = m.offre_id
        ORDER BY m.date_analyse DESC NULLS LAST
        LIMIT 8
    """)

    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    analyses = []
    for candidat, offre, score, date_analyse in rows:
        analyses.append({
            "candidat": candidat or "—",
            "offre": offre or "—",
            "score": float(score) if score is not None else 0,
            "date_analyse": date_analyse
        })

    return {"success": True, "analyses": analyses}


@app.get("/offres-page", response_class=HTMLResponse)
async def page_offres(request: Request):
    return templates.TemplateResponse("offres.html", {"request": request})



@app.get(
    "/classement/{offre_id}",
    response_class=HTMLResponse
)
async def page_classement(
    request: Request,
    offre_id: int
):

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return HTMLResponse(
            content="Offre introuvable.",
            status_code=404
        )

    return templates.TemplateResponse(
        "classement.html",
        {
            "request": request,
            "offre_id": offre_id
        }
    )


@app.get(
    "/profil-candidat",
    response_class=HTMLResponse
)
async def page_profil_candidat(
    request: Request
):

    return templates.TemplateResponse(
        "profil_candidat.html",
        {
            "request": request
        }
    )


@app.post("/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        return {
            "success": False,
            "message": "Veuillez envoyer un fichier PDF.",
        }

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    content = await file.read()

    with open(file_path, "wb") as f:
        f.write(content)

    document = pymupdf.open(file_path)
    nombre_pages = len(document)

    texte = ""
    for page in document:
        texte += page.get_text()
        texte += "\n"

    document.close()

    resultat_ia = analyser_cv(texte)

    candidat_data = {
        "nom": resultat_ia.get("candidat", {}).get("nom", ""),
        "email": resultat_ia.get("candidat", {}).get("email", ""),
        "telephone": resultat_ia.get("candidat", {}).get("telephone", ""),
        "adresse": resultat_ia.get("candidat", {}).get("adresse", ""),
        "profil": resultat_ia.get("profil", "")
    }

    email = candidat_data.get("email", "").strip()

    candidat_id = None

    if email:
        candidat_id = candidat_existe(email)

    if candidat_id is None:

        candidat_id = enregistrer_candidat(
            candidat_data,
            file.filename
        )

    else:

        mettre_a_jour_candidat(
            candidat_id,
            candidat_data,
            file.filename
        )

        supprimer_formations_candidat(candidat_id)
        supprimer_experiences_candidat(candidat_id)
        supprimer_competences_candidat(candidat_id)
        supprimer_langues_candidat(candidat_id)

    enregistrer_formations(
        candidat_id,
        resultat_ia.get("formations", [])
    )

    enregistrer_experiences(
        candidat_id,
        resultat_ia.get("experiences", [])
    )

    enregistrer_competences(
        candidat_id,
        resultat_ia.get("competences", [])
    )

    enregistrer_langues(
        candidat_id,
        resultat_ia.get("langues", [])
    )

    return {
        "success": True,
        "filename": file.filename,
        "pages": nombre_pages,
        "text": texte,
        "candidat_id": candidat_id,
        "analyse_ia": resultat_ia,
    }


@app.get("/candidats")
async def candidats():
    liste = lister_candidats()

    return {
        "success": True,
        "candidats": liste,
    }


@app.get("/candidats/{candidat_id}")
async def candidat_detail(candidat_id: int):
    candidat = recuperer_candidat(candidat_id)

    if candidat is None:
        return {
            "success": False,
            "message": "Candidat introuvable.",
        }

    return {
        "success": True,
        "candidat": candidat,
    }


@app.delete("/candidats/{candidat_id}")
async def supprimer_candidat(candidat_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM candidats
        WHERE id = %s
    """, (candidat_id,))

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()
        return {
            "success": False,
            "message": "Candidat introuvable."
        }

    connection.commit()
    cursor.close()
    connection.close()

    return {
        "success": True,
        "message": "Candidat supprimé avec succès."
    }


@app.get("/rechercher")
async def rechercher(recherche: str = ""):
    recherche = recherche.strip()

    if recherche == "":
        return {
            "success": False,
            "message": "Veuillez saisir un terme de recherche.",
        }

    resultats = rechercher_candidats(recherche)

    return {
        "success": True,
        "recherche": recherche,
        "candidats": resultats,
    }


@app.get("/offres")
async def obtenir_offres():

    offres = lister_offres()

    return {
        "success": True,
        "offres": offres
    }

@app.get("/offres/{offre_id}")
async def obtenir_offre(offre_id: int):
    offres = lister_offres()

    for offre in offres:
        if offre["id"] == offre_id:
            return {
                "success": True,
                "offre": offre,
            }

    return {
        "success": False,
        "message": "Offre introuvable.",
    }


@app.put("/offres/{offre_id}")
async def modifier_offre(
    offre_id: int,

    titre: str = Form(...),

    entreprise: str = Form(""),

    description: str = Form(""),

    missions: str = Form(""),

    competences_obligatoires: str = Form(""),

    competences_souhaitees: str = Form(""),

    niveau_etude: str = Form(""),

    experience: str = Form(""),

    type_contrat: str = Form(""),

    localisation: str = Form(""),

    salaire: str = Form(""),

    langues: str = Form(""),

    date_limite: str = Form(""),

    statut: str = Form("active")
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE offres
        SET
            titre = %s,
            entreprise = %s,
            description = %s,
            missions = %s,
            competences_obligatoires = %s,
            competences_souhaitees = %s,
            niveau_etude = %s,
            experience = %s,
            type_contrat = %s,
            localisation = %s,
            salaire = %s,
            langues = %s,
            date_limite = %s,
            statut = %s
        WHERE id = %s
    """, (
        titre.strip(),
        entreprise.strip(),
        description.strip(),
        missions.strip(),
        competences_obligatoires.strip(),
        competences_souhaitees.strip(),
        niveau_etude.strip(),
        experience.strip(),
        type_contrat.strip(),
        localisation.strip(),
        salaire.strip(),
        langues.strip(),
        date_limite.strip()
        if date_limite.strip() != ""
        else None,
        statut.strip(),
        offre_id
    ))

    if cursor.rowcount == 0:

        cursor.close()
        connection.close()

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "success": True,
        "message": "Offre modifiée avec succès."
    }



@app.post("/offres")
async def creer_offre(

    titre: str = Form(...),

    entreprise: str = Form(""),

    description: str = Form(""),

    missions: str = Form(""),

    competences_obligatoires: str = Form(""),

    competences_souhaitees: str = Form(""),

    niveau_etude: str = Form(""),

    experience: str = Form(""),

    type_contrat: str = Form(""),

    localisation: str = Form(""),

    salaire: str = Form(""),

    langues: str = Form(""),

    date_limite: str = Form(""),

    statut: str = Form("active")

):

    titre = titre.strip()

    entreprise = entreprise.strip()

    description = description.strip()

    missions = missions.strip()

    competences_obligatoires = (
        competences_obligatoires.strip()
    )

    competences_souhaitees = (
        competences_souhaitees.strip()
    )

    niveau_etude = niveau_etude.strip()

    experience = experience.strip()

    type_contrat = type_contrat.strip()

    localisation = localisation.strip()

    salaire = salaire.strip()

    langues = langues.strip()

    date_limite = date_limite.strip()

    statut = statut.strip()


    if titre == "":

        return {
            "success": False,
            "message": "Le titre de l'offre est obligatoire."
        }


    offre = {

        "titre": titre,

        "entreprise": entreprise,

        "description": description,

        "missions": missions,

        "competences_obligatoires":
            competences_obligatoires,

        "competences_souhaitees":
            competences_souhaitees,

        "niveau_etude":
            niveau_etude,

        "experience":
            experience,

        "type_contrat":
            type_contrat,

        "localisation":
            localisation,

        "salaire":
            salaire,

        "langues":
            langues,

        "date_limite":
            date_limite
            if date_limite != ""
            else None,

        "statut":
            statut
            if statut != ""
            else "active"

    }


    offre_id = enregistrer_offre(
        offre
    )


    return {

        "success": True,

        "message":
            "Offre créée avec succès.",

        "offre_id":
            offre_id

    }

# @app.get("/offres-detail/{offre_id}", response_class=HTMLResponse)
# async def page_detail_offre(request: Request, offre_id: int):
#     return templates.TemplateResponse(
#         "offre_detail.html",
#         {
#             "request": request,
#             "offre_id": offre_id,
#         },
#     )

@app.get(
    "/offres-detail",
    response_class=HTMLResponse
)
async def page_detail_offre(
    request: Request
):

    return templates.TemplateResponse(
        "offre_detail.html",
        {
            "request": request
        }
    )

@app.get(
    "/offres-modifier",
    response_class=HTMLResponse
)
async def page_modifier_offre(
    request: Request
):

    return templates.TemplateResponse(
        "offre_modifier.html",
        {
            "request": request
        }
    )


@app.delete("/offres/{offre_id}")
async def supprimer_offre(
    offre_id: int
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM offres
        WHERE id = %s
    """, (
        offre_id,
    ))

    if cursor.rowcount == 0:

        cursor.close()
        connection.close()

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "success": True,
        "message": "Offre supprimée avec succès."
    }

@app.get("/offres/{offre_id}/matchings")
async def obtenir_matchings_offre(
    offre_id: int
):

    matchings = lister_matchings_offre(
        offre_id
    )

    return {
        "success": True,
        "offre_id": offre_id,
        "matchings": matchings
    }

@app.get("/offres/{offre_id}/classement")
async def classement_candidats(
    offre_id: int
):

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    matchings = lister_matchings_offre(
        offre_id
    )

    matchings_tries = sorted(
        matchings,
        key=lambda matching: (
            matching.get("score") or 0
        ),
        reverse=True
    )

    return {

        "success": True,

        "offre_id": offre_id,

        "nombre_candidats":
            len(matchings_tries),

        "classement":
            matchings_tries

    }



@app.get("/test-matching")
async def test_matching():

    candidat = {
        "nom": "Jean Dupont",
        "profil": "Développeur logiciel junior",
        "formations": [
            {
                "diplome": "Master Informatique",
                "etablissement": "Université",
                "annee_debut": "2021",
                "annee_fin": "2025"
            }
        ],
        "experiences": [
            {
                "poste": "Développeur Python",
                "entreprise": "Entreprise Test",
                "date_debut": "2024",
                "date_fin": "2025",
                "description": "Développement d'applications web avec Python et FastAPI."
            }
        ],
        "competences": [
            "Python",
            "FastAPI",
            "PostgreSQL",
            "Git"
        ],
        "langues": [
            {
                "langue": "Français",
                "niveau": "Courant"
            },
            {
                "langue": "Anglais",
                "niveau": "Intermédiaire"
            }
        ]
    }

    offre = {
        "titre": "Développeur Python",
        "entreprise": "Entreprise Test",
        "description": "Développement d'applications web.",
        "missions": "Développer et maintenir des applications web.",
        "competences_obligatoires": "Python, FastAPI, PostgreSQL",
        "competences_souhaitees": "Git, Docker",
        "niveau_etude": "Bac+5",
        "experience": "1 an",
        "type_contrat": "CDI",
        "langues": "Français, Anglais"
    }

    resultat = analyser_matching(
        candidat,
        offre
    )

    return {
        "success": True,
        "matching": resultat
    }


@app.get("/test-offre/{offre_id}")
async def test_offre(offre_id: int):

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    return {
        "success": True,
        "offre": offre
    }


@app.get("/test-matching-reel/{candidat_id}/{offre_id}")
async def test_matching_reel(
    candidat_id: int,
    offre_id: int
):

    candidat = recuperer_candidat(
        candidat_id
    )

    if candidat is None:

        return {
            "success": False,
            "message": "Candidat introuvable."
        }

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    resultat = analyser_matching(
        candidat,
        offre
    )

    return {
        "success": True,
        "candidat_id": candidat_id,
        "offre_id": offre_id,
        "matching": resultat
    }

@app.post("/matching")
async def lancer_matching(
    candidat_id: int,
    offre_id: int
):

    candidat = recuperer_candidat(
        candidat_id
    )

    if candidat is None:

        return {
            "success": False,
            "message": "Candidat introuvable."
        }

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    try:

        resultat = analyser_matching(
            candidat,
            offre
        )

        return {

            "success": True,

            "candidat_id":
                candidat_id,

            "offre_id":
                offre_id,

            "matching":
                resultat

        }

    except Exception as erreur:

        return {

            "success": False,

            "message":
                str(erreur)

        }


@app.get("/test-enregistrer-matching/{candidat_id}/{offre_id}")
async def test_enregistrer_matching(
    candidat_id: int,
    offre_id: int
):

    candidat = recuperer_candidat(
        candidat_id
    )

    if candidat is None:

        return {
            "success": False,
            "message": "Candidat introuvable."
        }

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    resultat = analyser_matching(
        candidat,
        offre
    )

    matching = {

        "candidat_id": candidat_id,

        "offre_id": offre_id,

        "score": resultat.get("score"),

        "statut": "analyse_terminee",

        "competences_correspondantes": ", ".join(
            resultat.get(
                "competences_correspondantes",
                []
            )
        ),

        "competences_manquantes": ", ".join(
            resultat.get(
                "competences_manquantes",
                []
            )
        ),

        "analyse_ia": resultat.get(
            "analyse",
            ""
        ),

        "details_matching": resultat.get(
            "details",
            {}
        )

    }

    matching_id = enregistrer_matching(
        matching
    )

    return {

        "success": True,

        "message": "Matching enregistré avec succès.",

        "matching_id": matching_id,

        "matching": matching

    }

@app.get("/test-candidats-complets")
async def test_candidats_complets():

    candidats = lister_candidats_complets()

    return {
        "success": True,
        "nombre_candidats": len(candidats),
        "candidats": candidats
    }




@app.get("/test-matching-tous/{offre_id}")
async def test_matching_tous(
    offre_id: int
):

    offre = recuperer_offre(
        offre_id
    )

    if offre is None:

        return {
            "success": False,
            "message": "Offre introuvable."
        }

    candidats = lister_candidats_complets()

    def analyser_un_candidat(candidat):

        try:

            resultat = analyser_matching(
                candidat,
                offre
            )

            matching = {

                "candidat_id":
                    candidat["id"],

                "offre_id":
                    offre_id,

                "score":
                    resultat.get(
                        "score"
                    ),

                "statut":
                    "analyse_terminee",

                "competences_correspondantes":
                    ", ".join(
                        resultat.get(
                            "competences_correspondantes",
                            []
                        )
                    ),

                "competences_manquantes":
                    ", ".join(
                        resultat.get(
                            "competences_manquantes",
                            []
                        )
                    ),

                "analyse_ia":
                    resultat.get(
                        "analyse",
                        ""
                    ),

                "details_matching":
                    resultat.get(
                        "details",
                        {}
                    )

            }

            matching_id = enregistrer_matching(
                matching
            )

            return {

                "candidat_id":
                    candidat["id"],

                "candidat_nom":
                    candidat["nom"],

                "success":
                    True,

                "matching_id":
                    matching_id,

                "score":
                    resultat.get(
                        "score"
                    ),

                "competences_correspondantes":
                    resultat.get(
                        "competences_correspondantes",
                        []
                    ),

                "competences_manquantes":
                    resultat.get(
                        "competences_manquantes",
                        []
                    ),

                "analyse":
                    resultat.get(
                        "analyse",
                        ""
                    ),

                "details":
                    resultat.get(
                        "details",
                        {}
                    )

            }

        except Exception as erreur:

            return {

                "candidat_id":
                    candidat["id"],

                "candidat_nom":
                    candidat["nom"],

                "success":
                    False,

                "erreur":
                    str(erreur)

            }

    with ThreadPoolExecutor(
        max_workers=6
    ) as executor:

        resultats = list(
            executor.map(
                analyser_un_candidat,
                candidats
            )
        )

    return {

        "success":
            True,

        "offre_id":
            offre_id,

        "nombre_candidats":
            len(candidats),

        "resultats":
            resultats

    }
