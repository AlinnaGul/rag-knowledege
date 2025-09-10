from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_endpoints():
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/metrics').status_code == 200
    assert client.get('/api/ready').status_code in (200, 503)


def test_auth_me_requires_auth():
    # Endpoint exists and requires authentication
    resp = client.get('/api/auth/me')
    assert resp.status_code == 401
