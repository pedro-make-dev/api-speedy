"""Configuração via variáveis de ambiente (é assim que o Render injeta segredo)."""

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

ENDERECO_ORIGEM_PADRAO = (
    "R. José Barros Magaldi, 1247 - Jardim São João, São Paulo - SP, 05815-010"
)
CACHE_TTL_PADRAO_SEGUNDOS = 86400  # 24h


@dataclass(frozen=True)
class Config:
    google_api_key: str
    endereco_origem: str
    api_key: str
    cache_ttl_segundos: int


def carregar_config() -> Config:
    # Conveniência de desenvolvimento: no Render não existe .env e as variáveis
    # do painel já estão no ambiente. override=False garante que o painel vence.
    load_dotenv(find_dotenv(usecwd=True), override=False)

    google_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not google_api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY não configurada. "
            "Defina a variável de ambiente antes de subir a API."
        )

    return Config(
        google_api_key=google_api_key,
        endereco_origem=os.getenv("ENDERECO_ORIGEM", "").strip() or ENDERECO_ORIGEM_PADRAO,
        # API_KEY vazia = endpoint aberto. Preencher no painel do Render liga a proteção.
        api_key=os.getenv("API_KEY", "").strip(),
        cache_ttl_segundos=int(
            os.getenv("CACHE_TTL_SEGUNDOS", CACHE_TTL_PADRAO_SEGUNDOS)
        ),
    )
