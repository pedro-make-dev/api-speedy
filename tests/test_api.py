import httpx
import pytest
import respx

from tests.conftest import GEOCODE, ROUTES, geocode_ok

pytestmark = pytest.mark.anyio


def mock_google(metros=4300, location_type="ROOFTOP", endereco="Destino Formatado"):
    """Origem e destino saem do mesmo endpoint; separa pelo endereço consultado.

    Devolve a lista de endereços geocodificados e a rota do Routes API, para os
    testes que contam quantas vezes o Google foi chamado.
    """
    geocodificados = []

    def responder_geocode(request):
        consultado = request.url.params["address"]
        geocodificados.append(consultado)
        if "Barros Magaldi" in consultado:
            return geocode_ok(-23.5205, -46.7512, endereco="Origem Formatada")
        return geocode_ok(-23.53, -46.71, location_type, endereco)

    respx.get(GEOCODE).mock(side_effect=responder_geocode)
    rota = respx.post(ROUTES).mock(
        return_value=httpx.Response(200, json={"routes": [{"distanceMeters": metros}]})
    )
    return geocodificados, rota


async def test_health_responde_sem_tocar_no_google(cliente):
    resposta = await cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


@respx.mock
async def test_endereco_dentro_da_area_devolve_a_taxa(cliente):
    mock_google(metros=4300)

    resposta = await cliente.post(
        "/calcular-entrega", json={"destino": "Rua Guaipá, 500 - Vila Leopoldina"}
    )

    assert resposta.status_code == 200
    assert resposta.json() == {
        "success": True,
        "atendido": True,
        "distancia_km": 4.3,
        "raio": "até 4.5 km",
        "taxa_entrega": 13.99,
        "moeda": "BRL",
        "precisao": "exata",
        "endereco_normalizado": "Destino Formatado",
    }


@respx.mock
async def test_endereco_fora_da_area_nao_e_erro(cliente):
    mock_google(metros=9200)

    resposta = await cliente.post("/calcular-entrega", json={"destino": "Guarulhos, SP"})

    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["success"] is True
    assert corpo["atendido"] is False
    assert corpo["distancia_km"] == 9.2
    assert corpo["raio"] == "fora_da_area"
    assert corpo["taxa_entrega"] is None


@respx.mock
async def test_cep_sem_numero_marca_a_distancia_como_aproximada(cliente):
    respx.get(url__startswith="https://viacep.com.br").mock(
        return_value=httpx.Response(
            200,
            json={
                "logradouro": "Rua Guaipá",
                "bairro": "Vila Leopoldina",
                "localidade": "São Paulo",
                "uf": "SP",
            },
        )
    )
    mock_google(metros=4300, location_type="GEOMETRIC_CENTER")

    resposta = await cliente.post("/calcular-entrega", json={"destino": "05075-050"})

    assert resposta.status_code == 200
    assert resposta.json()["precisao"] == "aproximada"
    assert resposta.json()["taxa_entrega"] == 13.99


@respx.mock
async def test_endereco_com_numero_exato_nao_e_marcado_como_aproximado(cliente):
    mock_google(metros=1000, location_type="ROOFTOP")

    resposta = await cliente.post("/calcular-entrega", json={"destino": "Rua Guaipá, 500"})

    assert resposta.json()["precisao"] == "exata"


@pytest.mark.parametrize("corpo", [{"destino": ""}, {"destino": "   "}, {}])
async def test_destino_vazio_e_recusado(cliente, corpo):
    resposta = await cliente.post("/calcular-entrega", json=corpo)

    assert resposta.status_code == 400
    assert resposta.json()["success"] is False
    assert resposta.json()["error"] == "endereco_obrigatorio"


@respx.mock
async def test_cep_inexistente_e_recusado(cliente):
    respx.get(url__startswith="https://viacep.com.br").mock(
        return_value=httpx.Response(200, json={"erro": "true"})
    )

    resposta = await cliente.post("/calcular-entrega", json={"destino": "99999-999"})

    assert resposta.status_code == 422
    assert resposta.json()["error"] == "cep_invalido"


@respx.mock
async def test_endereco_desconhecido_e_recusado(cliente):
    def responder(request):
        if "Barros Magaldi" in request.url.params["address"]:
            return geocode_ok(-23.5205, -46.7512)
        return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})

    respx.get(GEOCODE).mock(side_effect=responder)

    resposta = await cliente.post("/calcular-entrega", json={"destino": "asdfghjkl"})

    assert resposta.status_code == 422
    assert resposta.json()["error"] == "endereco_nao_encontrado"


@respx.mock
async def test_google_indisponivel_vira_502(cliente):
    respx.get(GEOCODE).mock(return_value=httpx.Response(500))

    resposta = await cliente.post("/calcular-entrega", json={"destino": "Rua Guaipá, 500"})

    assert resposta.status_code == 502
    assert resposta.json()["error"] == "erro_roteamento"


@respx.mock
async def test_destino_repetido_nao_consulta_o_google_de_novo(cliente):
    _, rota = mock_google(metros=4300)

    primeira = await cliente.post("/calcular-entrega", json={"destino": "Rua Guaipá, 500"})
    segunda = await cliente.post("/calcular-entrega", json={"destino": "rua guaipá, 500 "})

    assert primeira.json() == segunda.json()
    assert rota.call_count == 1


@respx.mock
async def test_origem_e_geocodificada_uma_unica_vez(cliente):
    geocodificados, _ = mock_google(metros=4300)

    await cliente.post("/calcular-entrega", json={"destino": "Rua Guaipá, 500"})
    await cliente.post("/calcular-entrega", json={"destino": "Rua Clélia, 200"})

    origens = [e for e in geocodificados if "Barros Magaldi" in e]
    assert len(origens) == 1
    assert len(geocodificados) == 3  # 1 origem + 2 destinos distintos


@respx.mock
async def test_api_key_configurada_bloqueia_quem_nao_manda_o_header(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave-de-teste")
    monkeypatch.setenv("API_KEY", "segredo")
    from app.main import criar_app

    transporte = httpx.ASGITransport(app=criar_app())
    async with httpx.AsyncClient(transport=transporte, base_url="http://api") as c:
        resposta = await c.post("/calcular-entrega", json={"destino": "Rua Guaipá, 500"})

    assert resposta.status_code == 401
    assert resposta.json()["error"] == "nao_autorizado"


@respx.mock
async def test_api_key_correta_libera_o_calculo(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave-de-teste")
    monkeypatch.setenv("API_KEY", "segredo")
    mock_google(metros=4300)
    from app.main import criar_app

    transporte = httpx.ASGITransport(app=criar_app())
    async with httpx.AsyncClient(transport=transporte, base_url="http://api") as c:
        resposta = await c.post(
            "/calcular-entrega",
            json={"destino": "Rua Guaipá, 500"},
            headers={"X-API-Key": "segredo"},
        )

    assert resposta.status_code == 200
    assert resposta.json()["taxa_entrega"] == 13.99
