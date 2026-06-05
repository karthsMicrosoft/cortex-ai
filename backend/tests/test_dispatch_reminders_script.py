import json
from unittest.mock import AsyncMock, patch

import pytest

from scripts import dispatch_reminders


@pytest.mark.asyncio
async def test_main_returns_zero_and_logs_dispatch_result():
    counters = {
        "found": 1,
        "claimed": 1,
        "sent_push": 0,
        "sent_email": 1,
        "failed": 0,
        "rolled": 0,
    }

    with (
        patch("scripts.dispatch_reminders.dispatch", new=AsyncMock(return_value=counters)) as mock_dispatch,
        patch("scripts.dispatch_reminders.logger.info") as mock_info,
    ):
        exit_code = await dispatch_reminders.main()

    assert exit_code == 0
    mock_dispatch.assert_awaited_once()
    mock_info.assert_called_once()
    assert mock_info.call_args.args[0] == "reminders.dispatch_complete %s"
    assert json.loads(mock_info.call_args.args[1]) == counters
