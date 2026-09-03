import httpx
import pytest

GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"
ORIGEM_TEXTO = "R. José Barros Magaldi, 1247 - Jardim São João, São Paulo - SP, 05815-010"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "chave-de-teste")
    monkeypatch.setenv("ENDERECO_ORIGEM", ORIGEM_TEXTO)
    monkeypatch.delenv("API_KEY", raising=False)


@pytest.fixture
def app(ambiente):
    from app.main import criar_app

    return criar_app()


@pytest.fixture
async def cliente(app):
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://api") as c:
        yield c


def geocode_ok(lat, lng, location_type="ROOFTOP", endereco="Endereço Formatado",
               types=("street_address",)):
    return httpx.Response(
        200,
        json={
            "status": "OK",
            "results": [
                {
                    "formatted_address": endereco,
                    "types": list(types),
                    "geometry": {
                        "location": {"lat": lat, "lng": lng},
                        "location_type": location_type,
                    },
                }
            ],
        },
    )
