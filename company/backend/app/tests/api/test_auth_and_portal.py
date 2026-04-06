from __future__ import annotations


def test_login_with_tenant_and_email_success(client) -> None:
    response = client.post(
        "/auth/login",
        json={
            "tenantId": "demo",
            "email": "admin@mvp.local",
            "password": "Admin123!",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert "accessToken" in body
    assert body["tenantId"] == "demo"
    assert body["user"]["email"] == "admin@mvp.local"
    assert body["user"]["role"] == "tenant_admin"


def test_login_invalid_password_returns_401(client) -> None:
    response = client.post(
        "/auth/login",
        json={
            "tenantId": "demo",
            "email": "admin@mvp.local",
            "password": "WrongPassword",
        },
    )

    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Invalid credentials."
    assert body["reasonCode"] == "INVALID_CREDENTIALS"


def test_login_inactive_user_returns_403(client) -> None:
    response = client.post(
        "/auth/login",
        json={
            "tenantId": "demo",
            "email": "inactive@mvp.local",
            "password": "Admin123!",
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["reasonCode"] == "INACTIVE_USER"


def test_portal_me_requires_token(client) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 401
    body = response.json()
    assert body["reasonCode"] == "MISSING_TOKEN"


def test_portal_me_success_for_tenant_admin(client, tenant_admin_token) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenantId"] == "demo"
    assert body["role"] == "tenant_admin"


def test_tenant_admin_cannot_cross_tenant_scope(client, tenant_admin_token) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "Authorization": f"Bearer {tenant_admin_token}",
            "X-Tenant-Id": "platform",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["reasonCode"] == "TENANT_SCOPE_VIOLATION"


def test_company_admin_can_use_different_request_tenant(client, company_admin_token) -> None:
    response = client.get(
        "/portal/me",
        headers={
            "Authorization": f"Bearer {company_admin_token}",
            "X-Tenant-Id": "demo",
            "X-Session-Id": "portal-session-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenantId"] == "platform"
    assert body["role"] == "company_admin"