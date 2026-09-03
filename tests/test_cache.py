from app.cache import CacheTTL


class RelogioFalso:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += segundos


def test_devolve_o_valor_guardado():
    cache = CacheTTL(ttl_segundos=60)

    cache.set("05815010", "resultado")

    assert cache.get("05815010") == "resultado"


def test_chave_desconhecida_devolve_none():
    assert CacheTTL(ttl_segundos=60).get("nunca-visto") is None


def test_valor_expira_depois_do_ttl():
    relogio = RelogioFalso()
    cache = CacheTTL(ttl_segundos=60, relogio=relogio)
    cache.set("chave", "resultado")

    relogio.avancar(61)

    assert cache.get("chave") is None


def test_valor_sobrevive_dentro_do_ttl():
    relogio = RelogioFalso()
    cache = CacheTTL(ttl_segundos=60, relogio=relogio)
    cache.set("chave", "resultado")

    relogio.avancar(59)

    assert cache.get("chave") == "resultado"


def test_descarta_a_entrada_menos_usada_ao_atingir_o_limite():
    cache = CacheTTL(ttl_segundos=60, tamanho_maximo=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # "a" passa a ser a mais recente, "b" vira a candidata

    cache.set("c", 3)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
