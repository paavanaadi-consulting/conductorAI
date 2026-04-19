import requests
import json
from pprint import pprint

BASE_URL = "http://localhost:8000/api"


def test_create_project():
    """Create a new project."""
    payload = {
        "name": "AI Code Generator",
        "github_repo": "octocat/Hello-World",
        "requirements_yaml": "D:\\Learning\\ConductorAI\\Documents\\requirement.yaml",
        "infra_yaml": "D:\\Learning\\ConductorAI\\Documents\\infra.yaml",
        "selected_components": ["code", "unit_test", "deployment", "monitoring"]
    }
    resp = requests.post(f"{BASE_URL}/projects", json=payload)
    print(f"✅ Create Project: {resp.status_code}")
    project = resp.json()
    pprint(project)
    return project["id"]


def test_list_projects():
    """List all projects."""
    resp = requests.get(f"{BASE_URL}/projects")
    print(f"\n✅ List Projects: {resp.status_code}")
    projects = resp.json()
    print(f"Found {len(projects)} projects")
    for p in projects:
        print(f"  - {p['name']} ({p['id']})")
    return projects


def test_get_project(project_id):
    """Get specific project."""
    resp = requests.get(f"{BASE_URL}/projects/{project_id}")
    print(f"\n✅ Get Project: {resp.status_code}")
    pprint(resp.json())


def test_update_project(project_id):
    """Update project."""
    payload = {
        "name": "Updated AI Code Generator",
        "selected_components": ["code", "unit_test"]
    }
    resp = requests.put(f"{BASE_URL}/projects/{project_id}", json=payload)
    print(f"\n✅ Update Project: {resp.status_code}")
    pprint(resp.json())


def test_run_project(project_id):
    """Run workflow for project."""
    payload = {
        "selected_components": ["code", "unit_test"],
        "pipeline_type": "auto"
    }
    resp = requests.post(f"{BASE_URL}/projects/{project_id}/run", json=payload)
    print(f"\n✅ Run Project: {resp.status_code}")
    pprint(resp.json())
    return resp.json()["id"]


def test_get_workflow_run(run_id):
    """Get workflow run status."""
    resp = requests.get(f"{BASE_URL}/workflows/{run_id}")
    print(f"\n✅ Get Workflow Run: {resp.status_code}")
    pprint(resp.json())


if __name__ == "__main__":
    # Test the full flow
    print("=" * 60)
    print("TESTING PROJECTS API")
    print("=" * 60)

    # Create
    project_id = test_create_project()

    # List
    test_list_projects()

    # Get
    test_get_project(project_id)

    # Update
    test_update_project(project_id)

    # Run
    run_response = test_run_project(project_id)
    run_id = run_response.get("id")

    if run_id:
        # Check workflow status
        test_get_workflow_run(run_id)

    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED")
    print("=" * 60)