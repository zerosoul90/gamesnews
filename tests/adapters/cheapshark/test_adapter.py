from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.base import TransientError
from app.adapters.cheapshark.adapter import CheapSharkAdapter


@pytest.fixture
def cheapshark_adapter() -> CheapSharkAdapter:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    return CheapSharkAdapter(http=mock_http)


@pytest.mark.asyncio
async def test_cheapshark_search_game_success(cheapshark_adapter: CheapSharkAdapter) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"gameID": "123", "external": "Batman Arkham Knight", "cheapest": "4.99"}
    ]
    cheapshark_adapter._http.get.return_value = mock_response # type: ignore

    results = await cheapshark_adapter.search_game("Batman")
    assert len(results) == 1
    assert results[0]["gameID"] == "123"
    assert results[0]["title"] == "Batman Arkham Knight"
    assert results[0]["cheapest"] == 4.99


@pytest.mark.asyncio
async def test_cheapshark_get_historical_low_success(cheapshark_adapter: CheapSharkAdapter) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "info": {"title": "Batman Arkham Knight"},
        "cheapestPriceEver": {"price": "4.99", "date": 1612345678}
    }
    cheapshark_adapter._http.get.return_value = mock_response # type: ignore

    details = await cheapshark_adapter.get_historical_low("123")
    assert details is not None
    assert details["title"] == "Batman Arkham Knight"
    assert details["lowest_ever_price"] == 4.99
    assert details["lowest_ever_date"] == 1612345678


@pytest.mark.asyncio
async def test_cheapshark_adapter_transient_error(cheapshark_adapter: CheapSharkAdapter) -> None:
    cheapshark_adapter._http.get.side_effect = httpx.RequestError("Network error") # type: ignore
    with pytest.raises(TransientError):
        await cheapshark_adapter.search_game("Batman")
