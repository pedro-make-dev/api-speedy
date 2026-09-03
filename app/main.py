"""API de cálculo de taxa de entrega.

Recebe um endereço ou um CEP, mede a distância real de rota (driving) a partir
da loja e devolve a faixa de taxa. Quem decide o valor é esta API — nunca a LLM.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.cache import CacheTTL
from app.config import carregar_config
from app.enderecos import CepInvalido, EnderecoVazio, resolver_destino
from app.rotas import (
    EnderecoNaoEncontrado,
    ErroRoteamento,
    Local,
    distancia_rota_km,
    geocodificar,
)
from app.tarifa import calcular_taxa

MOEDA = "BRL"


class PedidoEntrega(BaseModel):
    destino: str = Field(default="", description="Endereço completo ou CEP do cliente")
    origem: str | None = Field(
        default=None, description="Sobrescreve o endereço da loja (opcional)"
    )


class ErroApi(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str):
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


def _erro(status: int, codigo: str, mensagem: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": codigo, "message": mensagem},
    )


async def exigir_api_key(request: Request) -> None:
    """Só protege se API_KEY estiver preenchida; vazia = endpoint aberto."""
    esperada = request.app.state.config.api_key
    if esperada and request.headers.get("X-API-Key") != esperada:
        raise ErroApi(401, "nao_autorizado", "Chave de API ausente ou inválida.")


async def _local_da_origem(app: FastAPI, endereco: str) -> Local:
    """A loja não muda de lugar: geocodifica uma vez e guarda pelo tempo de vida do processo."""
    if app.state.origem is None or app.state.origem[0] != endereco:
        local = await geocodificar(
            endereco, app.state.client, app.state.config.google_api_key
        )
        app.state.origem = (endereco, local)
    return app.state.origem[1]


def criar_app() -> FastAPI:
    config = carregar_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.client.aclose()

    app = FastAPI(
        title="API de Taxa de Entrega",
        version="1.0.0",
        description="Calcula a taxa de entrega pela distância real de rota a partir da loja.",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.client = httpx.AsyncClient()
    app.state.cache = CacheTTL(ttl_segundos=config.cache_ttl_segundos)
    app.state.origem = None

    @app.exception_handler(ErroApi)
    async def _trata_erro_api(request: Request, exc: ErroApi):
        return _erro(exc.status, exc.codigo, exc.mensagem)

    @app.exception_handler(EnderecoVazio)
    async def _trata_endereco_vazio(request: Request, exc: EnderecoVazio):
        return _erro(400, "endereco_obrigatorio", "Informe o endereço do cliente.")

    @app.exception_handler(CepInvalido)
    async def _trata_cep_invalido(request: Request, exc: CepInvalido):
        return _erro(422, "cep_invalido", str(exc))

    @app.exception_handler(EnderecoNaoEncontrado)
    async def _trata_endereco_nao_encontrado(request: Request, exc: EnderecoNaoEncontrado):
        return _erro(
            422,
            "endereco_nao_encontrado",
            "Não foi possível localizar esse endereço. Confirme rua, número e bairro.",
        )

    @app.exception_handler(ErroRoteamento)
    async def _trata_erro_roteamento(request: Request, exc: ErroRoteamento):
        return _erro(
            502,
            "erro_roteamento",
            "Serviço de rotas indisponível no momento. Tente novamente em instantes.",
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/calcular-entrega", dependencies=[Depends(exigir_api_key)])
    async def calcular_entrega(pedido: PedidoEntrega, request: Request):
        cfg = request.app.state.config
        client = request.app.state.client
        cache = request.app.state.cache

        destino_texto = (pedido.destino or "").strip()
        if not destino_texto:
            raise ErroApi(400, "endereco_obrigatorio", "Informe o endereço do cliente.")

        origem_texto = (pedido.origem or cfg.endereco_origem).strip()

        chave = f"{origem_texto.casefold()}|{destino_texto.casefold()}"
        guardado = cache.get(chave)
        if guardado is not None:
            return JSONResponse(guardado)

        # Antes de gastar cota do Google: resolve CEP e recusa entrada inválida.
        destino = await resolver_destino(destino_texto, client)
        origem_local = await _local_da_origem(request.app, origem_texto)
        destino_local = await geocodificar(destino.consulta, client, cfg.google_api_key)
        km = await distancia_rota_km(
            origem_local, destino_local, client, cfg.google_api_key
        )

        tarifa = calcular_taxa(km)
        corpo = {
            "success": True,
            "atendido": tarifa.atendido,
            "distancia_km": km,
            "raio": tarifa.raio,
            "taxa_entrega": tarifa.taxa,
            "moeda": MOEDA,
            # CEP sem número cai no centroide: a LLM pode pedir o número se
            # a distância estiver colada no limite da faixa.
            "precisao": "exata" if destino_local.exata and not destino.somente_cep else "aproximada",
            "endereco_normalizado": destino_local.endereco_formatado,
        }
        cache.set(chave, corpo)
        return JSONResponse(corpo)

    return app


app = criar_app()
