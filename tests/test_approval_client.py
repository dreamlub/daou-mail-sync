from daou_approval.client import DaouApprovalClient


def test_referer_identifies_the_tenant_to_the_portal_api():
    client = DaouApprovalClient("waldlust.daouoffice.com")

    assert client.session.headers["Referer"] == "https://waldlust.daouoffice.com/"
    assert client.session.headers["X-Referer-Info"] == "https://waldlust.daouoffice.com"


def test_tenant_may_be_given_with_a_scheme_or_a_trailing_slash():
    for tenant in ("waldlust.daouoffice.com", "https://waldlust.daouoffice.com/"):
        assert DaouApprovalClient(tenant).base_url == "https://waldlust.daouoffice.com"
