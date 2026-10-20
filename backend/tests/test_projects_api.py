"""Tests for project CRUD endpoints."""

from fastapi.testclient import TestClient


def test_create_and_get_project(client: TestClient) -> None:
    """Verify creating a project and retrieving it."""
    # Create project
    create_res = client.post("/api/projects", json={"name": "Arabic Tech Podcast"})
    assert create_res.status_code == 201
    project = create_res.json()
    assert project["name"] == "Arabic Tech Podcast"
    assert project["id"].startswith("proj_")
    assert project["media_count"] == 0
    assert project["media_assets"] == []

    # Get project
    get_res = client.get(f"/api/projects/{project['id']}")
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["id"] == project["id"]
    assert fetched["name"] == "Arabic Tech Podcast"


def test_create_project_validation(client: TestClient) -> None:
    """Verify rejection of empty or invalid project names."""
    # Empty string
    res1 = client.post("/api/projects", json={"name": ""})
    assert res1.status_code == 422

    # Whitespace only
    res2 = client.post("/api/projects", json={"name": "   "})
    assert res2.status_code == 422


def test_list_projects(client: TestClient) -> None:
    """Verify listing projects."""
    p1 = client.post("/api/projects", json={"name": "Project Alpha"}).json()
    p2 = client.post("/api/projects", json={"name": "Project Beta"}).json()

    list_res = client.get("/api/projects")
    assert list_res.status_code == 200
    items = list_res.json()
    ids = [item["id"] for item in items]
    assert p1["id"] in ids
    assert p2["id"] in ids


def test_get_nonexistent_project(client: TestClient) -> None:
    """Verify 404 for nonexistent project."""
    res = client.get("/api/projects/proj_nonexistent_xyz")
    assert res.status_code == 404


def test_delete_project(client: TestClient) -> None:
    """Verify deleting a project removes database records."""
    project = client.post("/api/projects", json={"name": "To Delete"}).json()
    pid = project["id"]

    del_res = client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 204

    # Verify subsequent GET returns 404
    get_res = client.get(f"/api/projects/{pid}")
    assert get_res.status_code == 404


def test_delete_nonexistent_project(client: TestClient) -> None:
    """Verify deleting nonexistent project returns 404."""
    res = client.delete("/api/projects/proj_ghost_xyz")
    assert res.status_code == 404


def test_update_project(client: TestClient) -> None:
    """Verify updating a project's name."""
    project = client.post("/api/projects", json={"name": "Initial Name"}).json()
    pid = project["id"]

    patch_res = client.patch(f"/api/projects/{pid}", json={"name": "Updated Name"})
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["id"] == pid
    assert updated["name"] == "Updated Name"

    # Verify through GET
    get_res = client.get(f"/api/projects/{pid}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Updated Name"


def test_update_project_validation(client: TestClient) -> None:
    """Verify rejecting empty names on update."""
    project = client.post("/api/projects", json={"name": "Valid Name"}).json()
    pid = project["id"]

    res_empty = client.patch(f"/api/projects/{pid}", json={"name": ""})
    assert res_empty.status_code == 422

    res_spaces = client.patch(f"/api/projects/{pid}", json={"name": "   "})
    assert res_spaces.status_code == 422


def test_update_nonexistent_project(client: TestClient) -> None:
    """Verify 404 for updating a nonexistent project."""
    res = client.patch("/api/projects/proj_ghost_xyz", json={"name": "Does Not Matter"})
    assert res.status_code == 404


def test_duplicate_project(client: TestClient) -> None:
    """Verify duplicating an existing project."""
    original = client.post("/api/projects", json={"name": "Original Series"}).json()
    orig_id = original["id"]

    dup_res = client.post(f"/api/projects/{orig_id}/duplicate")
    assert dup_res.status_code == 201
    duplicate = dup_res.json()
    assert duplicate["id"] != orig_id
    assert duplicate["name"] == "Original Series (Copy)"
    assert duplicate["media_count"] == 0


def test_duplicate_nonexistent_project(client: TestClient) -> None:
    """Verify 404 for duplicating a nonexistent project."""
    res = client.post("/api/projects/proj_ghost_xyz/duplicate")
    assert res.status_code == 404
