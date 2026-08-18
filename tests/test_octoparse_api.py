from scripts.fetch_octoparse_exports import fetch_batch, wait_for_completed


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(next(self.responses))


def test_wait_for_completed_returns_latest_lot():
    session = FakeSession(
        [{"data": {"status": "completed", "lotNo": "123", "collectedRows": 2}}]
    )

    status = wait_for_completed(session, "task-1", {"x-api-key": "secret"}, 0, 1)

    assert status["lotNo"] == "123"
    assert status["collectedRows"] == 2


def test_fetch_batch_paginates_until_total():
    session = FakeSession(
        [
            {
                "data": {
                    "offset": 172257,
                    "total": 3,
                    "restTotal": 1,
                    "data": [{"id": 1}, {"id": 2}],
                }
            },
            {
                "data": {
                    "offset": 172258,
                    "total": 3,
                    "restTotal": 0,
                    "data": [{"id": 3}],
                }
            },
        ]
    )

    rows = fetch_batch(session, "task-1", "lot-1", {"x-api-key": "secret"}, 2)

    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert session.calls[0][1]["params"]["offset"] == 0
    assert session.calls[1][1]["params"]["offset"] == 172257
