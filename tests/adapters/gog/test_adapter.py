from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.base import PermanentError, TransientError
from app.adapters.gog.adapter import GogAdapter


@pytest.fixture
def gog_adapter() -> GogAdapter:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    return GogAdapter(http=mock_http)


@pytest.mark.asyncio
async def test_gog_search_game_by_title_success(gog_adapter: GogAdapter) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "products": [
            {"id": "123", "title": "The Witcher 3", "slug": "the_witcher_3"}
        ]
    }
    gog_adapter._http.get.return_value = mock_response # type: ignore

    results = await gog_adapter.search_game_by_title("Witcher")
    assert len(results) == 1
    assert results[0]["id"] == "123"
    assert results[0]["title"] == "The Witcher 3"


@pytest.mark.asyncio
async def test_gog_get_price_success(gog_adapter: GogAdapter) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "products": [
            {
                "id": "123",
                "price": {
                    "finalMoney": {"amount": "15.00", "currency": "USD"},
                    "baseMoney": {"amount": "30.00", "currency": "USD"}
                }
            }
        ]
    }
    gog_adapter._http.get.return_value = mock_response # type: ignore

    price = await gog_adapter.get_price("123", "USD")
    assert price is not None
    assert price["price_final"] == 15.0
    assert price["price_initial"] == 30.0
    assert price["discount_percent"] == 50
    assert price["currency"] == "USD"


@pytest.mark.asyncio
async def test_gog_adapter_transient_error(gog_adapter: GogAdapter) -> None:
    gog_adapter._http.get.side_effect = httpx.RequestError("Network error") # type: ignore
    with pytest.raises(TransientError):
        await gog_adapter.search_game_by_title("Witcher")


@pytest.mark.asyncio
async def test_gog_adapter_permanent_error(gog_adapter: GogAdapter) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not found"
    gog_adapter._http.get.return_value = mock_response # type: ignore
    with pytest.raises(PermanentError):
        await gog_adapter.search_game_by_title("Witcher")
