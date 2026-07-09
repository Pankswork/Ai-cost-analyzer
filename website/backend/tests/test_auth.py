import pytest


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_token(client):
    resp = await client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "password123",
        "name": "New User",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client):
    await client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "password": "password123",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "password": "password123",
    })
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client):
    resp = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_token(client):
    await client.post("/api/auth/register", json={
        "email": "login@example.com",
        "password": "password123",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "login@example.com",
        "password": "password123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_invalid_password_returns_401(client):
    await client.post("/api/auth/register", json={
        "email": "badpwd@example.com",
        "password": "password123",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "badpwd@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_401(client):
    resp = await client.post("/api/auth/login", json={
        "email": "nobody@example.com",
        "password": "password123",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_with_valid_token(client, auth_token):
    resp = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {auth_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["name"] == "Test User"
    assert "id" in data


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client):
    resp = await client.get("/api/auth/me", headers={
        "Authorization": "Bearer invalid-token",
    })
    assert resp.status_code == 401
