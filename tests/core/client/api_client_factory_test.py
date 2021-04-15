import re
from unittest.mock import patch

import pytest

from symphony.bdk.core.client.api_client_factory import ApiClientFactory
from symphony.bdk.core.config.model.bdk_config import BdkConfig
from symphony.bdk.core.config.model.bdk_server_config import BdkProxyConfig
from symphony.bdk.core.config.model.bdk_ssl_config import BdkSslConfig
from tests.utils.resource_utils import get_resource_filepath

HOST = "acme.symphony.com"


@pytest.fixture(name="config")
def fixture_config():
    return BdkConfig(host=HOST)


@pytest.fixture(name="add_x_trace_id")
def fixture_add_x_trace_id():
    def mock_add_x_trace_id(func):
        return func

    return mock_add_x_trace_id


@pytest.mark.asyncio
async def test_host_configured(config):
    client_factory = ApiClientFactory(config)

    assert_host_configured_only(client_factory.get_pod_client(), "/pod")
    assert_host_configured_only(client_factory.get_login_client(), "/login")
    assert_host_configured_only(client_factory.get_agent_client(), "/agent")
    assert_host_configured_only(client_factory.get_app_session_auth_client(), "/sessionauth")
    assert_host_configured_only(client_factory.get_relay_client(), "/relay")


@pytest.mark.asyncio
async def test_client_cert_configured(config):
    client_cert_path = get_resource_filepath("cert/megabot.pem", as_text=True)

    config.app.certificate.path = client_cert_path
    client_factory = ApiClientFactory(config)
    session_auth_client = client_factory.get_app_session_auth_client()

    assert session_auth_client.configuration.cert_file == client_cert_path


@pytest.mark.asyncio
async def test_client_cert_not_configured(config):
    client_factory = ApiClientFactory(config)
    session_auth_client = client_factory.get_app_session_auth_client()

    assert session_auth_client.configuration.cert_file is None


@pytest.mark.asyncio
async def test_proxy_configured(config):
    proxy_host = "proxy.com"
    proxy_port = 1234
    config.proxy = BdkProxyConfig(proxy_host, proxy_port)
    client_factory = ApiClientFactory(config)

    assert_host_and_proxy_configured(client_factory.get_pod_client(), "/pod", proxy_host, proxy_port)
    assert_host_and_proxy_configured(client_factory.get_login_client(), "/login", proxy_host, proxy_port)
    assert_host_and_proxy_configured(client_factory.get_agent_client(), "/agent", proxy_host, proxy_port)
    assert_host_and_proxy_configured(client_factory.get_app_session_auth_client(), "/sessionauth", proxy_host,
                                     proxy_port)
    assert_host_and_proxy_configured(client_factory.get_relay_client(), "/relay", proxy_host, proxy_port)


@pytest.mark.asyncio
async def test_proxy_credentials_configured(config):
    proxy_host = "proxy.com"
    proxy_port = 1234
    config.proxy = BdkProxyConfig(proxy_host, proxy_port, "user", "pass")
    client_factory = ApiClientFactory(config)

    assert_host_and_proxy_credentials_configured(client_factory.get_pod_client(), "/pod", proxy_host, proxy_port)
    assert_host_and_proxy_credentials_configured(client_factory.get_login_client(), "/login", proxy_host, proxy_port)
    assert_host_and_proxy_credentials_configured(client_factory.get_agent_client(), "/agent", proxy_host, proxy_port)
    assert_host_and_proxy_credentials_configured(client_factory.get_app_session_auth_client(), "/sessionauth", proxy_host,
                                                 proxy_port)
    assert_host_and_proxy_credentials_configured(client_factory.get_relay_client(), "/relay", proxy_host, proxy_port)


@pytest.mark.asyncio
async def test_global_user_agent_configured(config):
    custom_user_agent = "custom-user-agent"

    config.default_headers = {"user-agent": custom_user_agent}
    client_factory = ApiClientFactory(config)

    assert client_factory.get_pod_client().user_agent == custom_user_agent
    assert client_factory.get_login_client().user_agent == custom_user_agent
    assert client_factory.get_agent_client().user_agent == custom_user_agent
    assert client_factory.get_app_session_auth_client().user_agent == custom_user_agent
    assert client_factory.get_relay_client().user_agent == custom_user_agent


@pytest.mark.asyncio
async def test_user_agent_configured_at_pod_level(config):
    custom_user_agent = "custom-user-agent"

    config.pod._default_headers = {"user-agent": custom_user_agent}
    client_factory = ApiClientFactory(config)

    assert client_factory.get_pod_client().user_agent == custom_user_agent
    assert client_factory.get_login_client().user_agent == custom_user_agent
    assert_default_user_agent_configured(client_factory.get_agent_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_app_session_auth_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_relay_client().user_agent)


@pytest.mark.asyncio
async def test_user_agent_configured_at_agent_level(config):
    custom_user_agent = "custom-user-agent"

    config.agent._default_headers = {"user-agent": custom_user_agent}
    client_factory = ApiClientFactory(config)

    assert_default_user_agent_configured(client_factory.get_pod_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_login_client().user_agent)
    assert client_factory.get_agent_client().user_agent == custom_user_agent
    assert_default_user_agent_configured(client_factory.get_app_session_auth_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_relay_client().user_agent)


@pytest.mark.asyncio
async def test_user_agent_configured_at_session_auth_level(config):
    custom_user_agent = "custom-user-agent"

    config.session_auth._default_headers = {"user-agent": custom_user_agent}
    client_factory = ApiClientFactory(config)

    assert_default_user_agent_configured(client_factory.get_pod_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_login_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_agent_client().user_agent)
    assert client_factory.get_app_session_auth_client().user_agent == custom_user_agent
    assert_default_user_agent_configured(client_factory.get_relay_client().user_agent)


@pytest.mark.asyncio
async def test_user_agent_configured_at_km_level(config):
    custom_user_agent = "custom-user-agent"

    config.key_manager._default_headers = {"user-agent": custom_user_agent}
    client_factory = ApiClientFactory(config)

    assert_default_user_agent_configured(client_factory.get_pod_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_login_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_agent_client().user_agent)
    assert_default_user_agent_configured(client_factory.get_app_session_auth_client().user_agent)
    assert client_factory.get_relay_client().user_agent == custom_user_agent


@pytest.mark.asyncio
async def test_global_default_headers(config):
    config.default_headers = {"header_name": "header_value"}
    client_factory = ApiClientFactory(config)

    assert_default_headers(client_factory.get_pod_client().default_headers, config.default_headers)
    assert_default_headers(client_factory.get_login_client().default_headers, config.default_headers)
    assert_default_headers(client_factory.get_agent_client().default_headers, config.default_headers)
    assert_default_headers(client_factory.get_app_session_auth_client().default_headers, config.default_headers)
    assert_default_headers(client_factory.get_relay_client().default_headers, config.default_headers)


@pytest.mark.asyncio
async def test_default_headers_at_pod_level(config):
    default_headers = {"header_name": "header_value"}

    config.pod._default_headers = default_headers
    client_factory = ApiClientFactory(config)

    assert_default_headers(client_factory.get_pod_client().default_headers, default_headers)
    assert_default_headers(client_factory.get_login_client().default_headers, default_headers)
    assert_default_headers(client_factory.get_agent_client().default_headers, {})
    assert_default_headers(client_factory.get_app_session_auth_client().default_headers, {})
    assert_default_headers(client_factory.get_relay_client().default_headers, {})


@pytest.mark.asyncio
async def test_default_headers_at_agent_level(config):
    default_headers = {"header_name": "header_value"}

    config.agent._default_headers = default_headers
    client_factory = ApiClientFactory(config)

    assert_default_headers(client_factory.get_pod_client().default_headers, {})
    assert_default_headers(client_factory.get_login_client().default_headers, {})
    assert_default_headers(client_factory.get_agent_client().default_headers, default_headers)
    assert_default_headers(client_factory.get_app_session_auth_client().default_headers, {})
    assert_default_headers(client_factory.get_relay_client().default_headers, {})


@pytest.mark.asyncio
async def test_default_headers_at_session_auth_level(config):
    default_headers = {"header_name": "header_value"}

    config.session_auth._default_headers = default_headers
    client_factory = ApiClientFactory(config)

    assert_default_headers(client_factory.get_pod_client().default_headers, {})
    assert_default_headers(client_factory.get_login_client().default_headers, {})
    assert_default_headers(client_factory.get_agent_client().default_headers, {})
    assert_default_headers(client_factory.get_app_session_auth_client().default_headers, default_headers)
    assert_default_headers(client_factory.get_relay_client().default_headers, {})


@pytest.mark.asyncio
async def test_default_headers_at_km_level(config):
    default_headers = {"header_name": "header_value"}

    config.key_manager._default_headers = default_headers
    client_factory = ApiClientFactory(config)

    assert_default_headers(client_factory.get_pod_client().default_headers, {})
    assert_default_headers(client_factory.get_login_client().default_headers, {})
    assert_default_headers(client_factory.get_agent_client().default_headers, {})
    assert_default_headers(client_factory.get_app_session_auth_client().default_headers, {})
    assert_default_headers(client_factory.get_relay_client().default_headers, default_headers)


@pytest.mark.asyncio
async def test_x_trace_id_not_in_default_headers(config, add_x_trace_id):
    with patch("symphony.bdk.core.client.api_client_factory.add_x_trace_id", return_value=add_x_trace_id) as mock:
        client_factory = ApiClientFactory(config)

        assert mock.call_count == 5
        assert_default_headers(client_factory.get_pod_client().default_headers, {})
        assert_default_headers(client_factory.get_login_client().default_headers, {})
        assert_default_headers(client_factory.get_agent_client().default_headers, {})
        assert_default_headers(client_factory.get_app_session_auth_client().default_headers, {})
        assert_default_headers(client_factory.get_relay_client().default_headers, {})


@pytest.mark.asyncio
async def test_x_trace_id_not_in_default_headers(config, add_x_trace_id):
    default_headers = {"x-trace-id": "trace-id"}

    config.default_headers = default_headers
    with patch("symphony.bdk.core.client.api_client_factory.add_x_trace_id", return_value=add_x_trace_id) as mock:
        client_factory = ApiClientFactory(config)

        mock.assert_not_called()
        assert_default_headers(client_factory.get_pod_client().default_headers, default_headers)
        assert_default_headers(client_factory.get_login_client().default_headers, default_headers)
        assert_default_headers(client_factory.get_agent_client().default_headers, default_headers)
        assert_default_headers(client_factory.get_app_session_auth_client().default_headers, default_headers)
        assert_default_headers(client_factory.get_relay_client().default_headers, default_headers)


def assert_default_headers(actual, expected):
    actual.pop("User-Agent")  # remove the User-Agent put by default
    assert actual == expected


def test_trust_store_configured(config):
    with patch("symphony.bdk.gen.rest.RESTClientObject"):
        truststore_path = "/path/to/truststore.pem"
        config.ssl = BdkSslConfig({"trustStore": {"path": truststore_path}})

        client_factory = ApiClientFactory(config)

        assert client_factory.get_pod_client().configuration.ssl_ca_cert == truststore_path


def assert_host_configured_only(client, url_suffix):
    configuration = client.configuration

    assert configuration.host == f"https://{HOST}:443{url_suffix}"
    assert_default_user_agent_configured(client.user_agent)
    assert configuration.proxy is None
    assert configuration.proxy_headers is None


def assert_host_and_proxy_configured(client, url_suffix, proxy_host, proxy_port):
    configuration = client.configuration

    assert configuration.host == f"https://{HOST}:443{url_suffix}"
    assert configuration.proxy == f"http://{proxy_host}:{proxy_port}"
    assert_default_user_agent_configured(client.user_agent)

    assert "proxy-authorization" not in configuration.proxy_headers
    assert "user-agent" in configuration.proxy_headers
    assert_default_user_agent_configured(configuration.proxy_headers["user-agent"])


def assert_host_and_proxy_credentials_configured(client, url_suffix, proxy_host, proxy_port):
    configuration = client.configuration

    assert configuration.host == f"https://{HOST}:443{url_suffix}"
    assert configuration.proxy == f"http://{proxy_host}:{proxy_port}"
    assert_default_user_agent_configured(client.user_agent)

    assert "proxy-authorization" in configuration.proxy_headers
    assert "user-agent" in configuration.proxy_headers
    assert_default_user_agent_configured(configuration.proxy_headers["user-agent"])


def assert_default_user_agent_configured(user_agent):
    assert re.match(r"^Symphony-BDK-Python/\S+ Python/3\.\S+$", user_agent) is not None
