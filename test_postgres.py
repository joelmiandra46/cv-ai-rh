import psycopg

try:
    connection = psycopg.connect(
        host="localhost",
        port=5432,
        dbname="cv_ai",
        user="postgres"
    )

    print("Connexion PostgreSQL réussie !")

    connection.close()

except Exception as e:
    print("Erreur de connexion :")
    print(e)