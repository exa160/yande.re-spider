# 请求头编辑功能 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在配置页增加 yande.re 请求头编辑功能(三个固定字段 + 自定义 header,平铺存储),不修改调用方代码。

**Architecture:** 后端 `ApiConfig.Headers` 模型增加 `extra_headers: dict[str,str]`,`model_serializer` 把 `extra_headers` 平铺到顶层;`model_validator(mode='before')` 把非固定字段归入 `extra_headers`;`update_api_config` 取消 `exclude={"headers"}`。前端新增 `HeadersEditorDialog.vue` 组件,`Config.vue` 增加"编辑请求头"按钮 + Dialog 集成。

**Tech Stack:** FastAPI + Pydantic v2 + pyyaml (Python 3.12) / Vue 3.4 + Element Plus 2.5 + Vitest 3.x / pytest 9.x

**前置阅读：**
- Spec：`docs/superpowers/specs/2026-07-28-headers-editor-design.md`
- 项目规范：`AGENTS.md`
- 全局规则：`~/.config/opencode/AGENTS.md`（中文回复 / **改代码后必须等用户确认才提交**,本次计划所有 Task 末尾均"暂不 commit"）

---

## Task 1: 后端 - 写 Headers 模型测试(TDD 第一步)

**Files:**
- Create: `unit_test/common/__init__.py`
- Create: `unit_test/common/test_headers_model.py`

- [ ] **Step 1: 创建测试目录**

```bash
mkdir -p unit_test/common
touch unit_test/common/__init__.py
```

- [ ] **Step 2: 写 Headers 模型单元测试**

创建 `unit_test/common/test_headers_model.py`:

```python
"""ApiConfig.Headers 模型行为测试。

覆盖：
1. 序列化 - 三个固定字段按烤串 alias 输出
2. 序列化 - extra_headers 平铺到顶层(无 extra_headers 键)
3. 反序列化 - 烤串命名(User-agent)归入 user_agent 字段
4. 反序列化 - 蛇形命名(user_agent)也能识别(populate_by_name)
5. 反序列化 - 任意非固定键归入 extra_headers
6. 序列化 - 空 Headers 实例正确序列化(空 dict)
7. 往返 - dump → load → dump 数据一致
"""
from src.common.settings import ApiConfig


def test_serialize_three_fixed_fields_use_kebab_alias():
    """三个固定字段序列化时使用烤串命名。"""
    cfg = ApiConfig.Headers(
        user_agent="UA-test",
        accept="text/html",
        accept_language="zh-CN",
    )
    out = cfg.model_dump(by_alias=True)
    assert out["User-agent"] == "UA-test"
    assert out["Accept"] == "text/html"
    assert out["Accept-Language"] == "zh-CN"
    # 蛇形命名不应出现
    assert "user_agent" not in out
    assert "accept" not in out
    assert "accept_language" not in out


def test_serialize_extra_headers_flattened_to_top_level():
    """extra_headers 序列化时平铺到顶层。"""
    cfg = ApiConfig.Headers(
        user_agent="UA",
        accept="text/html",
        accept_language="zh-CN",
        extra_headers={"Authorization": "Bearer xxx", "X-Custom": "foo"},
    )
    out = cfg.model_dump(by_alias=True)
    assert "extra_headers" not in out
    assert out["Authorization"] == "Bearer xxx"
    assert out["X-Custom"] == "foo"


def test_deserialize_kebab_alias_recognized_as_fixed_field():
    """烤串命名(如 User-agent)能识别为 user_agent 字段。"""
    cfg = ApiConfig.Headers.model_validate({
        "User-agent": "UA-from-kebab",
        "Accept": "text/html",
        "Accept-Language": "en-US",
    })
    assert cfg.user_agent == "UA-from-kebab"
    assert cfg.accept == "text/html"
    assert cfg.accept_language == "en-US"
    assert cfg.extra_headers == {}


def test_deserialize_snake_name_recognized_as_fixed_field():
    """蛇形命名(user_agent)也能识别(populate_by_name)。"""
    cfg = ApiConfig.Headers.model_validate({
        "user_agent": "UA-from-snake",
        "accept": "text/html",
        "accept_language": "en-US",
    })
    assert cfg.user_agent == "UA-from-snake"
    assert cfg.accept == "text/html"
    assert cfg.accept_language == "en-US"


def test_deserialize_unknown_keys_go_to_extra_headers():
    """非固定字段的任意键归入 extra_headers。"""
    cfg = ApiConfig.Headers.model_validate({
        "User-agent": "UA",
        "Authorization": "Bearer xxx",
        "X-Custom": "foo",
        "X-Trace-Id": "abc-123",
    })
    assert cfg.user_agent == "UA"
    assert cfg.extra_headers == {
        "Authorization": "Bearer xxx",
        "X-Custom": "foo",
        "X-Trace-Id": "abc-123",
    }


def test_serialize_empty_headers_yields_no_extra_headers_key():
    """默认 Headers 序列化后不应有 extra_headers 键。"""
    cfg = ApiConfig.Headers()
    out = cfg.model_dump(by_alias=True)
    # 关键: 平铺逻辑不应暴露 extra_headers 键
    assert 'extra_headers' not in out
    # 空字符串字段可能仍在(requests 接受),无需强求 {}


def test_round_trip_preserves_data():
    """dump → load → dump 数据一致。"""
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
    assert reloaded.extra_headers == {
        "Authorization": "Bearer xxx",
        "X-Custom": "foo",
    }
```

- [ ] **Step 3: 运行测试验证失败**

```bash
.venv/bin/python -m pytest unit_test/common/test_headers_model.py -v
```

预期:多数测试失败(因为 Headers 模型尚未重构)。`test_serialize_empty_headers_yields_empty_dict` 可能通过(因为当前模型没平铺逻辑)。

- [ ] **Step 4: 暂不 commit**

按用户指示不提交代码改动。本任务完成,继续 Task 2。

---

## Task 2: 后端 - 重构 Headers 模型

**Files:**
- Modify: `backend/src/common/settings.py:27-41`

- [ ] **Step 1: 修改 ApiConfig.Headers 子类**

打开 `backend/src/common/settings.py`,定位第 32-35 行(原 `Headers` 子类),替换为:

```python
class ApiConfig(ConfigModel):
    class ProxiesConfig(ConfigModel):
        http: str = ""
        https: str = ""

    class Headers(ConfigModel):
        model_config = ConfigDict(populate_by_name=True)

        # 三个固定字段:同时接受烤串(从 YAML)和蛇形(从 API 内部)
        user_agent: str = Field(
            '', alias='User-agent', serialization_alias='User-agent'
        )
        accept: str = Field(
            '', alias='Accept', serialization_alias='Accept'
        )
        accept_language: str = Field(
            '', alias='Accept-Language', serialization_alias='Accept-Language'
        )
        # 自定义 headers:序列化时平铺到顶层
        extra_headers: dict[str, str] = Field(default_factory=dict)

        @model_serializer(mode='wrap')
        def _ser(self, handler):
            """序列化:把 extra_headers 平铺到顶层"""
            d = handler(self)
            d.pop('extra_headers', None)
            d.update(self.extra_headers)
            return d

        @model_validator(mode='before')
        @classmethod
        def _flatten_extra(cls, data):
            """反序列化:非固定字段归入 extra_headers"""
            if not isinstance(data, dict):
                return data
            fixed_keys = {
                'User-agent', 'user-agent', 'user_agent',
                'Accept', 'accept',
                'Accept-Language', 'accept-language', 'accept_language',
            }
            extra = {k: v for k, v in data.items() if k not in fixed_keys}
            data = {k: v for k, v in data.items() if k in fixed_keys}
            data['extra_headers'] = extra
            return data

    proxy_enable: bool = Field(default=False)
    proxies: ProxiesConfig = ProxiesConfig()
    timeout: int = Field(default=30)
    retry: int = Field(3, description='yandere失败重试')
    headers: Optional[Headers] = Field(default_factory=Headers)
```

- [ ] **Step 2: 补充 imports**

打开 `backend/src/common/settings.py` 顶部 imports(第 1-9 行),增加 `model_serializer` 和 `model_validator`:

```python
from functools import wraps
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_serializer,
    model_serializer,
    model_validator,
)

from src.common.constant import path_constant
```

> 注:`BaseModel` 实际未使用,但保持原 imports 不破坏其他引用;若确认无引用可删除。

- [ ] **Step 3: 运行测试验证通过**

```bash
.venv/bin/python -m pytest unit_test/common/test_headers_model.py -v
```

预期:7 个测试全部 PASS。

- [ ] **Step 4: 验证 YAML 读写**

```bash
.venv/bin/python -c "
from src.common.settings import ApiConfig, save_config, load_config
from pathlib import Path
import tempfile, os

cfg = ApiConfig(headers={
    'User-agent': 'UA-test',
    'Accept': 'text/html',
    'Accept-Language': 'zh-CN',
    'Authorization': 'Bearer xxx',
    'X-Custom': 'foo',
})

# dump + save
tmp = Path(tempfile.mkdtemp()) / 'test.yaml'
save_config(cfg, tmp)
print('=== YAML 内容 ===')
print(tmp.read_text())

# load + reload
reloaded = load_config(tmp)
print('=== 加载后 ===')
print('user_agent:', reloaded.headers.user_agent)
print('extra:', reloaded.headers.extra_headers)
"
```

预期输出:
```
=== YAML 内容 ===
headers:
  User-agent: UA-test
  Accept: text/html
  Accept-Language: zh-CN
  Authorization: Bearer xxx
  X-Custom: foo
=== 加载后 ===
user_agent: UA-test
extra: {'Authorization': 'Bearer xxx', 'X-Custom': 'foo'}
```

注意:`save_config` 实际签名是 `save_config(_config: Config, config_path)` 而非 `save_config(ApiConfig, ...)`,本测试需直接调用 yaml.dump 验证平铺行为。改用:

```bash
.venv/bin/python -c "
from src.common.settings import ApiConfig
from pathlib import Path
import tempfile

cfg = ApiConfig(headers={
    'User-agent': 'UA-test',
    'Authorization': 'Bearer xxx',
})
print(cfg.headers.model_dump(by_alias=True, exclude_none=True))
"
```

预期:`{'User-agent': 'UA-test', 'Authorization': 'Bearer xxx'}`(平铺,无 `extra_headers` 键)

- [ ] **Step 5: 暂不 commit**

按用户指示不提交代码改动。本任务完成,继续 Task 3。

---

## Task 3: 后端 - 写 update_api_config 测试

**Files:**
- Create: `unit_test/services/test_config_update_headers.py`

- [ ] **Step 1: 写 update_api_config 集成测试**

创建 `unit_test/services/test_config_update_headers.py`:

```python
"""ConfigService.update_api_config 允许 headers 更新的测试。

覆盖:
1. 现有 config 加载后,调用 update_api_config 传入新 headers,config.yande_api.headers 被更新
2. 更新后的 headers 平铺到 YAML 持久化
3. 其他字段(retry / timeout / proxy_enable)保留不变
"""
import tempfile
from pathlib import Path

import pytest
import yaml

from src.common import config as global_config
from src.common.settings import (
    ApiConfig,
    Config,
    DatabaseConfig,
    DownloaderConfig,
    load_config,
    save_config,
)


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """用临时文件隔离全局 config,避免污染真实 config.yaml。"""
    test_file = tmp_path / "config.yaml"
    initial = Config(
        app=global_config.config.app.model_dump(),
        database=DatabaseConfig(enable=False),
        yande_api=ApiConfig(retry=3, timeout=30, proxy_enable=False),
        downloader=DownloaderConfig(),
        scheduler=global_config.config.scheduler.model_dump(),
    )
    save_config(initial, test_file)

    # monkey-patch global_config 的 path_constant 与重新加载
    monkeypatch.setattr(
        "src.common.constant.path_constant.config_file", test_file
    )
    reloaded = load_config(test_file)
    monkeypatch.setattr(global_config, "config", reloaded)
    # 同时让 ConfigService 用的 from src.common import config 引用也跟着变
    monkeypatch.setattr("src.services.config.config", reloaded)

    yield test_file


def test_update_api_config_writes_headers(isolated_config):
    """update_api_config 写入新 headers 后,config.yande_api.headers 变化。"""
    from src.services.config import ConfigService

    new_api_config = ApiConfig(
        retry=5,
        timeout=60,
        proxy_enable=False,
        headers={
            "User-agent": "UA-new",
            "Accept": "text/html",
            "Accept-Language": "zh-CN",
            "Authorization": "Bearer xxx",
        },
    )
    ConfigService.update_api_config(new_api_config)

    # 内存中 config 已更新
    assert global_config.config.yande_api.headers.user_agent == "UA-new"
    assert (
        global_config.config.yande_api.headers.extra_headers["Authorization"]
        == "Bearer xxx"
    )

    # YAML 文件也写入
    yaml_data = yaml.safe_load(isolated_config.read_text())
    headers_section = yaml_data["yande_api"]["headers"]
    assert headers_section["User-agent"] == "UA-new"
    assert headers_section["Authorization"] == "Bearer xxx"
    # 平铺验证:不应有 extra_headers 键
    assert "extra_headers" not in headers_section


def test_update_api_config_preserves_other_fields(isolated_config):
    """更新 headers 后,其他字段(retry/timeout)保持新值不变。"""
    from src.services.config import ConfigService

    new_api_config = ApiConfig(
        retry=10,
        timeout=120,
        proxy_enable=True,
        headers={"User-agent": "UA-new"},
    )
    ConfigService.update_api_config(new_api_config)

    assert global_config.config.yande_api.retry == 10
    assert global_config.config.yande_api.timeout == 120
    assert global_config.config.yande_api.proxy_enable is True
```

- [ ] **Step 2: 运行测试验证失败**

```bash
.venv/bin/python -m pytest unit_test/services/test_config_update_headers.py -v
```

预期:测试失败,因 `update_api_config` 仍 `exclude={"headers"}`。

- [ ] **Step 3: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 4。

---

## Task 4: 后端 - 改 update_api_config 取消 exclude

**Files:**
- Modify: `backend/src/services/config.py:33-34`

- [ ] **Step 1: 移除 exclude 参数**

打开 `backend/src/services/config.py`,定位第 33-34 行:

```python
tmp_config = config.yande_api.model_dump(mode="json")
tmp_config.update(api_config.model_dump(exclude={"headers"}))
config.update_config(ApiConfig.model_validate(tmp_config))
```

改为:

```python
tmp_config = config.yande_api.model_dump(mode="json")
tmp_config.update(api_config.model_dump(mode="json"))
config.update_config(ApiConfig.model_validate(tmp_config))
```

- [ ] **Step 2: 运行测试验证通过**

```bash
.venv/bin/python -m pytest unit_test/services/test_config_update_headers.py -v
```

预期:2 个测试全部 PASS。

- [ ] **Step 3: 运行现有测试确保无回归**

```bash
.venv/bin/python -m pytest unit_test/ -v --ignore=unit_test/dao/test_yande_data_dao_downloaded_ids.py
```

预期:无新失败(忽略项是已知慢测试)。

- [ ] **Step 4: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 5。

---

## Task 5: 后端 - 验证调用方兼容性

**Files:**
- Modify: (可能) `backend/src/infrastructure/downloader.py:100`

- [ ] **Step 1: 检查 yande_api.py 是否仍可加载 headers**

```bash
.venv/bin/python -c "
from src.common.settings import ApiConfig
from src.infrastructure.yande_api import YandeApi

cfg = ApiConfig(headers={
    'User-agent': 'UA-test',
    'Authorization': 'Bearer xxx',
})
api = YandeApi.__new__(YandeApi)  # 跳过 __init__ 不联网
api._session = type('S', (), {})()
# 验证 model_dump 输出平铺
print(cfg.headers.model_dump(by_alias=True, exclude_none=True))
"
```

预期输出:`{'User-agent': 'UA-test', 'Authorization': 'Bearer xxx'}`

- [ ] **Step 2: 检查 downloader.py 的 headers 用法**

打开 `backend/src/infrastructure/downloader.py:69-100`,确认:

- 第 69 行:`headers=config.yande_api.headers.model_dump(by_alias=True)` — 模型序列化,已验证兼容 ✓
- 第 100 行:`headers.update(config.yande_api.headers)` — 直接 dict-style update

Pydantic v2 BaseModel 默认不支持 `dict.update(model)`,需要实测验证。

```bash
.venv/bin/python -c "
from src.common.settings import ApiConfig
cfg = ApiConfig(headers={'User-agent': 'UA-test', 'X-Custom': 'foo'})
headers = {}
try:
    headers.update(cfg.headers)
    print('OK, dict.update 兼容:', headers)
except Exception as e:
    print('FAIL:', type(e).__name__, e)
"
```

- [ ] **Step 3: 若 Step 2 失败,改用 model_dump**

打开 `backend/src/infrastructure/downloader.py:100`,改为:

```python
headers.update(config.yande_api.headers.model_dump(by_alias=True))
```

- [ ] **Step 4: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 6。

---

## Task 6: 前端 - 创建 HeadersEditorDialog.vue 组件

**Files:**
- Create: `frontend/src/components/HeadersEditorDialog.vue`

- [ ] **Step 1: 创建组件文件骨架**

创建 `frontend/src/components/HeadersEditorDialog.vue`:

```vue
<template>
  <el-dialog
    v-model="visible"
    title="编辑请求头"
    width="720px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 三个固定字段 -->
    <div class="fixed-headers">
      <div class="section-title">常用</div>
      <el-form :inline="false" label-width="140px">
        <el-form-item label="User-Agent">
          <el-input v-model="localHeaders.user_agent" size="small" clearable placeholder="如: Mozilla/5.0 ..." />
        </el-form-item>
        <el-form-item label="Accept">
          <el-input v-model="localHeaders.accept" size="small" clearable placeholder="如: text/html,..." />
        </el-form-item>
        <el-form-item label="Accept-Language">
          <el-input v-model="localHeaders.accept_language" size="small" clearable placeholder="如: zh-CN,zh;q=0.9,..." />
        </el-form-item>
      </el-form>
    </div>

    <!-- 自定义 headers -->
    <div class="custom-headers">
      <div class="section-title">自定义</div>
      <div v-for="(item, index) in customHeaders" :key="index" class="custom-row">
        <el-input
          v-model="item.key"
          placeholder="Header 名 (如 Authorization)"
          size="small"
          class="key-input"
        />
        <el-input
          v-model="item.value"
          placeholder="Header 值"
          size="small"
          class="value-input"
        />
        <el-button
          :icon="Delete"
          circle
          size="small"
          @click="removeCustom(index)"
        />
      </div>
      <el-button
        v-if="canShowAddButton"
        type="primary"
        plain
        size="small"
        @click="addCustomRow"
        style="margin-top: 8px"
      >
        + 添加自定义 header
      </el-button>
      <div v-else class="hint">
        提示: 在已有行的最后一行输入内容后会自动追加新行
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose" size="small">取消</el-button>
      <el-button type="primary" @click="handleSave" size="small">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  headers: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:modelValue', 'save'])

// v-model 双向绑定
const visible = ref(false)
watch(
  () => props.modelValue,
  (v) => {
    visible.value = v
    if (v) initFromProps()
  }
)
watch(visible, (v) => emit('update:modelValue', v))

// 三个固定字段(本地 state)
const localHeaders = ref({
  user_agent: '',
  accept: '',
  accept_language: '',
})

// 自定义 headers(数组形式便于编辑)
const customHeaders = ref([])

const FIXED_KEYS = new Set([
  'User-agent', 'user-agent', 'user_agent',
  'Accept', 'accept',
  'Accept-Language', 'accept-language', 'accept_language',
])

function initFromProps() {
  const h = props.headers || {}
  localHeaders.value = {
    user_agent: h['User-agent'] ?? h['user-agent'] ?? h.user_agent ?? '',
    accept: h['Accept'] ?? h.accept ?? '',
    accept_language:
      h['Accept-Language'] ?? h['accept-language'] ?? h.accept_language ?? '',
  }
  customHeaders.value = Object.entries(h)
    .filter(([k]) => !FIXED_KEYS.has(k))
    .map(([k, v]) => ({ key: k, value: String(v) }))
}

const hasEmptyRow = computed(() =>
  customHeaders.value.some(
    (r) => r.key.trim() === '' && r.value.trim() === ''
  )
)

const canShowAddButton = computed(
  () => customHeaders.value.length === 0 || hasEmptyRow.value
)

// 监听自定义 rows,自动追加空行(实现"无限编辑"体验)
watch(
  customHeaders,
  (rows) => {
    // 末尾若已是空行,不再追加
    if (rows.length === 0) return
    const last = rows[rows.length - 1]
    if (last.key.trim() === '' && last.value.trim() === '') return
    // 追加新空行
    rows.push({ key: '', value: '' })
  },
  { deep: true }
)

function addCustomRow() {
  customHeaders.value.push({ key: '', value: '' })
}

function removeCustom(index) {
  customHeaders.value.splice(index, 1)
}

function handleClose() {
  visible.value = false
}

function handleSave() {
  // 校验:重复键(大小写不敏感,破折号视为同)
  const normalizeKey = (k) =>
    k.toLowerCase().replace(/[-_]/g, '-')

  const allKeys = []
  if (localHeaders.value.user_agent.trim())
    allKeys.push(normalizeKey('User-agent'))
  if (localHeaders.value.accept.trim())
    allKeys.push(normalizeKey('Accept'))
  if (localHeaders.value.accept_language.trim())
    allKeys.push(normalizeKey('Accept-Language'))
  customHeaders.value.forEach((r) => {
    if (r.key.trim()) allKeys.push(normalizeKey(r.key))
  })

  const seen = new Set()
  const dup = []
  allKeys.forEach((k) => {
    if (seen.has(k)) dup.push(k)
    else seen.add(k)
  })
  if (dup.length > 0) {
    ElMessage.error(
      `存在重复的 Header 名: ${[...new Set(dup)].join(', ')}`
    )
    return
  }

  // 组装最终 dict(烤串命名)
  const result = {}
  if (localHeaders.value.user_agent.trim()) {
    result['User-agent'] = localHeaders.value.user_agent
  }
  if (localHeaders.value.accept.trim()) {
    result['Accept'] = localHeaders.value.accept
  }
  if (localHeaders.value.accept_language.trim()) {
    result['Accept-Language'] = localHeaders.value.accept_language
  }
  customHeaders.value.forEach((r) => {
    if (r.key.trim() !== '') result[r.key] = r.value
  })

  emit('save', result)
  visible.value = false
}
</script>

<style scoped>
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 12px 0 8px;
}

.fixed-headers {
  border-bottom: 1px dashed var(--border-color);
  padding-bottom: 12px;
  margin-bottom: 12px;
}

.custom-headers {
  padding-bottom: 12px;
}

.custom-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.custom-row .key-input {
  flex: 0 0 200px;
}

.custom-row .value-input {
  flex: 1;
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 8px;
}
</style>
```

- [ ] **Step 2: 验证组件语法(前端 dev server)**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

预期:无错误(Vite 编译通过)。

- [ ] **Step 3: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 7。

---

## Task 7: 前端 - Config.vue 集成 Dialog

**Files:**
- Modify: `frontend/src/views/Config.vue`

- [ ] **Step 1: 增加 import**

在 `frontend/src/views/Config.vue` 第 253 行附近(现有 PreviewCleanupDialog import 旁),增加:

```javascript
import PreviewCleanupDialog from '@/components/PreviewCleanupDialog.vue'
import HeadersEditorDialog from '@/components/HeadersEditorDialog.vue'
```

- [ ] **Step 2: 修改 apiConfig 默认 state**

在 `frontend/src/views/Config.vue` 第 258-263 行,改为:

```javascript
const apiConfig = ref({
  retry_times: 3,
  timeout: 30,
  proxy_enable: false,
  proxy: '',
  headers: {},
})
```

- [ ] **Step 3: 在 API 配置表单增加"请求头"项**

定位第 59-63 行(`saveApiConfig` 按钮之前),在 `<el-form-item>` 块内(代理地址之后)增加:

```vue
<el-form-item label="请求头">
  <el-button @click="showHeadersDialog = true" size="small">
    编辑请求头 ({{ headersCount }} 项)
  </el-button>
</el-form-item>
```

- [ ] **Step 4: 模板底部挂载 Dialog**

定位第 244 行(PreviewCleanupDialog 旁),增加:

```vue
<PreviewCleanupDialog v-model="showCleanupDialog" :mode="selectedCleanupMode" />
<HeadersEditorDialog
  v-model="showHeadersDialog"
  :headers="apiConfig.headers"
  @save="saveHeaders"
/>
```

- [ ] **Step 5: 增加 Script state / computed / 方法**

定位 `loadConfig` 函数(第 511 行附近),修改:

```javascript
const loadConfig = async () => {
  try {
    const response = await api.get('/config')
    const config = response.data
    apiConfig.value = {
      retry_times: config.yande_api.retry,
      timeout: config.yande_api.timeout,
      proxy_enable: config.yande_api.proxy_enable,
      proxy: config.yande_api.proxies?.http || '',
      headers: config.yande_api.headers || {},
    }
    // ...其他配置原样保留
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}
```

定位 `saving` ref(第 282 行)附近,增加:

```javascript
const showHeadersDialog = ref(false)
const headersCount = computed(() =>
  Object.keys(apiConfig.value.headers || {}).length
)
```

在 `saveApiConfig` 函数(第 534 行)附近,增加:

```javascript
async function saveHeaders(newHeaders) {
  saving.value = true
  try {
    await api.put('/config/api', {
      retry: apiConfig.value.retry_times,
      timeout: apiConfig.value.timeout,
      proxy_enable: apiConfig.value.proxy_enable,
      proxies: {
        http: apiConfig.value.proxy,
        https: apiConfig.value.proxy,
      },
      headers: newHeaders,
    })
    apiConfig.value.headers = newHeaders
    ElMessage.success('请求头已更新')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
```

- [ ] **Step 6: 验证前端编译**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

预期:无错误。

- [ ] **Step 7: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 8。

---

## Task 8: 前端 - 端到端验证(本地启动)

**Files:** 无(纯验证)

- [ ] **Step 1: 启动后端**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
.venv/bin/uvicorn src.service:main_app --reload --host 0.0.0.0 --port 8000 &
```

等待 3 秒,确认进程存活。

- [ ] **Step 2: 启动前端**

```bash
cd frontend && npm run dev &
```

等待 5 秒,确认 3000 端口监听。

- [ ] **Step 3: 通过 curl 验证 API**

```bash
# GET 当前 config
curl -s http://localhost:8000/api/v1/config | python -c "import sys, json; d = json.load(sys.stdin); print(json.dumps(d['data']['yande_api']['headers'], indent=2))"

# PUT 新 headers
curl -s -X PUT http://localhost:8000/api/v1/config/api \
  -H 'Content-Type: application/json' \
  -d '{
    "retry": 3,
    "timeout": 30,
    "proxy_enable": false,
    "proxies": {"http": "", "https": ""},
    "headers": {
      "User-agent": "Mozilla/5.0 NewUA",
      "Accept": "text/html",
      "Accept-Language": "zh-CN",
      "X-Test": "hello"
    }
  }' | python -m json.tool

# 再次 GET 验证
curl -s http://localhost:8000/api/v1/config | python -c "import sys, json; d = json.load(sys.stdin); print(json.dumps(d['data']['yande_api']['headers'], indent=2))"
```

预期:
- 第二次 GET 返回 `X-Test: hello` 新增键
- `extra_headers` 键不存在

- [ ] **Step 4: 验证 YAML 文件**

```bash
grep -A 10 "yande_api" backend/config/config.yaml
```

预期:看到 `X-Test: hello` 平铺在 `headers:` 段下。

- [ ] **Step 5: 关闭后台进程**

```bash
pkill -f "uvicorn src.service"
pkill -f "vite"
```

- [ ] **Step 6: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 9。

---

## Task 9: 前端 - 浏览器手动验证清单

**Files:** 无(纯手动验证)

- [ ] **Step 1: 浏览器打开配置页**

启动服务后,浏览器访问 `http://localhost:3000/#/config`(或项目对应路由)。

- [ ] **Step 2: 验证 API 配置菜单**

确认看到:
- 重试次数 / 超时时间 / 启用代理 / 代理地址 / **编辑请求头 (N 项)** 按钮

预期:N 反映当前 headers 数量(应为已有 + 自定义项之和)。

- [ ] **Step 3: 打开 Dialog**

点击"编辑请求头"按钮。

预期:
- Dialog 弹出,标题"编辑请求头"
- "常用"区域三个固定字段已预填当前值
- "自定义"区域显示非固定字段
- 自动追加了一行空行(便于继续添加)

- [ ] **Step 4: 测试编辑/删除/添加**

- 修改 User-Agent 值,保存 → 重新打开 Dialog → 值更新 ✓
- 删除一个自定义 header 行,保存 → YAML 中该键消失 ✓
- 添加一个 `Authorization: Bearer xxx`,保存 → YAML 中新增该键 ✓

- [ ] **Step 5: 测试校验**

- 在自定义区域输入一个重复键(如 `accept: duplicate`),保存
- 预期:`ElMessage.error` 提示"存在重复的 Header 名",不调用 API

- [ ] **Step 6: 测试取消**

- 修改任意字段但不保存,点"取消"
- 重新打开 Dialog → 修改未生效 ✓

- [ ] **Step 7: 验证移动端适配**

浏览器 DevTools 切到手机模拟,打开 Dialog,确认宽度自适应。

- [ ] **Step 8: 暂不 commit**

按用户指示不提交。本任务完成,继续 Task 10。

---

## Task 10: 文档 + 版本号(可选)

**Files:**
- Modify: `README.md`(可选,功能列表)
- Modify: `frontend/package.json:3` (version)
- Modify: `pyproject.toml` (version)
- Modify: `backend/src/__init__.py` (AppConfig.version)

> 仅在用户确认实施完成后执行版本号升级。

- [ ] **Step 1: 暂不执行**

按用户指示,版本号升级留待用户明确同意后单独执行(参见 `docs/release.md`)。

---

## 收尾确认

完成上述 9 个任务后:

1. 暂不 commit(全部保留在工作区)
2. 通知用户审查代码改动
3. 用户审查 + 确认 → 用户执行 `git add` + `git commit` + `git push`(按全局规则不推送代码,等用户授权)
4. 用户决定是否继续 Task 10(版本号升级)