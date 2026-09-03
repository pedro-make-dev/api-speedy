import pytest

from app.config import ENDERECO_ORIGEM_PADRAO, carregar_config


@pytest.fixture(autouse=True)
def fora_do_projeto(monkeypatch, tmp_path):
    """Roda em um diretório vazio: o .env real do desenvolvedor não pode vazar
    para dentro dos testes de configuração."""
    monkeypatch.chdir(tmp_path)


def test_exige_a_chave_do_google(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_MAPS_API_KEY"):
        carregar_config()


def test_usa_o_endereco_da_loja_como_origem_padrao(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave")
    monkeypatch.delenv("ENDERECO_ORIGEM", raising=False)

    assert carregar_config().endereco_origem == ENDERECO_ORIGEM_PADRAO


def test_origem_pode_ser_trocada_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave")
    monkeypatch.setenv("ENDERECO_ORIGEM", "Av. Paulista, 1000 - São Paulo")

    assert carregar_config().endereco_origem == "Av. Paulista, 1000 - São Paulo"


def test_api_key_vazia_significa_endpoint_aberto(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave")
    monkeypatch.delenv("API_KEY", raising=False)

    assert carregar_config().api_key == ""


def test_le_a_chave_de_um_arquivo_env_local(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("ENDERECO_ORIGEM", raising=False)
    (tmp_path / ".env").write_text(
        "GOOGLE_MAPS_API_KEY=chave-do-arquivo\nENDERECO_ORIGEM=Av. Paulista, 1\n",
        encoding="utf-8",
    )

    config = carregar_config()

    assert config.google_api_key == "chave-do-arquivo"
    assert config.endereco_origem == "Av. Paulista, 1"


def test_variavel_do_ambiente_vence_o_arquivo_env(monkeypatch, tmp_path):
    # No Render não existe .env, mas se existisse o painel teria que mandar mais.
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave-do-painel")
    (tmp_path / ".env").write_text(
        "GOOGLE_MAPS_API_KEY=chave-do-arquivo\n", encoding="utf-8"
    )

    assert carregar_config().google_api_key == "chave-do-painel"
