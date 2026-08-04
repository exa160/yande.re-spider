"""proxy_enable 三态 (False=关闭 / True=自定义 / None=系统代理) 行为测试。

覆盖：
1. ApiConfig 默认 proxy_enable = None（系统代理）
2. 旧 YAML proxy_enable=true/false 仍按字面值加载
3. 缺失 proxy_enable 时解析为 None
4. configure_proxy_session 在三态下的 trust_env 与 proxies
5. OFF 模式 + 环境有 HTTP_PROXY：实际请求不会用环境代理（修复"关闭代理实际未关"的隐藏 bug）
6. SYSTEM 模式：实际请求会使用环境代理
"""
from unittest.mock import patch

import requests

from src.common.constant import ProxyMode
from src.common.settings import ApiConfig
from src.common.utils import configure_proxy_session


# ---------- ProxyMode 常量定义 ----------

def test_proxy_mode_constants_match_storage_values():
    """ProxyMode 常量与 ApiConfig.proxy_enable 的存储值一一对应"""
    assert ProxyMode.OFF is False
    assert ProxyMode.CUSTOM is True
    assert ProxyMode.SYSTEM is None


# ---------- ApiConfig proxy_enable 加载语义 ----------

def test_default_proxy_enable_is_none():
    cfg = ApiConfig()
    assert cfg.proxy_enable is None


def test_old_proxy_enable_true_loads_as_true():
    cfg = ApiConfig.model_validate({"proxy_enable": True})
    assert cfg.proxy_enable is True


def test_old_proxy_enable_false_loads_as_false():
    cfg = ApiConfig.model_validate({"proxy_enable": False})
    assert cfg.proxy_enable is False


def test_missing_proxy_enable_loads_as_none():
    cfg = ApiConfig.model_validate({})
    assert cfg.proxy_enable is None


def test_explicit_null_loads_as_none():
    cfg = ApiConfig.model_validate({"proxy_enable": None})
    assert cfg.proxy_enable is None


# ---------- configure_proxy_session 三态行为 ----------

def test_off_mode_disables_trust_env_and_clears_proxies(monkeypatch):
    """OFF(False): trust_env=False，proxies 清空，环境代理不应生效"""
    monkeypatch.setenv("HTTP_PROXY", "http://env-proxy:9999")
    with patch("src.common.utils.config") as mock_cfg:
        mock_cfg.yande_api.proxy_enable = False
        mock_cfg.yande_api.proxies = ApiConfig.ProxiesConfig()
        session = configure_proxy_session(requests.Session())

    assert session.trust_env is False
    assert dict(session.proxies) == {}


def test_custom_mode_uses_user_proxies_and_disables_trust_env(monkeypatch):
    """CUSTOM(True): trust_env=False，使用 proxies.http/https"""
    monkeypatch.setenv("HTTP_PROXY", "http://env-proxy:9999")
    with patch("src.common.utils.config") as mock_cfg:
        mock_cfg.yande_api.proxy_enable = True
        mock_cfg.yande_api.proxies = ApiConfig.ProxiesConfig(
            http="http://my-proxy:1234",
            https="http://my-proxy:1234",
        )
        session = configure_proxy_session(requests.Session())

    assert session.trust_env is False
    assert session.proxies["http"] == "http://my-proxy:1234"
    assert session.proxies["https"] == "http://my-proxy:1234"


def test_system_mode_enables_trust_env_and_clears_explicit_proxies(monkeypatch):
    """SYSTEM(None): trust_env=True，proxies 清空，让 requests 从环境读"""
    with patch("src.common.utils.config") as mock_cfg:
        mock_cfg.yande_api.proxy_enable = None
        mock_cfg.yande_api.proxies = ApiConfig.ProxiesConfig(
            http="http://my-proxy:1234",
            https="http://my-proxy:1234",
        )
        session = configure_proxy_session(requests.Session())

    assert session.trust_env is True
    assert dict(session.proxies) == {}


# ---------- 集成验证：resolve_proxies 实际生效 ----------

def test_off_mode_does_not_use_env_proxy(monkeypatch):
    """OFF 模式 + 环境有 HTTP_PROXY：实际请求不会用环境代理"""
    from requests.utils import resolve_proxies

    monkeypatch.setenv("HTTP_PROXY", "http://env-proxy:9999")
    with patch("src.common.utils.config") as mock_cfg:
        mock_cfg.yande_api.proxy_enable = False
        mock_cfg.yande_api.proxies = ApiConfig.ProxiesConfig()
        session = configure_proxy_session(requests.Session())

    req = requests.Request("GET", "https://yande.re/post.json").prepare()
    resolved = resolve_proxies(req, session.proxies, session.trust_env)
    assert resolved == {}, f"OFF 模式不应使用环境代理，实际: {resolved}"


def test_system_mode_does_use_env_proxy(monkeypatch):
    """SYSTEM 模式：实际请求会使用环境代理"""
    from requests.utils import resolve_proxies

    monkeypatch.setenv("HTTPS_PROXY", "http://env-proxy:9999")
    with patch("src.common.utils.config") as mock_cfg:
        mock_cfg.yande_api.proxy_enable = None
        mock_cfg.yande_api.proxies = ApiConfig.ProxiesConfig()
        session = configure_proxy_session(requests.Session())

    req = requests.Request("GET", "https://yande.re/post.json").prepare()
    resolved = resolve_proxies(req, session.proxies, session.trust_env)
    assert resolved.get("https") == "http://env-proxy:9999", f"SYSTEM 模式应使用环境代理，实际: {resolved}"