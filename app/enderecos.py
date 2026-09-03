"""Normalização do endereço que chega do WhatsApp: CEP isolado ou endereço escrito."""

import re
from dataclasses import dataclass

import httpx

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
TIMEOUT_VIACEP = httpx.Timeout(5.0)

_PREFIXO_CEP = re.compile(r"^cep\b", re.IGNORECASE)
_SEPARADORES = re.compile(r"[\s.\-:]")
_OITO_DIGITOS = re.compile(r"\d{8}")


class EnderecoVazio(Exception):
    """Nenhum destino foi informado."""


class CepInvalido(Exception):
    """O CEP tem formato de CEP, mas não existe na base dos Correios."""


@dataclass(frozen=True)
class Destino:
    consulta: str
    somente_cep: bool


def normalizar_cep(texto: str) -> str | None:
    """Devolve os 8 dígitos se o texto for *só* um CEP, senão None.

    "05815-010" e "CEP: 05815.010" são CEP. Um endereço que por acaso contém
    um CEP não é — nesse caso o texto inteiro vale mais para o geocoder.
    """
    if not texto:
        return None

    limpo = _SEPARADORES.sub("", _PREFIXO_CEP.sub("", texto.strip()))
    return limpo if _OITO_DIGITOS.fullmatch(limpo) else None


def formatar_cep(cep: str) -> str:
    return f"{cep[:5]}-{cep[5:]}"


async def resolver_destino(texto: str, client: httpx.AsyncClient) -> Destino:
    """Transforma a entrada crua numa string que o geocoder entende bem."""
    if not texto or not texto.strip():
        raise EnderecoVazio("informe o endereço do cliente")

    cep = normalizar_cep(texto)
    if cep is None:
        return Destino(consulta=texto.strip(), somente_cep=False)

    endereco = await _consultar_viacep(cep, client)
    if endereco is None:
        # ViaCEP indisponível: o Google resolve CEP brasileiro sozinho.
        return Destino(consulta=f"{formatar_cep(cep)}, Brasil", somente_cep=True)

    return Destino(consulta=endereco, somente_cep=True)


async def _consultar_viacep(cep: str, client: httpx.AsyncClient) -> str | None:
    """Endereço formatado, ou None se o ViaCEP não respondeu. CepInvalido se não existe."""
    try:
        resposta = await client.get(VIACEP_URL.format(cep=cep), timeout=TIMEOUT_VIACEP)
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return None

    # O ViaCEP sinaliza CEP inexistente com "erro", ora string ora booleano.
    if str(dados.get("erro", "")).lower() == "true":
        raise CepInvalido(f"CEP {formatar_cep(cep)} não encontrado")

    partes = [
        dados.get("logradouro"),
        dados.get("bairro"),
        f"{dados.get('localidade')} - {dados.get('uf')}",
        formatar_cep(cep),
    ]
    return ", ".join(p for p in partes if p)
