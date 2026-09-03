import httpx
import pytest
import respx

from app.enderecos import CepInvalido, EnderecoVazio, normalizar_cep, resolver_destino

VIACEP = "https://viacep.com.br/ws/05815010/json/"

RESPOSTA_VIACEP = {
    "cep": "05815-010",
    "logradouro": "Rua José Barros Magaldi",
    "complemento": "",
    "bairro": "Jardim São João",
    "localidade": "São Paulo",
    "uf": "SP",
}


@pytest.mark.parametrize(
    "texto",
    ["05815010", "05815-010", "cep 05815-010", "CEP: 05815.010", "  05815 010 "],
)
def test_reconhece_um_cep_isolado_em_varios_formatos(texto):
    assert normalizar_cep(texto) == "05815010"


@pytest.mark.parametrize(
    "texto",
    [
        "Rua José Barros Magaldi, 1247",
        "Rua José Barros Magaldi, 1247 - 05815-010",
        "0581501",
        "058150100",
        "",
    ],
)
def test_nao_confunde_endereco_com_cep(texto):
    assert normalizar_cep(texto) is None


@pytest.mark.anyio
@respx.mock
async def test_cep_isolado_vira_endereco_completo_pelo_viacep():
    respx.get(VIACEP).mock(return_value=httpx.Response(200, json=RESPOSTA_VIACEP))

    async with httpx.AsyncClient() as client:
        destino = await resolver_destino("05815-010", client)

    assert destino.consulta == (
        "Rua José Barros Magaldi, Jardim São João, São Paulo - SP, 05815-010"
    )
    assert destino.somente_cep is True


@pytest.mark.anyio
@respx.mock
async def test_endereco_completo_vai_direto_para_o_geocoder():
    rota = respx.get(url__startswith="https://viacep.com.br")

    async with httpx.AsyncClient() as client:
        destino = await resolver_destino("Rua Guaipá, 500 - Vila Leopoldina, SP", client)

    assert destino.consulta == "Rua Guaipá, 500 - Vila Leopoldina, SP"
    assert destino.somente_cep is False
    assert not rota.called


@pytest.mark.anyio
@respx.mock
async def test_cep_inexistente_e_rejeitado():
    respx.get(VIACEP).mock(return_value=httpx.Response(200, json={"erro": "true"}))

    async with httpx.AsyncClient() as client:
        with pytest.raises(CepInvalido):
            await resolver_destino("05815-010", client)


@pytest.mark.anyio
@respx.mock
async def test_viacep_fora_do_ar_nao_derruba_a_consulta():
    respx.get(VIACEP).mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        destino = await resolver_destino("05815-010", client)

    # degrada para o CEP puro; o geocoder do Google resolve CEP sozinho
    assert destino.consulta == "05815-010, Brasil"
    assert destino.somente_cep is True


@pytest.mark.anyio
@pytest.mark.parametrize("texto", ["", "   ", "\n"])
async def test_destino_vazio_e_rejeitado(texto):
    async with httpx.AsyncClient() as client:
        with pytest.raises(EnderecoVazio):
            await resolver_destino(texto, client)
