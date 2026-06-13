import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse, unquote

# ==============================================================================
# MICROSSERVIÇO DE BUSCA E CATALOGAÇÃO AUTOMÁTICA DE MÍDIA - ESTILO HBO MAX (API FASTAPI)
# ==============================================================================
# Este é o arquivo principal 'main.py' configurado para rodar no Render.com.
# Ele expõe uma API REST rápida que recebe links da nuvem e retorna metadados do TMDB.
# ==============================================================================

app = FastAPI(
    title="UniCine Play TMDB Cataloging Microservice",
    description="API de Produção para mapeamento automático de links de mídia com o TMDB.",
    version="1.0.0"
)

# 1. Configurações Globais e Autenticação via Bearer Token
TMDB_BASE_URL = "https://api.themoviedb.org/3"
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI3OWVmMWZhMTY4OWU4N2Q3NDRmMDcxMzZjMjdkMDFkMSIsIm5iZiI6MTc4MDE4NTc1OS4zNjQsInN1YiI6IjZhMWI3YTlmNmEzNmQ4ODRhMTRiOGU1YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.c0tlX5PNHXd0j1c4Xg7rEuUjWzHnYk1Mhisa40Y8mhQ"

HEADERS = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "accept": "application/json"
}

class StreamRequest(BaseModel):
    stream_url: str

def extract_filename_from_url_or_path(input_source: str) -> str:
    try:
        parsed_url = urlparse(input_source)
        path = unquote(parsed_url.path)
        
        # Busca por parâmetros populares em links de nuvem
        query_params = re.findall(r"(?:name|file|filename|title)=([^&]+)", parsed_url.query, re.IGNORECASE)
        if query_params:
            return unquote(query_params[0])
            
        filename = path.split("/")[-1]
        if not filename:
            filename = input_source.split("/")[-1]
            
        return filename
    except Exception:
        return input_source.split("/")[-1] if "/" in input_source else input_source

def parse_filename(filename: str) -> dict:
    name_without_ext = re.sub(r"\.(mp4|mkv|avi|webm|ts|m3u8)$", "", filename, flags=re.IGNORECASE)
    
    # Regex padrões
    pattern_s_e = re.compile(r"^(.*?)(?:[\s._-]+)?[sS](\d+)[eE](\d+)", re.IGNORECASE)
    pattern_s_dot_e = re.compile(r"^(.*?)(?:[\s._-]+)?[sS](\d+)(?:[\s._-]+)?[eE](\d+)", re.IGNORECASE)
    pattern_x = re.compile(r"^(.*?)(?:[\s._-]+)?(\d+)[xX](\d+)", re.IGNORECASE)

    raw_title = name_without_ext
    season = None
    episode = None
    is_series = False

    match = pattern_s_e.search(name_without_ext)
    if match:
        raw_title, season, episode = match.group(1), int(match.group(2)), int(match.group(3))
        is_series = True
    else:
        match = pattern_s_dot_e.search(name_without_ext)
        if match:
            raw_title, season, episode = match.group(1), int(match.group(2)), int(match.group(3))
            is_series = True
        else:
            match = pattern_x.search(name_without_ext)
            if match:
                raw_title, season, episode = match.group(1), int(match.group(2)), int(match.group(3))
                is_series = True

    cleaned_title = re.sub(r"[\._-]", " ", raw_title)
    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()
    
    return {
        "title": cleaned_title,
        "season": season,
        "episode": episode,
        "is_series": is_series
    }

def fetch_media_from_tmdb(parsed_data: dict, original_input_source: str) -> dict:
    query = parsed_data["title"]
    is_series = parsed_data["is_series"]
    
    endpoint_type = "tv" if is_series else "movie"
    url = f"{TMDB_BASE_URL}/search/{endpoint_type}"
    
    params = {
        "query": query,
        "language": "pt-BR",
        "page": 1
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        
        if response.status_code == 401:
            return {
                "success": False,
                "error": "Autenticação Recusada (401). Verifique o Bearer Token do TMDB."
            }
        elif response.status_code == 404:
            return {
                "success": False,
                "error": "Endpoint Inexistente."
            }
            
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            return {
                "success": False,
                "error": f"Nenhuma correspondência no TMDB para: '{query}'"
            }
            
        best_match = results[0]
        id_oficial_tmdb = best_match.get("id")
        nome_oficial = best_match.get("name") if is_series else best_match.get("title")
        sinopse = best_match.get("overview", "Sem sinopse instalada no momento.")
        poster_path = best_match.get("poster_path")
        url_do_poster = f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else None
        
        response_data = {
            "success": True,
            "id_oficial_tmdb": id_oficial_tmdb,
            "nome_da_media": nome_oficial,
            "sinopse": sinopse,
            "url_do_poster_alta_definicao": url_do_poster,
            "tipo": "Série" if is_series else "Filme",
            "url_do_streaming_original": original_input_source
        }
        
        if is_series:
            response_data["temporada_detectada"] = parsed_data["season"]
            response_data["episodio_detectado"] = parsed_data["episode"]
            
        return response_data
        
    except requests.exceptions.Timeout:
        return {"success": False, "error": "A API do TMDB excedeu tempo limite de resposta."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Falha de conexão com o TMDB."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/")
def read_root():
    """Rota de verificação para saber se o servidor está ativo no Render."""
    return {
        "status": "online",
        "service": "UniCine Play Backend Cataloger",
        "docs_url": "/docs"
    }


@app.post("/api/v1/catalog")
def catalog_media(request: StreamRequest):
    """
    Rota principal POST. Recebe JSON com a chave 'stream_url'
    e retorna os dados estruturados do TMDB.
    """
    stream_url = request.stream_url
    if not stream_url:
        raise HTTPException(status_code=400, detail="O link 'stream_url' está vazio.")
        
    extracted_filename = extract_filename_from_url_or_path(stream_url)
    parsed_metadata = parse_filename(extracted_filename)
    result = fetch_media_from_tmdb(parsed_metadata, stream_url)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
        
    return result
