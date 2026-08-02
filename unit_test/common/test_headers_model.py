from src.common.settings import ApiConfig


def _extra(cfg):
    """读取 Pydantic 收集的额外字段(extra='allow' 时存在 __pydantic_extra__)。"""
    return getattr(cfg, "__pydantic_extra__", None) or {}


def test_serialize_three_fixed_fields_use_kebab_alias():
    cfg = ApiConfig.Headers(
        user_agent="UA-test",
        accept="text/html",
        accept_language="zh-CN",
    )
    out = cfg.model_dump(by_alias=True)
    assert out["User-agent"] == "UA-test"
    assert out["Accept"] == "text/html"
    assert out["Accept-Language"] == "zh-CN"
    assert "user_agent" not in out
    assert "accept" not in out
    assert "accept_language" not in out


def test_extra_headers_flattened_to_top_level_on_serialize():
    cfg = ApiConfig.Headers.model_validate({
        "User-agent": "UA",
        "Authorization": "Bearer xxx",
        "X-Custom": "foo",
    })
    out = cfg.model_dump(by_alias=True)
    assert "Authorization" in out
    assert "X-Custom" in out
    assert out["Authorization"] == "Bearer xxx"
    assert out["X-Custom"] == "foo"
    assert _extra(cfg) == {"Authorization": "Bearer xxx", "X-Custom": "foo"}


def test_deserialize_kebab_alias_recognized_as_fixed_field():
    cfg = ApiConfig.Headers.model_validate({
        "User-agent": "UA-from-kebab",
        "Accept": "text/html",
        "Accept-Language": "en-US",
    })
    assert cfg.user_agent == "UA-from-kebab"
    assert cfg.accept == "text/html"
    assert cfg.accept_language == "en-US"


def test_deserialize_snake_name_recognized_as_fixed_field():
    cfg = ApiConfig.Headers.model_validate({
        "user_agent": "UA-from-snake",
        "accept": "text/html",
        "accept_language": "en-US",
    })
    assert cfg.user_agent == "UA-from-snake"
    assert cfg.accept == "text/html"
    assert cfg.accept_language == "en-US"


def test_unknown_keys_go_to_pydantic_extra():
    cfg = ApiConfig.Headers.model_validate({
        "User-agent": "UA",
        "Authorization": "Bearer xxx",
        "X-Trace-Id": "abc-123",
    })
    assert cfg.user_agent == "UA"
    assert _extra(cfg) == {
        "Authorization": "Bearer xxx",
        "X-Trace-Id": "abc-123",
    }


def test_serialize_empty_headers_yields_only_fixed_fields():
    cfg = ApiConfig.Headers()
    out = cfg.model_dump(by_alias=True)
    assert "User-agent" in out
    assert "Accept" in out
    assert "Accept-Language" in out
    assert _extra(cfg) == {}


def test_round_trip_preserves_data():
    original = ApiConfig.Headers.model_validate({
        "User-agent": "UA",
        "Accept": "*/*",
        "Accept-Language": "zh-CN",
        "Authorization": "Bearer xxx",
        "X-Custom": "foo",
    })
    dumped = original.model_dump(by_alias=True)
    reloaded = ApiConfig.Headers.model_validate(dumped)
    assert reloaded.user_agent == "UA"
    assert reloaded.accept == "*/*"
    assert reloaded.accept_language == "zh-CN"
    assert _extra(reloaded) == {
        "Authorization": "Bearer xxx",
        "X-Custom": "foo",
    }