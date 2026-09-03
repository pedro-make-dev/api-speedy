import pytest

from app.tarifa import calcular_taxa


@pytest.mark.parametrize(
    "km, taxa_esperada",
    [
        (0.0, 10.99),
        (1.7, 10.99),
        (3.0, 10.99),
        (3.01, 11.99),
        (4.0, 11.99),
        (4.01, 13.99),
        (4.3, 13.99),
        (4.5, 13.99),
        (4.51, 14.99),
        (5.5, 14.99),
        (5.51, 15.99),
        (6.0, 15.99),
        (6.01, 16.99),
        (6.5, 16.99),
        (6.51, 17.99),
        (7.0, 17.99),
        (7.01, 18.99),
        (7.5, 18.99),
        (7.51, 19.99),
        (8.0, 19.99),
        (8.01, 20.99),
        (8.5, 20.99),
    ],
)
def test_retorna_a_taxa_da_faixa_correspondente(km, taxa_esperada):
    resultado = calcular_taxa(km)

    assert resultado.atendido is True
    assert resultado.taxa == taxa_esperada


@pytest.mark.parametrize("km", [8.51, 9.2, 40.0])
def test_acima_de_8_5_km_fica_fora_da_area(km):
    resultado = calcular_taxa(km)

    assert resultado.atendido is False
    assert resultado.taxa is None
    assert resultado.raio == "fora_da_area"


def test_descreve_o_raio_da_faixa_atendida():
    assert calcular_taxa(4.3).raio == "até 4.5 km"
    assert calcular_taxa(0.4).raio == "até 3.0 km"
    assert calcular_taxa(8.5).raio == "até 8.5 km"


def test_arredonda_a_distancia_para_duas_casas_antes_de_comparar():
    # 8.5004 km vem do provedor como 8500.4 metros; deve continuar na última faixa
    assert calcular_taxa(8.5004).taxa == 20.99


def test_distancia_negativa_e_rejeitada():
    with pytest.raises(ValueError):
        calcular_taxa(-1.0)
