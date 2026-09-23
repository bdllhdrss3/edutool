def test_recovery_code_resets_password_and_remains_reusable(api):
    registration = api.client.post("/api/v1/auth/register", json={
        "username": "learner", "password": "original-password"})
    assert registration.status_code == 201
    recovery_code = registration.json()["recovery_code"]
    assert len(recovery_code) >= 12
    api.client.post("/api/v1/auth/logout")

    reset = api.client.post("/api/v1/auth/reset-password", json={
        "username": "learner", "recovery_code": recovery_code, "new_password": "updated-password"})
    assert reset.status_code == 204
    assert api.client.post("/api/v1/auth/login", json={
        "username": "learner", "password": "original-password"}).status_code == 401
    assert api.client.post("/api/v1/auth/login", json={
        "username": "learner", "password": "updated-password"}).status_code == 200
    assert api.client.post("/api/v1/auth/reset-password", json={
        "username": "learner", "recovery_code": recovery_code, "new_password": "third-password"}).status_code == 204


def test_existing_authenticated_user_can_enroll_in_recovery(api):
    assert api.client.get("/api/v1/auth/me").json()["has_recovery_code"] is False

    enrollment = api.client.post("/api/v1/auth/recovery-code")

    assert enrollment.status_code == 200
    assert len(enrollment.json()["recovery_code"]) >= 12
    assert api.client.get("/api/v1/auth/me").json()["has_recovery_code"] is True