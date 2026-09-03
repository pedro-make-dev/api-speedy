"""Cliente das APIs do Google: Geocoding (endereço → coordenada) e Routes (rota de carro)."""

from dataclasses import dataclass

import httpx

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
TIMEOUT = httpx.Timeout(10.0)

# O Google só crava o ponto exato do imóvel em ROOFTOP; o resto é interpolação
# ou centroide (típico de CEP sem número).
_PRECISAO_EXATA = "ROOFTOP"

# O Geocoding sempre devolve *alguma coisa*: "asdfghjkl" vira o centroide do Brasil,
# "São Paulo" vira o centroide da cidade e um bairro vira o centroide do bairro.
# Cobrar entrega em cima desses pontos é chutar. Só aceitamos resultado do nível
# da rua para baixo — o resto volta como endereço não encontrado, e a LLM pede
# o endereço completo ao cliente.
_TIPOS_ENTREGAVEIS = frozenset(
    {
        "street_address",
        "premise",
        "subpremise",
        "route",
        "intersection",
        "postal_code",
        "plus_code",
        "establishment",
        "point_of_interest",
    }
)


class EnderecoNaoEncontrado(Exception):
    """O Google não reconheceu o endereço."""


class ErroRoteamento(Exception):
    """Falha do provedor: chave inválida, cota estourada, indisponibilidade, sem rota."""


@dataclass(frozen=True)
class Local:
    lat: float
    lng: float
    endereco_formatado: str
    exata: bool


async def geocodificar(consulta: str, client: httpx.AsyncClient, api_key: str) -> Local:
    try:
        resposta = await client.get(
            GEOCODE_URL,
            params={
                "address": consulta,
                "components": "country:BR",
                "language": "pt-BR",
                "key": api_key,
            },
            timeout=TIMEOUT,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise ErroRoteamento(f"geocoding indisponível: {erro}") from erro

    # A ordem importa: REQUEST_DENIED/OVER_QUERY_LIMIT também vêm com results vazio,
    # e são falha nossa (chave/cota), não endereço inexistente.
    status = dados.get("status")
    if status == "ZERO_RESULTS":
        raise EnderecoNaoEncontrado(f"endereço não localizado: {consulta}")
    if status != "OK":
        raise ErroRoteamento(f"geocoding retornou {status}")
    if not dados.get("results"):
        raise EnderecoNaoEncontrado(f"endereço não localizado: {consulta}")

    resultado = dados["results"][0]
    if not _TIPOS_ENTREGAVEIS.intersection(resultado.get("types", [])):
        raise EnderecoNaoEncontrado(
            f"resultado vago demais para entrega ({resultado.get('types')}): {consulta}"
        )

    geometria = resultado["geometry"]
    return Local(
        lat=geometria["location"]["lat"],
        lng=geometria["location"]["lng"],
        endereco_formatado=resultado.get("formatted_address", consulta),
        exata=geometria.get("location_type") == _PRECISAO_EXATA,
    )


async def distancia_rota_km(
    origem: Local, destino: Local, client: httpx.AsyncClient, api_key: str
) -> float:
    """Distância dirigindo, em km. Nunca linha reta."""
    corpo = {
        "origin": {"location": {"latLng": {"latitude": origem.lat, "longitude": origem.lng}}},
        "destination": {
            "location": {"latLng": {"latitude": destino.lat, "longitude": destino.lng}}
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
        "units": "METRIC",
        "languageCode": "pt-BR",
        "regionCode": "BR",
    }
    cabecalhos = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.distanceMeters",
        "Content-Type": "application/json",
    }

    try:
        resposta = await client.post(
            ROUTES_URL, json=corpo, headers=cabecalhos, timeout=TIMEOUT
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise ErroRoteamento(f"routes indisponível: {erro}") from erro

    rotas = dados.get("routes") or []
    if not rotas or "distanceMeters" not in rotas[0]:
        raise ErroRoteamento("nenhuma rota de carro entre origem e destino")

    return round(rotas[0]["distanceMeters"] / 1000, 2)
