# Yande.re Spider 接口编写规范

> 本规范基于 `next_dev` 分支的重构经验总结构建，对比了 `next`（AI原写）和 `next_dev`（可读性重构后）的代码差异。

**详细文档请参考 [docs/](docs/) 目录。**

---

## 核心原则

1. **分层职责**：`api/` → `services/` → `dao/` 严禁跨层调用
2. **类型安全**：所有函数必须声明返回类型注解
3. **统一响应**：`BaseResponse` + `APIException` + `ErrMsg`
4. **自动化**：路由注册、中间件加载全部自动化

---

## 快速参考

| 操作 | 规范 |
|------|------|
| 新增 API 路由 | 在 `api/v1/` 下创建文件，APILoader 自动发现 |
| 返回响应 | `BaseResponse(message=ErrMsg.OK.msg, data={...})` |
| 抛出错误 | `raise APIException(ErrMsg.XXX, e=e)` |
| 新增 DAO | 继承 `BaseDAO`，使用 `self.session` 操作数据库 |
| 配置常量 | 在 `common/constant.py` 中定义 `PathConstant`、`ErrMsg` 等 |
| **升级版本** | **改 3 处 version 源**（`package.json` + `pyproject.toml` + `AppConfig.version`）→ commit → tag → `gh release create` → `gh issue create` → `gh pr create --base next`（详见 [docs/release.md](docs/release.md)）|

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/structure.md](docs/structure.md) | 项目目录结构、层级职责划分 |
| [docs/api-route.md](docs/api-route.md) | API 路由文件模板、关键规则 |
| [docs/response.md](docs/response.md) | BaseResponse、响应格式约定 |
| [docs/error-handling.md](docs/error-handling.md) | ErrMsg 枚举、APIException、错误中间件 |
| [docs/dao.md](docs/dao.md) | BaseDAO、Session 管理、编写规范 |
| [docs/middleware.md](docs/middleware.md) | 中间件注册顺序、模板、RequestSessionMiddleware |
| [docs/router-registry.md](docs/router-registry.md) | APILoader 自动路由发现、RouterMap |
| [docs/constants.md](docs/constants.md) | PathConstant、TaskStatus 等常量定义 |
| [docs/design.md](docs/design.md) | 架构设计详解 |
| [docs/tasks.md](docs/tasks.md) | 开发任务追踪 |
| [docs/release.md](docs/release.md) | **版本升级流程**（三处 version 源 + 启动 banner + Vite 注入 + GH Release + Issue + PR）|

---

## 代码风格要点

1. **类型注解**：所有函数必须声明返回类型
2. **Pydantic Field**：请求模型使用 `Field()` 定义校验规则
3. **docstring**：每个 API 路由添加 `"""描述"""` 文档字符串
4. **日志记录**：在 `middleware/loggers.py` 统一日志格式
5. **枚举优先**：状态码、错误码使用枚举而非硬编码字符串
6. **frozen 配置**：PathConstant 等配置类使用 `frozen=True` 防止意外修改

---

## 重构状态追踪

### 已完成的重构（next_dev 分支）

| 重构项 | 状态 | 提交记录 |
|--------|------|----------|
| 目录结构重组（backend/src/） | ✅ 完成 | 738beef, d4a01e4 |
| 自动路由注册（APILoader） | ✅ 完成 | b8afae8 |
| 统一响应格式（BaseResponse） | ✅ 完成 | 1489e01 |
| 统一错误处理（APIException + ErrMsg） | ✅ 完成 | 1489e01 |
| 中间件层拆分（middleware/） | ✅ 完成 | 6ef8596 |
| 常量管理统一（PathConstant） | ✅ 完成 | 8a05889 |
| 导入路径标准化（src.xxx） | ✅ 完成 | 8a05889 |
| DAO 层重构 | ✅ 完成 | bea5017 |
| API 路由系统重构 | ✅ 完成 | 3331539 |
| 数据库模型模块化 | ✅ 完成 | 8ce9224 |

### 代码规范检查清单

**API 路由文件检查**：
- [ ] 是否使用 `APIException(ErrMsg.XXX, e=e)` 模式
- [ ] 是否返回 `BaseResponse` 或继承类
- [ ] 是否声明返回类型注解
- [ ] 是否添加 docstring
- [ ] Request Model 是否使用 `Field()` 校验
- [ ] 本地 tag 匹配：默认精确 token；`*` 表通配（`pan*` 前缀，`p*n` 中间）；`-` 表排除；纯 `*` 忽略（详见 `docs/superpowers/specs/2026-07-18-local-tag-exact-match-design.md`）

**响应格式检查**：
- [ ] 成功响应：`BaseResponse(message=ErrMsg.OK.msg, data={...})`
- [ ] 错误响应：`raise APIException(ErrMsg.XXX, e=e)`
- [ ] 避免返回原始字典

---

*最后更新：基于 next_dev 分支 fd42787 提交记录总结*