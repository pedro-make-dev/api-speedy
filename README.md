# API de Taxa de Entrega

Calcula a taxa de entrega a partir da **distância real de rota (driving)** entre a loja
e o endereço do cliente. Aceita **endereço escrito** ou **CEP**.

A regra de negócio mora aqui, não na LLM. O agente de WhatsApp só manda o endereço e
lê o resultado.

## Tabela de faixas

| Distância de rota | Taxa |
|---|---|
| 0 – 3,0 km | R$ 10,99 |
| 3,01 – 4,0 km | R$ 11,99 |
| 4,01 – 4,5 km | R$ 13,99 |
| 4,51 – 5,5 km | R$ 14,99 |
| 5,51 – 6,0 km | R$ 15,99 |
| 6,01 – 6,5 km | R$ 16,99 |
| 6,51 – 7,0 km | R$ 17,99 |
| 7,01 – 7,5 km | R$ 18,99 |
| 7,51 – 8,0 km | R$ 19,99 |
| 8,01 – 8,5 km | R$ 20,99 |
| acima de 8,5 km | fora da área |

Para mudar valores ou faixas, edite só a tupla `FAIXAS` em [app/tarifa.py](app/tarifa.py).

## Endpoints

### `POST /calcular-entrega`

```json
{ "destino": "Rua Guaipá, 500 - Vila Leopoldina, São Paulo" }
```

`destino` aceita endereço completo **ou** CEP (`05815-010`, `05815010`, `CEP 05815-010`).
`origem` é opcional e sobrescreve o endereço da loja.

**Dentro da área (200):**

```json
{
  "success": true,
  "atendido": true,
  "distancia_km": 4.3,
  "raio": "até 4.5 km",
  "taxa_entrega": 13.99,
  "moeda": "BRL",
  "precisao": "exata",
  "endereco_normalizado": "R. Guaipá, 500 - Vila Leopoldina, São Paulo - SP, 05089-000, Brasil"
}
```

**Fora da área (200 — não é erro):**

```json
{
  "success": true,
  "atendido": false,
  "distancia_km": 9.2,
  "raio": "fora_da_area",
  "taxa_entrega": null,
  "moeda": "BRL",
  "precisao": "exata",
  "endereco_normalizado": "..."
}
```

**`precisao`** vale `"exata"` quando o Google cravou o imóvel, e `"aproximada"` quando o
cliente mandou só o CEP ou a rua sem número (usa o centroide). Se vier `aproximada` e a
distância estiver colada no limite de uma faixa, vale a LLM pedir o número da casa.

**Endereço vago é recusado, não estimado.** O Geocoding do Google sempre devolve alguma
coisa: `"São Paulo"` vira o centroide da cidade, um bairro vira o centroide do bairro e
`"asdfghjkl"` vira o centroide do Brasil. Cobrar entrega em cima desses pontos é chutar,
então a API só aceita resultado do nível da rua para baixo (rua, número, CEP,
estabelecimento) — o resto volta como `endereco_nao_encontrado` para a LLM pedir o
endereço completo. A lista está em `_TIPOS_ENTREGAVEIS` em [app/rotas.py](app/rotas.py).

**Erros:**

| Situação | HTTP | `error` |
|---|---|---|
| destino vazio ou ausente | 400 | `endereco_obrigatorio` |
| CEP não existe nos Correios | 422 | `cep_invalido` |
| Google não reconheceu o endereço | 422 | `endereco_nao_encontrado` |
| Endereço vago demais (só cidade/bairro) | 422 | `endereco_nao_encontrado` |
| Google fora do ar / cota estourada | 502 | `erro_roteamento` |
| `API_KEY` ligada e header errado | 401 | `nao_autorizado` |

```json
{ "success": false, "error": "endereco_nao_encontrado", "message": "..." }
```

### `GET /health`

`{"status": "ok"}` — é o health check do Render. Não chama o Google.

## Passo 1 — Chave do Google

1. [console.cloud.google.com](https://console.cloud.google.com) → crie um projeto.
2. **Faturamento**: ative. Sem billing, as APIs respondem `REQUEST_DENIED`.
   O Google dá um crédito mensal gratuito que cobre bem o volume de um delivery pequeno.
3. **APIs e serviços → Biblioteca**: ative as duas:
   - **Geocoding API**
   - **Routes API**
4. **Credenciais → Criar credenciais → Chave de API**. Copie a chave.
5. Em **Restrições de API**, limite a chave a essas duas APIs. Não use restrição por
   HTTP referrer nem por IP (o IP do Render muda) — a restrição por API já protege bem,
   e o `API_KEY` da própria API cobre o resto.

## Passo 2 — Subir para o Git

O Render lê de um repositório. Do diretório do projeto:

```bash
git init
git add .
git commit -m "API de cálculo de taxa de entrega"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/api-taxa-entrega.git
git push -u origin main
```

O `.gitignore` já bloqueia `.venv/` e `.env` — a chave do Google nunca vai para o repo.

## Passo 3 — Deploy no Render

**Opção A — Blueprint (usa o `render.yaml`, mais rápido):**

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**.
2. Conecte o repositório. O Render lê o `render.yaml` sozinho.
3. Ele vai pedir o valor de `GOOGLE_MAPS_API_KEY` (e `API_KEY`, que você pode deixar
   em branco). Cole a chave e confirme.
4. **Apply**.

**Opção B — Manual:**

1. **New +** → **Web Service** → conecte o repositório.
2. Preencha:
   - **Language:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. Em **Environment**, adicione:

| Variável | Valor |
|---|---|
| `GOOGLE_MAPS_API_KEY` | a chave do passo 1 |
| `ENDERECO_ORIGEM` | `R. José Barros Magaldi, 1247 - Jardim São João, São Paulo - SP, 05815-010` |
| `PYTHON_VERSION` | `3.12.8` |
| `API_KEY` | deixe vazia (endpoint aberto) |

4. **Create Web Service**.

### Sobre o plano

O `render.yaml` vem com `plan: starter` (US$ 7/mês) de propósito. **No plano free o
serviço hiberna após 15 min sem tráfego e a primeira requisição demora ~50 s** — para um
atendimento de WhatsApp isso é uma eternidade: o cliente acha que o bot travou. Se quiser
testar de graça primeiro, troque para `plan: free` no `render.yaml` (ou escolha Free no
painel) e suba para Starter quando entrar em produção.

## Passo 4 — Testar

Trocando `SUA-APP` pelo nome que o Render deu:

```bash
curl https://SUA-APP.onrender.com/health

curl -X POST https://SUA-APP.onrender.com/calcular-entrega \
  -H "Content-Type: application/json" \
  -d '{"destino": "Rua Guaipá, 500 - Vila Leopoldina, São Paulo"}'

curl -X POST https://SUA-APP.onrender.com/calcular-entrega \
  -H "Content-Type: application/json" \
  -d '{"destino": "05075-050"}'
```

Documentação interativa: `https://SUA-APP.onrender.com/docs`

## Passo 5 — Plugar no n8n

Nó **HTTP Request** (ou **Tool HTTP Request**, se for tool do agente):

- **Method:** `POST`
- **URL:** `https://SUA-APP.onrender.com/calcular-entrega`
- **Body Content Type:** `JSON`
- **Body:** `{ "destino": "{{ $json.endereco_do_cliente }}" }`

Se você ligar o `API_KEY`, adicione em **Headers**: `X-API-Key: <valor>`.

Na descrição da tool para o agente, deixe explícito que **ele não calcula nada** — só
passa o endereço e comunica o `taxa_entrega` que voltar. E lembre da regra do briefing:
**o cliente só vê a taxa depois da emissão do pedido.**

## Rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

Copie o `.env.example` para `.env` e preencha a `GOOGLE_MAPS_API_KEY`. O arquivo é lido
automaticamente e está no `.gitignore` — não vai para o repositório.

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload
```

No Render o `.env` não existe: lá valem as variáveis do painel. Se as duas coisas
existissem, o painel venceria (`override=False` em [app/config.py](app/config.py)).

## Testes

```bash
.venv\Scripts\python -m pytest
```

97 testes, nenhum toca a rede: as respostas do Google e do ViaCEP são mockadas com
`respx`. Cobrem as bordas de todas as faixas (3.0/3.01, 4.5/4.51, 8.5/8.51), os formatos
de CEP, a recusa de endereço vago, e cada caminho de erro.

## Como funciona por dentro

```
POST /calcular-entrega
  │
  ├─ cache (24h, em memória) — acerto devolve na hora, sem custo
  ├─ app/enderecos.py  → é CEP? ViaCEP monta o endereço. É endereço? passa direto
  ├─ app/rotas.py      → Google Geocoding (country:BR) → lat/lng + precisão
  ├─ app/rotas.py      → Google Routes (travelMode DRIVE) → metros
  └─ app/tarifa.py     → faixa → taxa
```

| Arquivo | Responsabilidade |
|---|---|
| [app/tarifa.py](app/tarifa.py) | tabela de faixas — função pura, sem I/O |
| [app/enderecos.py](app/enderecos.py) | CEP vs endereço, consulta ao ViaCEP |
| [app/rotas.py](app/rotas.py) | cliente Google (Geocoding + Routes) |
| [app/cache.py](app/cache.py) | cache LRU com TTL |
| [app/config.py](app/config.py) | variáveis de ambiente |
| [app/main.py](app/main.py) | rotas HTTP, autenticação, tradução de erros |

O cache é por processo e some no restart — é só economia de cota, não fonte de verdade.
O ViaCEP é dispensável: se ele cair, a API manda o CEP puro para o Google, que resolve
CEP brasileiro sozinho.
