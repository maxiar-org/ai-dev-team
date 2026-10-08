import respx

from dispatcher.coolify import CoolifyClient

B = "http://coolify:8080/api/v1"


@respx.mock
def test_apps_with_last_deploy_and_previews():
    respx.get(f"{B}/applications").respond(json=[
        {"uuid": "u1", "name": "qr-generator", "git_repository": "maxiar-org/qr-generator", "fqdn": "http://qr.maxiar.dev",
         "status": "running:healthy", "preview_url_template": "qr-pr-{{pr_id}}.maxiar.dev"},
        {"uuid": "u2", "name": "preview-lab", "git_repository": "maxiar-org/preview-lab", "fqdn": None,
         "docker_compose_domains": '{"app":{"domain":"http://preview-lab.maxiar.dev"}}', "status": "running:unknown",
         "preview_url_template": None},
    ])
    respx.get(f"{B}/deployments/applications/u1").respond(json={"deployments": [
        {"pull_request_id": 23, "status": "finished", "created_at": "2026-10-08T05:00:00Z"},
        {"pull_request_id": 0, "status": "finished", "created_at": "2026-10-08T04:57:00Z"},
    ]})
    respx.get(f"{B}/deployments/applications/u2").respond(json={"deployments": []})
    apps = {a.name: a for a in CoolifyClient("http://coolify:8080/api/v1", "t").apps()}
    qr = apps["qr-generator"]
    assert (qr.repo, qr.url, qr.status) == ("maxiar-org/qr-generator", "https://qr.maxiar.dev", "running:healthy")
    assert (qr.last_deploy, qr.last_deploy_status, qr.preview_prs) == ("2026-10-08T04:57:00Z", "finished", (23,))
    assert apps["preview-lab"].url == "https://preview-lab.maxiar.dev"
