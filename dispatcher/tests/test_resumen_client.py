import respx

from dispatcher.resumen_client import ResumenClient

B = "http://operador:8091"


@respx.mock
def test_status_and_request():
    respx.get(f"{B}/resumen").respond(json={"status": "idle"})
    post = respx.post(f"{B}/resumen").mock(side_effect=[respx.MockResponse(202), respx.MockResponse(409)])
    c = ResumenClient(B, "tok")
    assert c.status() == {"status": "idle"}
    assert c.request({"a": 1}) is True and c.request({"a": 1}) is False
    assert post.calls[0].request.headers["authorization"] == "Bearer tok"
