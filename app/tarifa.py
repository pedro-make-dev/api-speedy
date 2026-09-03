"""Tabela de taxas de entrega. Função pura, sem I/O — o coração da regra de negócio."""

from dataclasses import dataclass

# (limite superior da faixa em km, taxa em BRL). Ordenada do menor para o maior.
FAIXAS: tuple[tuple[float, float], ...] = (
    (3.0, 10.99),
    (4.0, 11.99),
    (4.5, 13.99),
    (5.5, 14.99),
    (6.0, 15.99),
    (6.5, 16.99),
    (7.0, 17.99),
    (7.5, 18.99),
    (8.0, 19.99),
    (8.5, 20.99),
)

LIMITE_ATENDIMENTO_KM = FAIXAS[-1][0]


@dataclass(frozen=True)
class Tarifa:
    atendido: bool
    taxa: float | None
    raio: str


def calcular_taxa(distancia_km: float) -> Tarifa:
    """Devolve a tarifa da faixa em que a distância de rota se encaixa.

    A distância é arredondada para 2 casas antes da comparação: o provedor
    entrega metros inteiros, e 8500 m não pode cair fora da faixa de 8.5 km
    por um resíduo de ponto flutuante.
    """
    if distancia_km < 0:
        raise ValueError(f"distância não pode ser negativa: {distancia_km}")

    km = round(distancia_km, 2)

    for limite, taxa in FAIXAS:
        if km <= limite:
            return Tarifa(atendido=True, taxa=taxa, raio=f"até {limite} km")

    return Tarifa(atendido=False, taxa=None, raio="fora_da_area")
