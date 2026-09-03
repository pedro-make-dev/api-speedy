import json

import httpx
import pytest
import respx

from app.rotas import (
    EnderecoNaoEncontrado,
    ErroRoteamento,
    Local,
    distancia_rota_km,
    geocodificar,
)

GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"

ORIGEM = Local(lat=-23.52, lng=-46.75, endereco_formatado="Origem", exata=True)
DESTINO = Local(lat=-23.53, lng=-46.71, endereco_formatado="Destino", exata=True)


def resposta_geocode(location_type="ROOFTOP", status="OK", types=("street_address",)):
    return {
        "status": status,
        "results": [
            {
                "formatted_address": "R. José Barros Magaldi, 1247 - Jardim São João, "
                "São Paulo - SP, 05815-010, Brasil",
                "types": list(types),
                "geometry": {
                    "location": {"lat": -23.5205, "lng": -46.7512},
                    "location_type": location_type,
                },
            }
        ],
    }


@pytest.mark.anyio
@respx.mock
async def test_geocodifica_um_endereco():
    respx.get(GEOCODE).mock(return_value=httpx.Response(200, json=resposta_geocode()))

    async with httpx.AsyncClient() as client:
        local = await geocodificar("R. José Barros Magaldi, 1247", client, "chave")

    assert local.lat == -23.5205
    assert local.lng == -46.7512
    assert local.endereco_formatado.startswith("R. José Barros Magaldi, 1247")
    assert local.exata is True


@pytest.mark.anyio
@respx.mock
async def test_restringe_a_busca_ao_brasil():
    rota = respx.get(GEOCODE).mock(
        return_value=httpx.Response(200, json=resposta_geocode())
    )

    async with httpx.AsyncClient() as client:
        await geocodificar("Rua Guaipá, 500", client, "chave")

    params = rota.calls.last.request.url.params
    assert params["components"] == "country:BR"
    assert params["key"] == "chave"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "location_type", ["GEOMETRIC_CENTER", "APPROXIMATE", "RANGE_INTERPOLATED"]
)
@respx.mock
async def test_marca_como_inexata_quando_o_google_nao_acha_o_numero(location_type):
    respx.get(GEOCODE).mock(
        return_value=httpx.Response(200, json=resposta_geocode(location_type))
    )

    async with httpx.AsyncClient() as client:
        local = await geocodificar("05815-010", client, "chave")

    assert local.exata is False


@pytest.mark.anyio
@respx.mock
async def test_endereco_inexistente_e_reportado():
    respx.get(GEOCODE).mock(
        return_value=httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(EnderecoNaoEncontrado):
            await geocodificar("asdfghjkl", client, "chave")


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["REQUEST_DENIED", "OVER_QUERY_LIMIT", "UNKNOWN_ERROR"])
@respx.mock
async def test_chave_invalida_ou_cota_estourada_vira_erro_de_roteamento(status):
    respx.get(GEOCODE).mock(
        return_value=httpx.Response(200, json={"status": status, "results": []})
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ErroRoteamento):
            await geocodificar("Rua Guaipá, 500", client, "chave")


@pytest.mark.anyio
@respx.mock
async def test_google_fora_do_ar_vira_erro_de_roteamento():
    respx.get(GEOCODE).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(ErroRoteamento):
            await geocodificar("Rua Guaipá, 500", client, "chave")


@pytest.mark.anyio
@respx.mock
async def test_converte_a_distancia_da_rota_de_metros_para_km():
    respx.post(ROUTES).mock(
        return_value=httpx.Response(200, json={"routes": [{"distanceMeters": 4321}]})
    )

    async with httpx.AsyncClient() as client:
        km = await distancia_rota_km(ORIGEM, DESTINO, client, "chave")

    assert km == 4.32


@pytest.mark.anyio
@respx.mock
async def test_pede_rota_de_carro_e_so_o_campo_de_distancia():
    rota = respx.post(ROUTES).mock(
        return_value=httpx.Response(200, json={"routes": [{"distanceMeters": 1000}]})
    )

    async with httpx.AsyncClient() as client:
        await distancia_rota_km(ORIGEM, DESTINO, client, "chave")

    requisicao = rota.calls.last.request
    corpo = json.loads(requisicao.content)
    assert corpo["travelMode"] == "DRIVE"
    assert corpo["origin"]["location"]["latLng"] == {
        "latitude": -23.52,
        "longitude": -46.75,
    }
    assert requisicao.headers["X-Goog-Api-Key"] == "chave"
    assert requisicao.headers["X-Goog-FieldMask"] == "routes.distanceMeters"


@pytest.mark.anyio
@respx.mock
async def test_sem_rota_dirigivel_vira_erro_de_roteamento():
    respx.post(ROUTES).mock(return_value=httpx.Response(200, json={"routes": []}))

    async with httpx.AsyncClient() as client:
        with pytest.raises(ErroRoteamento):
            await distancia_rota_km(ORIGEM, DESTINO, client, "chave")


@pytest.mark.anyio
@respx.mock
async def test_routes_api_com_erro_http_vira_erro_de_roteamento():
    respx.post(ROUTES).mock(return_value=httpx.Response(403, json={"error": "denied"}))

    async with httpx.AsyncClient() as client:
        with pytest.raises(ErroRoteamento):
            await distancia_rota_km(ORIGEM, DESTINO, client, "chave")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "types",
    [
        ["country", "political"],  # "asdfghjkl" cai no centroide do Brasil
        ["locality", "political"],  # "São Paulo"
        ["administrative_area_level_2", "political"],  # "Guarulhos - SP"
        ["administrative_area_level_1", "political"],  # "SP"
        ["political", "sublocality", "sublocality_level_1"],  # "Jardim São Luís"
        ["neighborhood", "political"],
    ],
)
@respx.mock
async def test_resultado_vago_demais_nao_serve_de_endereco_de_entrega(types):
    respx.get(GEOCODE).mock(
        return_value=httpx.Response(
            200, json=resposta_geocode(location_type="APPROXIMATE", types=types)
        )
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(EnderecoNaoEncontrado):
            await geocodificar("São Paulo", client, "chave")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "types",
    [
        ["street_address"],
        ["street_address", "subpremise"],
        ["premise"],
        ["route"],  # rua sem número: impreciso, mas é um endereço de verdade
        ["postal_code"],
        ["establishment", "point_of_interest"],
    ],
)
@respx.mock
async def test_resultado_no_nivel_da_rua_ou_mais_fino_e_aceito(types):
    respx.get(GEOCODE).mock(
        return_value=httpx.Response(200, json=resposta_geocode(types=types))
    )

    async with httpx.AsyncClient() as client:
        local = await geocodificar("Rua Ernest Renan, 500", client, "chave")

    assert local.lat == -23.5205
