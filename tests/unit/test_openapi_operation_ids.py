"""The frontend's generated client names each SDK function after an operation ID."""

from __future__ import annotations

from collections import Counter

from molabel.app.main import create_app


def test_every_operation_id_is_its_route_name_and_unique():
    spec = create_app().openapi()
    ids = [
        operation["operationId"]
        for methods in spec["paths"].values()
        for operation in methods.values()
    ]

    assert [name for name, count in Counter(ids).items() if count > 1] == []
    assert spec["paths"]["/api/v1/queues"]["get"]["operationId"] == (
        "list_queues_endpoint"
    )
