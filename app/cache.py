"""Cache LRU com expiração, em memória. Existe para não pagar duas vezes ao Google
pelo mesmo endereço — o cliente repete, e o n8n dá retry."""

import time
from collections import OrderedDict
from typing import Any, Callable


class CacheTTL:
    def __init__(
        self,
        ttl_segundos: float,
        tamanho_maximo: int = 5000,
        relogio: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_segundos
        self._tamanho_maximo = tamanho_maximo
        self._relogio = relogio
        self._itens: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, chave: str) -> Any | None:
        item = self._itens.get(chave)
        if item is None:
            return None

        gravado_em, valor = item
        if self._relogio() - gravado_em > self._ttl:
            del self._itens[chave]
            return None

        self._itens.move_to_end(chave)
        return valor

    def set(self, chave: str, valor: Any) -> None:
        self._itens[chave] = (self._relogio(), valor)
        self._itens.move_to_end(chave)
        while len(self._itens) > self._tamanho_maximo:
            self._itens.popitem(last=False)
