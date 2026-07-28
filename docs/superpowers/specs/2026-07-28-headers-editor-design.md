# 请求头编辑功能设计

> **日期**: 2026-07-28
> **作者**: Sisyphus
> **状态**: 设计已定稿,等待实施计划
> **关联**: `frontend/src/views/Config.vue` · `backend/src/common/settings.py` · `backend/src/services/config.py`

---

## 1. 背景

当前配置界面(API 配置菜单)允许编辑重试次数、超时时间、代理开关与代理地址,但**不允许编辑 HTTP 请求头**(`yande_api.headers`)。后端 `ConfigService.update_api_config` 显式 `exclude={"headers"}`,意味着当前 API 通道无法修改 headers。

而 headers 经常因 yande.re 反爬策略升级需要调整(典型场景:User-Agent 过期需要更新),目前只能手动编辑 `config/config.yaml` 文件,使用体验较差。

**目标**:在配置页面提供可视化编辑器,允许用户在不接触 YAML 文件的前提下修改请求头。

---

## 2. 范围

### 2.1 编辑能力

| 类别 | 字段 | 说明 |
|---|---|---|
| 固定字段 | `User-Agent` | HTTP 标准命名,必填项,影响 yande.re 反爬识别 |
| 固定字段 | `Accept` | HTTP 标准命名 |
| 固定字段 | `Accept-Language` | HTTP 标准命名 |
| 自定义字段 | `X-Custom`、`Authorization` 等任意键 | 用户按需添加/删除 |

### 2.2 不在范围内

- ❌ 不修改 headers 在 requests 库中的使用方式(调用方代码不变)
- ❌ 不增加 headers 模板/预设功能(避免功能蔓延)
- ❌ 不实现 headers 加密存储(明文存在 config.yaml,符合现有约定)
- ❌ 不影响数据库配置、下载器配置、调度器配置

---

## 3. 用户故事

> 作为项目运维者,
> 我希望通过网页配置界面修改 yande.re 请求头(尤其是 User-Agent),
> 以便在反爬策略升级时无需登录服务器编辑 YAML 文件。

**验收标准**:
1. 配置页"API配置"菜单显示"编辑请求头"按钮,旁边显示当前 header 数量
2. 点击按钮弹出 Dialog,显示三个固定字段(预填当前值)+ 自定义键值对区域
3. 用户可编辑/清空固定字段的值,也可添加/删除任意自定义 header
4. 点击保存后,Dialog 关闭,YAML 文件更新(刷新页面后内容仍生效)
5. 取消按钮不保存任何修改
6. 输入空键/空值/重复键时给出友好提示,不提交请求

---

## 4. 架构

```
┌───────────────────────────────────────────────────────────────┐
│  前端 (Vue3 + Element Plus)                                  │
│                                                               │
│  Config.vue                                                   │
│    ├─ "编辑请求头" 按钮 (在 API配置表单内)                    │
│    └─ HeadersEditorDialog                                     │
│         ├─ 三个固定字段输入框                                  │
│         └─ 自定义 header 动态键值对表格                        │
└───────────────────────────────────────────────────────────────┘
                            ↓ PUT /config/api
┌───────────────────────────────────────────────────────────────┐
│  后端 (FastAPI + Pydantic)                                    │
│                                                               │
│  api/v1/config.py                                             │
│    └─ update_api_config(ApiConfig)                            │
│         └─ ConfigService.update_api_config()                  │
│              └─ ApiConfig.model_validate()                    │
│                   └─ Headers.model_validator (mode='before')  │
│                        └─ 平铺/归一化处理                      │
│              └─ config.update_config() → save_config() → YAML │
└───────────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  config/config.yaml                                          │
│    yande_api:                                                 │
│      headers:                                                 │
│        User-agent: ...                                        │
│        Accept: ...                                            │
│        Accept-Language: ...                                   │
│        X-Custom: ...          # 平铺存储                      │
└───────────────────────────────────────────────────────────────┘
                            ↓ (启动时由 settings 加载)
┌───────────────────────────────────────────────────────────────┐
│  infrastructure/yande_api.py                                  │
│    headers.model_dump(by_alias=True, exclude_none=True)       │
│    → self._session.headers.update(...)                        │
│  infrastructure/downloader.py                                 │
│    config.yande_api.headers.model_dump(by_alias=True)         │
│    config.yande_api.headers (直接 dict-style update)          │
└───────────────────────────────────────────────────────────────┘
```

---

## 5. 后端设计

### 5.1 `backend/src/common/settings.py` — `ApiConfig.Headers` 重构

**当前**:
```python
class ApiConfig(ConfigModel):
    class Headers(ConfigModel):
        user_agent: str = Field('', serialization_alias='User-agent')
        accept: str = Field('', serialization_alias='Accept')
        accept_language: str = Field('', serialization_alias='Accept-Language')

    # ...
    headers: Optional[Headers] = Field(Headers())
```

**目标**:
```python
class ApiConfig(ConfigModel):
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
            # 固定字段的烤串 + 蛇形两种命名都要排除
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

**关键点**:

1. **`populate_by_name=True`**:允许用 `User-agent` 或 `user_agent` 都能识别固定字段
2. **`model_serializer(mode='wrap')`**:序列化(dump)时把 `extra_headers` 字典里的键平铺到顶层
3. **`model_validator(mode='before')`**:反序列化(load)时把不属于固定字段的键归入 `extra_headers`
4. **`extra_headers: dict[str, str]`**:`extra` 在 Pydantic v2 中是保留名,故用 `extra_headers` 而非 `extra`

**向后兼容验证**:
- 现有 `config.yaml` 中的 `user-agent` / `Accept` / `Accept-Language` 会被 `_flatten_extra` 识别为固定字段(在 `fixed_keys` 集合中)
- `model_validator` 处理后,`user-agent` 烤串命名通过 `alias='User-agent'` 被识别为 `user_agent` 字段
- `_ser` 序列化时按 `serialization_alias='User-agent'` 输出为烤串
- **YAML 文件在第一次写入后,键名会被规范化为烤串**(例:`user-agent` → `User-agent`),这是预期行为

### 5.2 `backend/src/services/config.py` — 允许 headers 更新

**当前**(`update_api_config` 第 33-34 行):
```python
tmp_config = config.yande_api.model_dump(mode="json")
tmp_config.update(api_config.model_dump(exclude={"headers"}))  # ← 排除 headers
```

**目标**:
```python
tmp_config = config.yande_api.model_dump(mode="json")
tmp_config.update(api_config.model_dump(mode="json"))  # 不再 exclude
```

**变更说明**:仅仅删除 `exclude={"headers"}`,其余逻辑保持不变。`update_config()` 内部调用 `save_config()` 会自动按新 schema 序列化写入 YAML。

### 5.3 错误处理

| 场景 | 后端响应 |
|---|---|
| `headers` 字段缺失 | Pydantic 使用默认值 `Headers()`,无错误 |
| `headers` 字段为非 dict | 422 Validation Error(`model_validator(mode='before')` 触发) |
| 自定义 header 的 value 不是字符串 | 422 Validation Error(`extra_headers: dict[str, str]` 校验) |
| 文件写失败 | `update_api_config` 返回 false → `APIException(CONFIG_UPDATE_ERROR)` |

### 5.4 调用方兼容性验证

**`infrastructure/yande_api.py:64`**:
```python
self._session.headers.update(
    headers.model_dump(by_alias=True, exclude_none=True)
)
```

新 `model_dump(by_alias=True)`:
- 固定字段输出为烤串(同旧)
- `extra_headers` 字段经 `model_serializer` 平铺输出
- **兼容**

**`infrastructure/downloader.py:69`**:
```python
headers=config.yande_api.headers.model_dump(by_alias=True)
```

同上,兼容。

**`infrastructure/downloader.py:100`**:
```python
headers.update(config.yande_api.headers)
```

Pydantic BaseModel 支持 `dict.update(model)` 调用,因为 BaseModel 实现了 `__iter__` 返回字段元组 / 或直接当 dict 用 — 实际上,**这一行用 Pydantic v2 的 model 对象作为 dict-like,需要确认**。如果有问题,改为:
```python
headers.update(config.yande_api.headers.model_dump(by_alias=True))
```

具体由实施时的小测试验证。

---

## 6. 前端设计

### 6.1 `frontend/src/components/HeadersEditorDialog.vue` — 新增组件

独立的 Dialog 组件,接收 `modelValue`(v-model 显示状态)与 `headers`(初始 dict)两个 props,触发 `update:modelValue` 与 `save` 两个 events。

#### Props / Emits

> 注:本节用 TypeScript 类型标注说明 props/emits 契约,实际项目代码是 JS,实施时按 JS 语法实现等价逻辑即可。

```typescript
interface Props {
  modelValue: boolean         // v-model:visible
  headers: Record<string, string>   // JS 中即 Object
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'save', headers: Record<string, string>): void
}
```

#### 模板结构

```
<el-dialog v-model="visible" title="编辑请求头" width="720px">
  ├── 常用字段区(.fixed-headers)
  │    ├── User-Agent
  │    ├── Accept
  │    └── Accept-Language
  ├── 自定义字段区(.custom-headers)
  │    ├── 动态键值对行(el-input + el-input + 删除按钮)
  │    └── "+ 添加自定义 header" 按钮
  └── footer
       ├── 取消
       └── 保存
</el-dialog>
```

#### 核心逻辑

```typescript
// 三个固定字段本地 state
const localHeaders = ref({
  user_agent: '',
  accept: '',
  accept_language: '',
})

// 自定义 headers(数组形式,便于 v-for 编辑)
const customHeaders = ref<Array<{ key: string; value: string }>>([])

// Dialog 打开时初始化
function initFromProps() {
  const h = props.headers || {}
  localHeaders.value = {
    user_agent: h['User-agent'] ?? h.user_agent ?? '',
    accept: h['Accept'] ?? h.accept ?? '',
    accept_language: h['Accept-Language'] ?? h.accept_language ?? '',
  }
  // 剥离固定字段,剩下的归入自定义区域
  const fixed = new Set([
    'User-agent', 'user-agent', 'user_agent',
    'Accept', 'accept',
    'Accept-Language', 'accept-language', 'accept_language',
  ])
  customHeaders.value = Object.entries(h)
    .filter(([k]) => !fixed.has(k))
    .map(([k, v]) => ({ key: k, value: String(v) }))
}

// 保存时组装最终 dict(用 HTTP 标准烤串命名)
function handleSave() {
  // 校验:重复键(大小写不敏感),固定字段与自定义字段都要纳入检查
  const normalizeKey = (k: string) => k.toLowerCase().replace(/[-_]/g, '-')
  const allKeys: string[] = []
  if (localHeaders.value.user_agent.trim())
    allKeys.push(normalizeKey('User-agent'))
  if (localHeaders.value.accept.trim())
    allKeys.push(normalizeKey('Accept'))
  if (localHeaders.value.accept_language.trim())
    allKeys.push(normalizeKey('Accept-Language'))
  customHeaders.value.forEach(r => {
    if (r.key.trim()) allKeys.push(normalizeKey(r.key))
  })
  const seen = new Set<string>()
  const dup: string[] = []
  allKeys.forEach(k => {
    if (seen.has(k)) dup.push(k)
    else seen.add(k)
  })
  if (dup.length > 0) {
    ElMessage.error(`存在重复的 Header 名: ${[...new Set(dup)].join(', ')}`)
    return
  }

  // 组装最终 dict(烤串命名)
  const result: Record<string, string> = {}
  if (localHeaders.value.user_agent.trim())
    result['User-agent'] = localHeaders.value.user_agent
  if (localHeaders.value.accept.trim())
    result['Accept'] = localHeaders.value.accept
  if (localHeaders.value.accept_language.trim())
    result['Accept-Language'] = localHeaders.value.accept_language
  customHeaders.value.forEach(r => {
    if (r.key.trim() !== '') result[r.key] = r.value
  })
  
  emit('save', result)
  visible.value = false
}
```

详细代码见实施计划。

### 6.2 `frontend/src/views/Config.vue` — 集成

**改动 1**:API 配置表单新增"请求头"项
```vue
<el-form-item label="请求头">
  <el-button @click="showHeadersDialog = true" size="small">
    编辑请求头 ({{ headersCount }} 项)
  </el-button>
</el-form-item>
```

**改动 2**:模板底部挂载 Dialog
```vue
<HeadersEditorDialog
  v-model="showHeadersDialog"
  :headers="apiConfig.headers"
  @save="saveHeaders"
/>
```

**改动 3**:Script 增加 state、computed、方法
```typescript
import HeadersEditorDialog from '@/components/HeadersEditorDialog.vue'

const apiConfig = ref({
  retry_times: 3,
  timeout: 30,
  proxy_enable: false,
  proxy: '',
  headers: {} as Record<string, string>,  // ← 新增
})

const showHeadersDialog = ref(false)
const headersCount = computed(() => 
  Object.keys(apiConfig.value.headers || {}).length
)

// 加载配置时填充 headers
function loadConfig() {
  // ...
  apiConfig.value.headers = config.yande_api.headers || {}
}

// 保存 headers
async function saveHeaders(newHeaders: Record<string, string>) {
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
    apiConfig.value.headers = newHeaders  // 同步本地 state
    ElMessage.success('请求头已更新')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
```

### 6.3 前端校验

| 校验项 | 时机 | 处理 |
|---|---|---|
| 重复键(大小写不敏感) | 保存时 | `ElMessage.error` 提示,不调用 API |
| 空键 + 空值 | 自动过滤 | 自定义 header 中空键的行不会出现在最终 dict |
| 键名含特殊字符 | 不校验 | 后端透传给 requests 库,由 HTTP 协议层处理 |
| 三个固定字段全部为空 | 允许 | 等价于"无 User-Agent",正常保存 |

### 6.4 UI 风格

- 复用 Element Plus 组件(`el-dialog`、`el-input`、`el-button`、`el-icon`)
- 暗色模式适配:跟随 Config.vue 已有的 `--bg-primary` / `--text-primary` CSS 变量
- 移动端:Dialog 自带响应式,小屏幕下 Element Plus 自动全屏

---

## 7. 数据流(单向)

```
用户点击"编辑请求头"按钮
        ↓
Config.vue: showHeadersDialog = true
        ↓
HeadersEditorDialog: visible = true, initFromProps()
        ↓
  - 拆分 props.headers → 固定字段(3 个) + 自定义键值对
        ↓
用户编辑(改值/增删行)
        ↓
HeadersEditorDialog: handleSave()
        ↓
  - 校验(重复键 / 空行过滤)
  - 组装最终 dict(烤串命名)
        ↓
emit('save', result)
        ↓
Config.vue.saveHeaders(newHeaders)
        ↓
PUT /config/api { retry, timeout, ..., headers }
        ↓
后端 ConfigService.update_api_config()
        ↓
  - 合并 yande_api 现有字段(headers 不再 exclude)
  - ApiConfig.model_validate() → Headers.model_validator 平铺/归一化
  - config.update_config() → save_config()
        ↓
YAML 文件更新(headers 平铺在 yande_api.headers 段)
        ↓
Config.vue: apiConfig.value.headers = newHeaders (本地 state 同步)
        ↓
"请求头已更新" 提示
```

---

## 8. 测试

### 8.1 后端单测

| 用例 | 验证点 |
|---|---|
| `test_headers_serialize_flat` | `Headers().model_dump()` 输出平铺 dict,无 `extra_headers` 键 |
| `test_headers_serialize_with_extra` | 设置 `extra_headers={"X-Custom": "foo"}` 后,序列化输出含 `X-Custom` 键 |
| `test_headers_deserialize_pickup_extra` | 输入 dict 含未知键(如 `Authorization`),该键归入 `extra_headers` |
| `test_headers_accept_kebab_alias` | 输入 `{"User-agent": "..."}` 能识别为 `user_agent` 字段 |
| `test_headers_accept_snake_name` | 输入 `{"user_agent": "..."}` 也能识别 |
| `test_headers_round_trip` | `dump → load → dump` 数据一致 |
| `test_update_api_config_includes_headers` | 调用 `update_api_config({"headers": {"X-Foo": "bar"}})` 后,`config.yande_api.headers["X-Foo"] == "bar"` |
| `test_yaml_flat_dump` | `save_config()` 写入的 YAML 中 headers 平铺(无 `extra_headers` 字段) |

### 8.2 前端验证

考虑到 Config.vue 目前没有前端单测,且改动是表单 UI 性质,建议**手动验证**为主:

**手动验证清单**:
- [ ] 打开配置页 → API配置菜单 → 显示"编辑请求头(N 项)"按钮(N 反映当前 headers 数)
- [ ] 点击按钮 → Dialog 弹出
- [ ] 三个固定字段预填当前值(从 YAML 加载)
- [ ] 自定义区域显示非固定字段
- [ ] 修改任意值后保存 → Dialog 关闭 → 提示成功
- [ ] 刷新页面 → 修改生效(从后端 GET 加载到新值)
- [ ] 检查 `config/config.yaml` 文件,headers 平铺存储
- [ ] 添加一个自定义 header(如 `Authorization: Bearer xxx`)→ 保存 → 重启服务 → 下载任务正常带此 header 发送
- [ ] 输入重复键名 → 保存 → 提示错误,不调用 API
- [ ] 取消按钮 → 不修改任何 state
- [ ] 移动端(浏览器 DevTools) → Dialog 自适应宽度

### 8.3 回归测试

- [ ] 现有 `update_api_config` 调用方(若有任何)不受影响
- [ ] `yande_api.py` 与 `downloader.py` 启动时仍能正确加载 headers(用现有的 config.yaml 测试)
- [ ] `get_system_config` API 返回的 `headers` 字段结构不变(键名仍是烤串)
- [ ] 重置配置(`POST /config/reset?section=api`)后,headers 重置为默认值

---

## 9. 部署与兼容性

### 9.1 兼容性

| 项 | 影响 |
|---|---|
| 现有 config.yaml | **键名会被规范化**(`user-agent` → `User-agent`),首次写入后变化,但语义不变 |
| 数据库 schema | 无 |
| Docker 镜像 | 无新依赖 |
| 前端依赖 | 无新依赖(沿用 Element Plus 与 `@element-plus/icons-vue`) |
| 后端调用方 | 无需调整(已验证 `yande_api.py` / `downloader.py` 兼容) |

### 9.2 风险与缓解

| 风险 | 缓解 |
|---|---|
| 用户清空所有 headers 后保存,导致请求失败 | 允许但显示 `ElMessage.warning` 提示(可选):"所有 headers 已清空,可能导致 API 请求失败" |
| `model_validator(mode='before')` 与 `populate_by_name` 配合的边界 case | 实施时增加单测覆盖烤串/蛇形/混用三种命名 |
| downloader.py 第 100 行 Pydantic model 当 dict 用 | 实施时单独测试,如有需要改为 `.model_dump(by_alias=True)` |
| YAML 首次写入后键名规范化,导致 git diff 噪音 | 在 PR 描述中说明,合并时 squash |

### 9.3 文档更新

- [ ] `docs/api-route.md`:无需更新(API 端点不变)
- [ ] `docs/design.md`:可选更新(架构图未涉及 headers 编辑流)
- [ ] `README.md`:可选更新(功能列表加"可编辑请求头")
- [ ] 本 spec 文档本身已就位

### 9.4 版本号

按 `AGENTS.md` 与 `docs/release.md` 规范,这是用户配置面的小功能,小版本号递增(v1.1.7 → v1.1.8)。
需要改 3 处 version 源:

| 文件 | 字段 |
|---|---|
| `frontend/package.json` | `"version"` |
| `pyproject.toml` | `version` |
| `backend/src/__init__.py` | `AppConfig.version` |

实际执行时机在实施完成后按 `docs/release.md` 流程操作(commit → tag → `gh release create` → `gh issue create` → `gh pr create --base next`)。

---

## 10. 决策记录

| 决策 | 备选 | 选定 | 理由 |
|---|---|---|---|
| 编辑范围 | 固定 / 自由 / 混合 | **混合** | 平衡 UX 与灵活性 |
| YAML 存储 | 平铺 / 嵌套 extra / 带前缀 | **平铺** | 与现有 schema 一致,YAML 可读 |
| UI 入口 | 内嵌表单 / 按钮+Dialog | **按钮+Dialog** | 避免主表单臃肿,headers 内容多时 Dialog 更舒展 |
| 后端 schema | 纯 dict / 嵌套 + 序列化 / 仅去 exclude | **嵌套 + 序列化** | 保留字段约束与文档,自定义时仍灵活 |
| 字段命名 | 全烤串 / 全蛇形 / 双向 | **双向(烤串为标准)** | 与 HTTP 标准一致(YAML/调用方),API 内部也接受蛇形 |

---

## 11. 待办

- [ ] 实施计划由 `writing-plans` 技能生成
- [ ] 实施完成后,按 `docs/release.md` 升级版本号 + tag + release + PR