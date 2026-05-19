from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def calcular_similitud_coseno(texto_inicial: str, texto_final: str) -> dict:
    if not texto_inicial.strip() or not texto_final.strip():
        return {"similitud_coseno": 0.0, "interpretacion": "texto vacío"}
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([texto_inicial, texto_final])
    similitud = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
    return {
        "similitud_coseno": round(float(similitud), 4),
        "interpretacion": (
            "alta coherencia temática" if similitud > 0.7
            else "coherencia media" if similitud > 0.4
            else "posible desviación temática"
        ),
    }
