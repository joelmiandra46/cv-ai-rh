import os
import requests
import json
import time


# ============================================================
# CONFIGURATION
# ============================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ============================================================
# MODÈLES OPENROUTER GRATUITS
# ============================================================
#
# Le programme essaiera les modèles dans cet ordre.
#
# Si un modèle retourne 429 :
#     1. quelques secondes d'attente
#     2. nouvelle tentative
#     3. changement de modèle
#
# IMPORTANT :
# Les modèles gratuits peuvent être temporairement
# indisponibles selon les limites des fournisseurs.
# ============================================================

OPENROUTER_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super:free",
    "openrouter/free"
]


# Nombre de tentatives pour chaque modèle
MAX_RETRIES_PER_MODEL = 2


# Temps d'attente entre deux tentatives
RETRY_DELAY_SECONDS = 5


# Nombre maximum de caractères du CV envoyé à l'IA
MAX_CV_CHARACTERS = 30000


# ============================================================
# NETTOYAGE ET PARSING JSON
# ============================================================

def nettoyer_json(contenu):
    """
    Nettoie et transforme une réponse de l'IA
    en dictionnaire Python.

    Gère notamment :
    - ```json ... ```
    - ``` ... ```
    - texte avant le JSON
    - texte après le JSON
    """

    if not contenu:
        raise Exception(
            "La réponse de l'IA est vide."
        )

    contenu = str(contenu).strip()

    # --------------------------------------------------------
    # Suppression des balises Markdown
    # --------------------------------------------------------

    contenu = contenu.replace("```json", "")
    contenu = contenu.replace("```JSON", "")
    contenu = contenu.replace("```", "")

    contenu = contenu.strip()

    # --------------------------------------------------------
    # Recherche du début du JSON
    # --------------------------------------------------------

    debut = contenu.find("{")

    if debut == -1:
        raise Exception(
            "La réponse de l'IA ne contient aucun objet JSON."
        )

    contenu = contenu[debut:]

    # --------------------------------------------------------
    # Extraction robuste du JSON
    # --------------------------------------------------------

    niveau = 0
    dans_string = False
    echappement = False
    fin = -1

    for i, caractere in enumerate(contenu):

        if echappement:
            echappement = False
            continue

        if caractere == "\\":
            echappement = True
            continue

        if caractere == '"':
            dans_string = not dans_string
            continue

        if not dans_string:

            if caractere == "{":
                niveau += 1

            elif caractere == "}":
                niveau -= 1

                if niveau == 0:
                    fin = i
                    break

    if fin == -1:
        raise Exception(
            "La réponse de l'IA semble être un JSON "
            "incomplet ou tronqué."
        )

    contenu_json = contenu[:fin + 1].strip()

    # --------------------------------------------------------
    # Conversion JSON -> dictionnaire Python
    # --------------------------------------------------------

    try:

        resultat = json.loads(contenu_json)

    except json.JSONDecodeError as erreur:

        print("\n========== JSON INVALIDE ==========")
        print(contenu_json)
        print("===================================")

        raise Exception(
            f"JSON retourné par l'IA invalide : {erreur}"
        )

    if not isinstance(resultat, dict):

        raise Exception(
            "Le JSON retourné par l'IA n'est pas un objet."
        )

    return resultat


# ============================================================
# VALIDATION DE LA STRUCTURE DU CV
# ============================================================

def valider_structure_cv(resultat):
    """
    Vérifie que l'IA a bien retourné
    la structure attendue.
    """

    if not isinstance(resultat, dict):

        raise Exception(
            "Le résultat de l'analyse CV "
            "n'est pas un objet JSON."
        )

    # --------------------------------------------------------
    # candidat
    # --------------------------------------------------------

    if "candidat" not in resultat:
        resultat["candidat"] = {}

    if not isinstance(resultat["candidat"], dict):
        resultat["candidat"] = {}

    champs_candidat = [
        "nom",
        "email",
        "telephone",
        "adresse"
    ]

    for champ in champs_candidat:

        if champ not in resultat["candidat"]:
            resultat["candidat"][champ] = ""

    # --------------------------------------------------------
    # profil
    # --------------------------------------------------------

    if "profil" not in resultat:
        resultat["profil"] = ""

    if not isinstance(resultat["profil"], str):

        resultat["profil"] = str(
            resultat["profil"]
        )

    # --------------------------------------------------------
    # formations
    # --------------------------------------------------------

    if "formations" not in resultat:
        resultat["formations"] = []

    if not isinstance(resultat["formations"], list):
        resultat["formations"] = []

    # --------------------------------------------------------
    # expériences
    # --------------------------------------------------------

    if "experiences" not in resultat:
        resultat["experiences"] = []

    if not isinstance(resultat["experiences"], list):
        resultat["experiences"] = []

    # --------------------------------------------------------
    # compétences
    # --------------------------------------------------------

    if "competences" not in resultat:
        resultat["competences"] = []

    if not isinstance(resultat["competences"], list):
        resultat["competences"] = []

    # --------------------------------------------------------
    # langues
    # --------------------------------------------------------

    if "langues" not in resultat:
        resultat["langues"] = []

    if not isinstance(resultat["langues"], list):
        resultat["langues"] = []

    return resultat


# ============================================================
# ANALYSE DU CV AVEC OPENROUTER
# ============================================================

def analyser_cv(texte_cv):
    """
    Analyse un CV avec OpenRouter.

    Fonctionnement :

    Modèle 1
        ↓
    429 ?
        ↓
    Retry
        ↓
    429 ?
        ↓
    Modèle 2
        ↓
    429 ?
        ↓
    Retry
        ↓
    Modèle 3
        ↓
    JSON final
    """

    api_key = os.getenv(
        "OPENROUTER_API_KEY"
    )

    if not api_key:

        raise Exception(
            "OPENROUTER_API_KEY est absente."
        )

    if not texte_cv or not texte_cv.strip():

        raise Exception(
            "Le CV ne contient aucun texte exploitable."
        )

    # --------------------------------------------------------
    # Nettoyage du texte
    # --------------------------------------------------------

    texte_cv = texte_cv.strip()

    # --------------------------------------------------------
    # Protection contre les CV extrêmement longs
    # --------------------------------------------------------

    if len(texte_cv) > MAX_CV_CHARACTERS:

        print(
            f"\nCV trop long : "
            f"{len(texte_cv)} caractères."
        )

        print(
            f"Limitation à "
            f"{MAX_CV_CHARACTERS} caractères."
        )

        texte_cv = texte_cv[:MAX_CV_CHARACTERS]

    # --------------------------------------------------------
    # PROMPT
    # --------------------------------------------------------

    prompt = f"""
Tu es un système professionnel d'extraction
de données de CV pour une application de recrutement RH.

Ta tâche est UNIQUEMENT d'extraire les informations
présentes dans le CV.

IMPORTANT :
- N'invente aucune information.
- Ne déduis aucune information absente.
- Ne fais aucune analyse.
- Ne donne aucune explication.
- Ne montre aucun raisonnement.
- Retourne uniquement le JSON demandé.

CV À ANALYSER
============================================================

{texte_cv}

============================================================

RÈGLES
============================================================

1. Retourne UNIQUEMENT un objet JSON valide.

2. Ne retourne aucune explication.

3. Ne retourne aucun raisonnement.

4. Ne retourne aucun texte avant le JSON.

5. Ne retourne aucun texte après le JSON.

6. Ne mets pas de balises Markdown.

7. Commence directement par l'objet JSON.

8. Termine directement par l'objet JSON.

9. N'invente aucune information.

10. Si une information est absente :
    - "" pour une valeur texte
    - [] pour une liste

11. Conserve les informations réellement présentes
    dans le CV.

12. Pour les dates, ne déduis aucune date.

13. Pour les formations, conserve les diplômes,
    établissements et années réellement mentionnés.

14. Pour les expériences, conserve les postes,
    entreprises, dates et descriptions réellement
    mentionnés.

15. Les compétences doivent provenir du CV.

16. Les langues doivent provenir du CV.

17. Si plusieurs compétences sont présentes,
    conserve-les séparément dans la liste.

18. Si plusieurs langues sont présentes,
    conserve-les séparément.

STRUCTURE JSON OBLIGATOIRE
============================================================

{{
    "candidat": {{
        "nom": "",
        "email": "",
        "telephone": "",
        "adresse": ""
    }},

    "profil": "",

    "formations": [
        {{
            "diplome": "",
            "etablissement": "",
            "annee_debut": "",
            "annee_fin": ""
        }}
    ],

    "experiences": [
        {{
            "poste": "",
            "entreprise": "",
            "date_debut": "",
            "date_fin": "",
            "description": ""
        }}
    ],

    "competences": [],

    "langues": [
        {{
            "langue": "",
            "niveau": ""
        }}
    ]
}}

IMPORTANT :
Réponds uniquement avec le JSON.
"""

    # ========================================================
    # HEADERS
    # ========================================================

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "CV AI"
    }

    # ========================================================
    # INFORMATIONS GÉNÉRALES
    # ========================================================

    print(
        "\n=================================================="
    )

    print(
        "ANALYSE DU CV AVEC OPENROUTER"
    )

    print(
        f"Longueur du CV : "
        f"{len(texte_cv)} caractères"
    )

    print(
        f"Nombre de modèles disponibles : "
        f"{len(OPENROUTER_MODELS)}"
    )

    print(
        "=================================================="
    )

    # ========================================================
    # VARIABLES POUR LES ERREURS
    # ========================================================

    dernier_message_erreur = None

    # ========================================================
    # ESSAI DES MODÈLES
    # ========================================================

    for index_modele, modele in enumerate(
        OPENROUTER_MODELS
    ):

        print(
            "\n--------------------------------------------------"
        )

        print(
            f"MODÈLE {index_modele + 1}/"
            f"{len(OPENROUTER_MODELS)}"
        )

        print(
            f"Modèle : {modele}"
        )

        print(
            "--------------------------------------------------"
        )

        # ----------------------------------------------------
        # RETRIES DU MODÈLE ACTUEL
        # ----------------------------------------------------

        for tentative in range(
            1,
            MAX_RETRIES_PER_MODEL + 1
        ):

            print(
                f"\nTentative "
                f"{tentative}/"
                f"{MAX_RETRIES_PER_MODEL}"
            )

            # ------------------------------------------------
            # DATA
            # ------------------------------------------------

            data = {
                "model": modele,

                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Tu es un extracteur professionnel "
                            "de données de CV. "
                            "Retourne uniquement le JSON demandé. "
                            "Ne montre aucun raisonnement."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],

                "temperature": 0,

                "max_tokens": 8000,

                "response_format": {
                    "type": "json_object"
                }
            }

            try:

                # ============================================
                # REQUÊTE OPENROUTER
                # ============================================

                response = requests.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=data,
                    timeout=120
                )

                # ============================================
                # ERREUR 429
                # ============================================

                if response.status_code == 429:

                    try:
                        erreur = response.json()

                    except Exception:
                        erreur = response.text

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        f"HTTP 429 - {erreur}"
                    )

                    print(
                        "\n⚠️ 429 : modèle temporairement "
                        "limité."
                    )

                    # ----------------------------------------
                    # Si ce n'est pas la dernière tentative
                    # ----------------------------------------

                    if tentative < MAX_RETRIES_PER_MODEL:

                        print(
                            f"Nouvelle tentative dans "
                            f"{RETRY_DELAY_SECONDS} secondes..."
                        )

                        time.sleep(
                            RETRY_DELAY_SECONDS
                        )

                        continue

                    # ----------------------------------------
                    # Dernière tentative :
                    # passer au modèle suivant
                    # ----------------------------------------

                    print(
                        "\n⚠️ Modèle épuisé."
                    )

                    print(
                        "Passage au modèle suivant..."
                    )

                    break


                # ============================================
                # AUTRES ERREURS HTTP
                # ============================================

                if response.status_code != 200:

                    try:
                        erreur = response.json()

                    except Exception:
                        erreur = response.text

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        f"HTTP {response.status_code} - "
                        f"{erreur}"
                    )

                    print(
                        "\n⚠️ Erreur HTTP : "
                        f"{response.status_code}"
                    )

                    print(
                        erreur
                    )

                    # ----------------------------------------
                    # Pour une erreur HTTP autre que 429,
                    # on passe directement au modèle suivant.
                    # ----------------------------------------

                    print(
                        "Passage au modèle suivant..."
                    )

                    break


                # ============================================
                # LECTURE DE LA RÉPONSE
                # ============================================

                try:

                    resultat = response.json()

                except json.JSONDecodeError:

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        "réponse HTTP non JSON."
                    )

                    print(
                        "\n⚠️ Réponse OpenRouter "
                        "non JSON."
                    )

                    break


                # ============================================
                # DEBUG COMPLET
                # ============================================

                print(
                    "\n========== RÉPONSE OPENROUTER =========="
                )

                print(
                    json.dumps(
                        resultat,
                        ensure_ascii=False,
                        indent=4
                    )
                )

                print(
                    "========================================="
                )


                # ============================================
                # VÉRIFICATION CHOICES
                # ============================================

                if "choices" not in resultat:

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        "champ choices absent."
                    )

                    print(
                        "\n⚠️ Réponse OpenRouter "
                        "invalide : choices absent."
                    )

                    break


                if not resultat["choices"]:

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        "aucun résultat."
                    )

                    print(
                        "\n⚠️ Aucun résultat retourné."
                    )

                    break


                # ============================================
                # PREMIER CHOIX
                # ============================================

                choix = resultat["choices"][0]

                message = choix.get(
                    "message",
                    {}
                )


                # ============================================
                # FINISH REASON
                # ============================================

                finish_reason = choix.get(
                    "finish_reason"
                )

                native_finish_reason = choix.get(
                    "native_finish_reason"
                )

                print(
                    "\n========== INFORMATIONS =========="
                )

                print(
                    f"Modèle utilisé : {modele}"
                )

                print(
                    f"finish_reason : "
                    f"{finish_reason}"
                )

                print(
                    f"native_finish_reason : "
                    f"{native_finish_reason}"
                )

                print(
                    "=================================="
                )


                # ============================================
                # RÉCUPÉRATION CONTENT
                # ============================================

                contenu = message.get(
                    "content"
                )


                # IMPORTANT :
                #
                # NE JAMAIS utiliser :
                #
                # message["reasoning"]
                #
                # comme JSON.
                #
                # Le reasoning n'est pas la réponse finale.
                # ============================================

                if (
                    contenu is None
                    or not str(contenu).strip()
                ):

                    # ----------------------------------------
                    # CAS MAX TOKENS
                    # ----------------------------------------

                    if (
                        finish_reason == "length"
                        or native_finish_reason
                        == "max_tokens"
                    ):

                        dernier_message_erreur = (
                            f"Modèle {modele} : "
                            "réponse coupée par max_tokens."
                        )

                        print(
                            "\n⚠️ Réponse coupée "
                            "par max_tokens."
                        )

                        # ------------------------------------
                        # On essaie à nouveau le même modèle
                        # ------------------------------------

                        if tentative < MAX_RETRIES_PER_MODEL:

                            print(
                                "Nouvelle tentative "
                                "avec le même modèle..."
                            )

                            time.sleep(
                                RETRY_DELAY_SECONDS
                            )

                            continue

                        print(
                            "Passage au modèle suivant..."
                        )

                        break


                    # ----------------------------------------
                    # AUTRE RÉPONSE VIDE
                    # ----------------------------------------

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        "content vide."
                    )

                    print(
                        "\n⚠️ Content vide."
                    )

                    break


                contenu = str(
                    contenu
                ).strip()


                # ============================================
                # DEBUG RÉPONSE BRUTE
                # ============================================

                print(
                    "\n========== RÉPONSE BRUTE =========="
                )

                print(
                    repr(contenu)
                )

                print(
                    "===================================="
                )


                # ============================================
                # PARSING JSON
                # ============================================

                try:

                    resultat_cv = nettoyer_json(
                        contenu
                    )

                except Exception as erreur_json:

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        f"JSON invalide - "
                        f"{erreur_json}"
                    )

                    print(
                        "\n⚠️ JSON invalide."
                    )

                    print(
                        erreur_json
                    )

                    # ----------------------------------------
                    # Si JSON invalide, essayer à nouveau
                    # ----------------------------------------

                    if tentative < MAX_RETRIES_PER_MODEL:

                        print(
                            f"Nouvelle tentative dans "
                            f"{RETRY_DELAY_SECONDS} secondes..."
                        )

                        time.sleep(
                            RETRY_DELAY_SECONDS
                        )

                        continue

                    print(
                        "Passage au modèle suivant..."
                    )

                    break


                # ============================================
                # VALIDATION STRUCTURE
                # ============================================

                try:

                    resultat_cv = (
                        valider_structure_cv(
                            resultat_cv
                        )
                    )

                except Exception as erreur_validation:

                    dernier_message_erreur = (
                        f"Modèle {modele} : "
                        f"structure invalide - "
                        f"{erreur_validation}"
                    )

                    print(
                        "\n⚠️ Structure JSON invalide."
                    )

                    print(
                        erreur_validation
                    )

                    break


                # ============================================
                # SUCCÈS
                # ============================================

                print(
                    "\n=================================================="
                )

                print(
                    "✅ EXTRACTION CV RÉUSSIE"
                )

                print(
                    f"Modèle utilisé : {modele}"
                )

                print(
                    "=================================================="
                )


                print(
                    "\n========== JSON CV EXTRAIT =========="
                )

                print(
                    json.dumps(
                        resultat_cv,
                        ensure_ascii=False,
                        indent=4
                    )
                )

                print(
                    "====================================="
                )


                # ============================================
                # RETOUR DU RÉSULTAT
                # ============================================

                return resultat_cv


            # =================================================
            # TIMEOUT
            # =================================================

            except requests.Timeout:

                dernier_message_erreur = (
                    f"Modèle {modele} : "
                    "timeout après 120 secondes."
                )

                print(
                    "\n⚠️ Timeout avec ce modèle."
                )

                if tentative < MAX_RETRIES_PER_MODEL:

                    print(
                        f"Nouvelle tentative dans "
                        f"{RETRY_DELAY_SECONDS} secondes..."
                    )

                    time.sleep(
                        RETRY_DELAY_SECONDS
                    )

                    continue

                print(
                    "Passage au modèle suivant..."
                )

                break


            # =================================================
            # ERREUR RÉSEAU
            # =================================================

            except requests.RequestException as erreur:

                dernier_message_erreur = (
                    f"Modèle {modele} : "
                    f"erreur réseau - {erreur}"
                )

                print(
                    "\n⚠️ Erreur réseau :"
                )

                print(
                    erreur
                )

                if tentative < MAX_RETRIES_PER_MODEL:

                    print(
                        f"Nouvelle tentative dans "
                        f"{RETRY_DELAY_SECONDS} secondes..."
                    )

                    time.sleep(
                        RETRY_DELAY_SECONDS
                    )

                    continue

                print(
                    "Passage au modèle suivant..."
                )

                break


            except Exception as erreur:

                dernier_message_erreur = (
                    f"Modèle {modele} : "
                    f"{erreur}"
                )

                print(
                    "\n⚠️ Erreur :"
                )

                print(
                    erreur
                )

                break


    # ========================================================
    # AUCUN MODÈLE N'A FONCTIONNÉ
    # ========================================================

    raise Exception(
        "Impossible d'analyser le CV avec "
        "les modèles OpenRouter disponibles.\n\n"
        f"Dernière erreur : "
        f"{dernier_message_erreur}"
    )


# ============================================================
# ANALYSE MATCHING AVEC GROQ
# ============================================================

def analyser_matching(candidat, offre):
    """
    Analyse la compatibilité entre un candidat
    et une offre avec Groq.
    """

    api_key = os.getenv(
        "GROQ_API_KEY"
    )

    if not api_key:

        raise Exception(
            "GROQ_API_KEY non configurée."
        )


    # ========================================================
    # HEADERS
    # ========================================================

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


    # ========================================================
    # CONVERSION DES DONNÉES EN JSON
    # ========================================================

    candidat_json = json.dumps(
        candidat,
        ensure_ascii=False,
        indent=2,
        default=str
    )

    offre_json = json.dumps(
        offre,
        ensure_ascii=False,
        indent=2,
        default=str
    )


    # ========================================================
    # PROMPT MATCHING
    # ========================================================

    prompt = f"""
Tu es un système expert de recrutement.

Analyse la compatibilité entre le candidat
et l'offre d'emploi.

============================================================
CANDIDAT
============================================================

{candidat_json}

============================================================
OFFRE
============================================================

{offre_json}

============================================================
RÉSULTAT ATTENDU
============================================================

Retourne uniquement un objet JSON valide.

Format obligatoire :

{{
    "score": 0,
    "competences_correspondantes": [],
    "competences_manquantes": [],
    "analyse": "",
    "details": {{
        "competences": 0,
        "experience": 0,
        "formation": 0,
        "langues": 0
    }}
}}

============================================================
RÈGLES
============================================================

- score entre 0 et 100.

- competences_correspondantes est une liste.

- competences_manquantes est une liste.

- analyse est une courte analyse en français.

- details contient les scores :
  compétences,
  expérience,
  formation,
  langues.

- Chaque score de details est compris entre 0 et 100.

- Ne jamais inventer une compétence du candidat.

- Ne jamais inventer une expérience du candidat.

- Utilise uniquement les informations présentes
  dans les données du candidat.

- Retourne uniquement le JSON.
"""


    # ========================================================
    # REQUÊTE GROQ
    # ========================================================

    data = {
        "model": "openai/gpt-oss-20b",

        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],

        "temperature": 0,

        "response_format": {
            "type": "json_object"
        }
    }


    # ========================================================
    # ENVOI
    # ========================================================

    try:

        response = requests.post(
            GROQ_URL,
            headers=headers,
            json=data,
            timeout=30
        )


        # ====================================================
        # ERREUR 429
        # ====================================================

        if response.status_code == 429:

            raise Exception(
                "Limite Groq atteinte (429). "
                "Veuillez patienter avant de relancer "
                "l'analyse."
            )


        # ====================================================
        # AUTRES ERREURS HTTP
        # ====================================================

        if response.status_code != 200:

            raise Exception(
                f"Erreur Groq : "
                f"{response.status_code} - "
                f"{response.text}"
            )


        # ====================================================
        # LECTURE JSON
        # ====================================================

        try:

            resultat = response.json()

        except json.JSONDecodeError:

            raise Exception(
                "Groq a retourné une réponse "
                "qui n'est pas un JSON valide."
            )


        if "choices" not in resultat:

            raise Exception(
                f"Réponse Groq invalide : {resultat}"
            )

        if not resultat["choices"]:

            raise Exception(
                "Groq n'a retourné aucun résultat."
            )


        # ====================================================
        # RÉCUPÉRATION CONTENU
        # ====================================================

        message = resultat["choices"][0].get(
            "message",
            {}
        )

        contenu = message.get(
            "content",
            ""
        )


        if not contenu or not str(contenu).strip():

            raise Exception(
                "Réponse Groq vide."
            )


        contenu = str(
            contenu
        ).strip()


        # ====================================================
        # DEBUG MATCHING
        # ====================================================

        print(
            "\n========== RÉPONSE BRUTE GROQ =========="
        )

        print(
            repr(contenu)
        )

        print(
            "========================================="
        )


        # ====================================================
        # PARSING JSON
        # ====================================================

        resultat_matching = nettoyer_json(
            contenu
        )


        return resultat_matching


    # ========================================================
    # TIMEOUT
    # ========================================================

    except requests.Timeout:

        raise Exception(
            "L'analyse Groq a dépassé "
            "le délai de 30 secondes."
        )


    # ========================================================
    # ERREUR RÉSEAU
    # ========================================================

    except requests.RequestException as erreur:

        raise Exception(
            f"Erreur réseau Groq : {erreur}"
        )


    except Exception:

        raise