from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.rfps import get_rfp_status
from app.main import app
from app.models.mixins import utc_now


@pytest.mark.parametrize(
    "stage,state,percent,terminal",
    [
        ("queued", "QUEUED", 5, False),
        ("extract_requirements", "PROCESSING", 30, False),
        ("evaluate_capabilities", "FAILED", 55, True),
        ("generate_proposal", "PROCESSING", 80, False),
        ("human_review", "REVIEW_PENDING", 95, False),
        ("approved", "APPROVED", 100, True),
    ],
)
async def test_status_progress_and_elapsed(stage, state, percent, terminal):
    now = utc_now()
    rfp_id = uuid4()
    rfp = SimpleNamespace(
        id=str(rfp_id),
        status=state,
        current_stage=stage,
        stage_started_at=now - timedelta(seconds=90),
        updated_at=now,
        error_message=None,
        processing_started_at=now - timedelta(seconds=100),
        completed_at=None,
        workflow_runs=[SimpleNamespace(created_at=now, attempt=2)],
    )
    response = await get_rfp_status(rfp_id, SimpleNamespace(get=AsyncMock(return_value=rfp)))
    assert response.progress_percent == percent
    assert response.is_terminal is terminal
    assert response.attempt == 2
    assert response.elapsed_seconds >= 90
    assert response.stage_started_at == rfp.stage_started_at


def test_example_documentation_is_disabled():
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        schema = client.get("/openapi.json").json()
        assert "/rfps/{rfp_id}/retry" in schema["paths"]
