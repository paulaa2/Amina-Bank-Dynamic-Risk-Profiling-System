import feedparser
import urllib.parse

def buscar_noticias_empresa(nombre_empresa):
    # 1. Codificar el nombre de la empresa para que sea seguro en una URL
    # (Por si el nombre tiene espacios, acentos o caracteres especiales)
    query = urllib.parse.quote(nombre_empresa)
    
    # 2. Construir la URL (En este caso, buscando noticias en inglés a nivel global)
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    
    # 3. Parsear el feed RSS
    feed = feedparser.parse(url)
    
    # 4. Extraer la información relevante
    noticias = []
    for entry in feed.entries[:10]: # Limitamos a las 10 últimas noticias para la prueba
        noticia = {
            "titulo": entry.title,
            "enlace": entry.link,
            "fecha_publicacion": entry.published
        }
        noticias.append(noticia)
        
    return noticias

# --- PRUEBA DE FUNCIONAMIENTO ---
if __name__ == "__main__":
    empresa_test = "Amina Bank" # Podéis cambiarlo por la empresa que queráis probar
    resultados = buscar_noticias_empresa(empresa_test)
    
    print(f"--- Últimas noticias encontradas para: {empresa_test} ---")
    for idx, n in enumerate(resultados, 1):
        print(f"\n[{idx}] {n['titulo']}")
        print(f"    Fecha: {n['fecha_publicacion']}")
        print(f"    Link: {n['enlace']}")