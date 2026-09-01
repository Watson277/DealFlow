import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.session import async_session_factory, engine
from app.main import app
from app.models import Customer

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run database integration tests",
    ),
]


@pytest.mark.asyncio
async def test_customer_create_get_list_and_conflict() -> None:
    suffix = uuid4().hex[:12]
    submitted_code = f"customer-{suffix}"
    normalized_code = submitted_code.upper()
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/customers",
                json={
                    "name": "Stellar Integration Customer",
                    "code": submitted_code,
                    "industry": "Technology",
                    "primary_contact_name": "Test Contact",
                    "primary_contact_email": "contact@example.com",
                    "extra_data": {"source": "integration-test"},
                },
            )
            assert create_response.status_code == 201, create_response.text
            created = create_response.json()
            assert created["code"] == normalized_code

            get_response = await client.get(f"/customers/{created['id']}")
            assert get_response.status_code == 200
            assert get_response.json()["name"] == "Stellar Integration Customer"

            list_response = await client.get(
                "/customers",
                params={"search": suffix, "offset": 0, "limit": 10},
            )
            assert list_response.status_code == 200
            page = list_response.json()
            assert page["total"] == 1
            assert page["items"][0]["id"] == created["id"]

            conflict_response = await client.post(
                "/customers",
                json={"name": "Duplicate Customer", "code": submitted_code},
            )
            assert conflict_response.status_code == 409

            missing_response = await client.get(f"/customers/{uuid4()}")
            assert missing_response.status_code == 404
    finally:
        async with async_session_factory() as session, session.begin():
            await session.execute(delete(Customer).where(Customer.code == normalized_code))
        await engine.dispose()
