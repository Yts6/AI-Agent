# B 站 5 门课 · 重点知识整理 + 自测题库

> 用途：把 5 门课里**真正用得上的知识**压成一份复习稿，配 30 道折叠答案的自测题。
> 对齐文档：`AI-Agent实习上岸学习指南.md` §6.2-6.5、`智能体实习-分步执行手册.md` Step 8-26。
> 生成时间：2026-10-20 · 全部 BV 号已通过 B 站接口核验（集数 / 时长 / 分 P 标题）。

---

## 0. 这份文档怎么用

| 场景 | 怎么用 |
|---|---|
| **跟课之前** | 先扫一遍对应章节的"知识地图"，知道这门课要解决什么问题，看视频时不迷路 |
| **跟课之中** | 卡住了来这里查"坑"小节，比拉进度条快 |
| **跟课之后** | 做对应章节的自测题，**先只看题目**，心里答完再点开答案 |
| **面试前** | 只刷每章末尾的「面试会怎么问」+ 全部 30 题 |

**折叠答案怎么看**：本文用 HTML 折叠块（details/summary）实现。Typora / Obsidian / VS Code 预览 / GitHub 都会渲染成"点击展开"，打印时会自动展开。

**做题原则**：答不出来就标红，别扫一眼就往下翻——**阅读答案会产生"我懂了"的错觉**，这是刷题最大的坑。

---

## 1. 五门课总览

| # | 课程 | BV 号 | 体量 | 本文覆盖 | 对应手册 |
|---|---|---|---|---|---|
| 0 | RAG 工作机制详解（马克的技术工作坊） | `BV1JLN2z4EZQ` | 18 min | 全部 | 建立全局直觉 |
| 1 | 零基础 FastAPI + Vue3 + LangChain（知了传课） | `BV1Vr25ByEpG` | 42 集 / 7.8 h | **第 04-18 集** | Step 8-9 |
| 2 | FastAPI + LangGraph 智能实验室预约系统（程序员青戈） | `BV13hbP6zEUd` | 27 集 / 25.7 h | 全部 | Step 8-9 + 17 + 21-25 |
| 3 | Milvus 3.0 + RAG 企业知识库（马士兵说） | `BV1HZgV6TEen` | 83 集 / 14.5 h | **【RAG】01-20** | Step 14-18 |
| 4 | AI Agent + RAG + MCP 校园课程助手（程序员青戈） | `BV1puaw6oE6X` | 8 集 / 7.9 h | 全部 | Step 26 |

> 第 3 课 21 集以后是就业市场、简历包装、面试录音，**不属于知识课**；但【面试题】01-15 值得单独刷，正文末尾我列了对应主题。

---

## 2. 知识地图：一条主线串起 5 门课

```
        第 0 课（18 分钟）
        RAG 全链路直觉：解析 → 切分 → 向量化 → 存储 → 召回 → 重排 → 生成 → 评估
                 │
                 ▼
        第 1 课  FastAPI：把"调模型"包成能跑的服务
                 │   （路由 / Pydantic / 依赖注入 / ORM / JWT / 422）
                 ▼
        第 2 课  业务系统 + AI 助手：会话、SSE、Tool Calling、LangGraph、状态机
                 │   （先手写 Function Calling，再上框架）
                 ▼
        第 3 课  RAG 工程化：Milvus、混合检索、稠密+稀疏向量
                 │   （把"能答"变成"答得准、有数据"）
                 ▼
        第 4 课  MCP：把工具标准化，接缝从 N×M 降到 N+M
                 │
                 ▼
        产出：一个能演示、能讲取舍、有评估数据的项目
```

---

## 3. 第 0 课 · RAG 全链路（18 分钟建立直觉）

**一句话**：RAG = 先查资料，再让模型"开卷考试"。

### 3.1 八个环节，以及每个环节的失败点

| 环节 | 做什么 | 最容易翻车的地方 |
|---|---|---|
| ① 加载 | PDF / Word / Markdown 读成文本 | 扫描件提取空白、表格错位、双栏串行 |
| ② 切分 | 切成能进上下文的 chunk | 切碎导致语义不完整；切太大导致检索不准 |
| ③ 向量化 | embedding 模型把文本映射成向量 | 换模型不重建索引；中文场景用英文模型 |
| ④ 存储 | 向量库建索引 | 维度写死、metadata 丢失（丢了出处就没法验证） |
| ⑤ 召回 | 相似度检索 top-k | 专有名词、编号、代码检索不到（纯语义的短板） |
| ⑥ 重排 | rerank 精排 | 不做重排就硬塞给模型，噪声大 |
| ⑦ 生成 | 拼 Prompt 生成答案 | 不约束"只依据资料回答"→ 幻觉 |
| ⑧ 评估 | 定量测召回率 / 忠实度 | 全靠"我感觉还行" |

### 3.2 必须记住的四句话

1. **RAG 的天花板在检索，不在模型**——召回不到，再强的模型也只能编。
2. **没有出处的答案不可验证**——面试官第一个问题往往是"你怎么知道它答对了"。
3. **chunk size 是要用实验说话的**——"网上说 500"不算理由。
4. **每加一个组件都要跑一次评估**——否则优化是玄学。

### 3.3 面试会怎么问

- RAG 和微调怎么选？（知识频繁更新 → RAG；风格/格式/领域语言 → 微调；两者可叠加）
- 为什么要有 rerank，不在检索时直接排？（召回模型是双塔、可预先建索引、快；rerank 是交叉编码器、逐对打分、准但慢，只能对小候选集做）

---

## 4. 第 1 课 · FastAPI（第 04-18 集）

**一句话**：FastAPI = 类型注解驱动的 Web 框架，自带校验、序列化、接口文档。

### 4.1 ASGI / 运行方式

- FastAPI 跑在 **ASGI** 上（Starlette），服务器是 **uvicorn**；Flask/Django 传统是 WSGI（同步、一请求一线程）。
- `async def` 路由跑在事件循环里，**遇到同步阻塞调用会卡死整个服务**——这是新手第一大坑（见 4.9）。

```bash
pip install "fastapi[standard]"
uvicorn main:app --reload --port 8000   # main.py 里的 app 对象
fastapi dev main.py                     # 新版官方 CLI
```

- 访问 `/docs`（Swagger UI）、`/redoc`、`/openapi.json`。**接口文档是白送的，面试演示时直接用。**

### 4.2 路由与 APIRouter

```python
# routers/users.py
router = APIRouter(prefix="/users", tags=["用户"])

@router.get("/{user_id}")
async def get_user(user_id: int):
    ...

# main.py
app.include_router(users.router)
app.include_router(chat.router, dependencies=[Depends(verify_token)])  # 整个模块挂鉴权
```

- `tags` 决定文档分组，`prefix` 决定路径前缀。**项目超过 3 个模块就该拆 router。**

### 4.3 三类参数：路径 / 查询 / 请求体

| 类型 | 来源 | 写法 | 校验 |
|---|---|---|---|
| 路径参数 | URL 段 | `/items/{item_id}` + `item_id: int` | 类型转换失败 → 422 |
| 查询参数 | `?skip=0&limit=10` | 函数里**不在路径中的普通参数** | `Query(0, ge=0, le=100)` |
| 请求体 | JSON body | Pydantic 模型参数 | `Field(...)` |

```python
from fastapi import Path, Query, Body

@app.get("/items/{item_id}")
async def read(item_id: int = Path(..., gt=0),
               q: str | None = Query(None, max_length=50),
               limit: int = Query(10, le=100)):
    ...

@app.post("/ask")
async def ask(inp: AskIn, debug: bool = Body(False, embed=True)):   # embed=True → {"debug": true}
    ...
```

### 4.4 Pydantic 模型（v2）

```python
from pydantic import BaseModel, Field, field_validator, ConfigDict

class AskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(5, ge=1, le=20)
    session_id: str | None = None

    @field_validator("question")
    @classmethod
    def strip_q(cls, v: str) -> str:
        return v.strip()

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)   # 允许从 ORM 对象直接转
    id: int
    name: str
```

| v1 写法（旧教程常见） | v2 写法（现在用） |
|---|---|
| `class Config: orm_mode = True` | `model_config = ConfigDict(from_attributes=True)` |
| `.dict()` / `.json()` | `.model_dump()` / `.model_dump_json()` |
| `@validator` | `@field_validator` |
| `parse_obj()` | `model_validate()` |

> ⚠️ 你看的很多 2024 年教程还是 v1 语法，直接抄会报错。**先 `pip show pydantic` 看版本。**

### 4.5 422 到底在说什么

```json
{"detail":[{"type":"missing","loc":["body","question"],"msg":"Field required","input":{}}]}
```

- `loc` = 出错位置：`["body","question"]` 表示 body 里缺 `question`；`["query","limit"]` 表示查询参数不对。
- **排查顺序：先看 loc 定位字段，再看 type 判断是缺失/类型错/超范围。** 这是 Step 8 明确点名的坑。

### 4.6 依赖注入（Depends）

```python
async def get_db() -> AsyncSession:          # yield 依赖：请求结束自动关闭
    async with SessionLocal() as s:
        yield s

async def get_current_user(token: str = Depends(oauth2_scheme),
                            db: AsyncSession = Depends(get_db)) -> User:
    ...

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user
```

- 用途四连：**取数据库会话、取当前用户、取配置、取公共查询参数**。
- 依赖可以层层嵌套（`get_current_user` 依赖 `get_db`），并且有缓存（同一请求内同参数只算一次）。
- `yield` 依赖的清理代码在响应发出后执行 —— 适合 session、临时文件。

### 4.7 数据库：SQLAlchemy 2.0 + Alembic

```python
engine = create_async_engine(DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")
```

- 三种关系：**一对一**（外键 + `unique` + `uselist=False`）、**一对多**（默认）、**多对多**（中间关联表 `Table`）。
- 迁移：`alembic revision --autogenerate -m "add kb tables"` → `alembic upgrade head`。
- **改模型必须走迁移**，直接手改数据库会在换环境时爆炸（第 1 课和第 3 课都强调）。

### 4.8 JWT 登录链路

```python
payload = {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(hours=2)}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

链路：**注册（唯一性校验 + bcrypt 哈希）→ 登录（比对哈希 → 签发 token）→ 请求带 `Authorization: Bearer xxx` → 依赖解析 → current_user**。

- 密码永远不存明文，也**不要用 md5/sha1**。
- `exp` 必须要有；敏感操作可加 refresh token。
- 权限：在路由上加 `Depends(require_role("admin"))`，别在前端藏按钮就算完。

### 4.9 异步陷阱（高频踩坑）

| 错误写法 | 后果 | 正确做法 |
|---|---|---|
| `async def` 里 `requests.get()` | 阻塞事件循环，并发全挂 | `httpx.AsyncClient` |
| `async def` 里同步 `OpenAI()` | 同上，流式更明显 | `AsyncOpenAI` |
| `async def` 里 `time.sleep()` | 卡死所有请求 | `await asyncio.sleep()` |
| 同步 CPU 密集（本地 embedding） | 卡死 | `await run_in_threadpool(fn)` 或写成普通 `def` 路由（FastAPI 会丢线程池） |

### 4.10 流式输出（SSE）

```python
from fastapi.responses import StreamingResponse

async def gen():
    async for chunk in llm_stream(q):
        yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"

return StreamingResponse(gen(), media_type="text/event-stream",
                         headers={"Cache-Control": "no-cache",
                                  "X-Accel-Buffering": "no"})
```

- SSE 格式**必须**是 `data: xxx` + **两个换行**；前端用 `EventSource` 或 fetch + ReadableStream。
- `X-Accel-Buffering: no` 防 nginx 缓冲——不加的话"流式"会变成一次性返回（这是部署后最常见的"本地好好的，上线不流"原因）。
- 加心跳（长时间无输出发注释行）防代理超时。

### 4.11 其他必会的零碎

| 主题 | 要点 |
|---|---|
| 统一响应 | `{"code":0,"msg":"ok","data":...}` + `@app.exception_handler` 兜底 |
| 全局异常 | 自定义 `BusinessException`，统一转成 HTTP 200 + code≠0 或 4xx |
| 文件上传 | `UploadFile`，校验大小/后缀，按 md5 命名防重 |
| 静态文件 | `app.mount("/static", StaticFiles(directory="static"), name="static")` |
| CORS | `CORSMiddleware(allow_origins=[...])`，前后端分离必配 |
| 生命周期 | `lifespan` 里加载 embedding 模型 / 建连接池，别每次请求都加载 |
| 后台任务 | `BackgroundTasks` 做索引构建，接口先返回"任务已提交" |

### 4.12 面试会怎么问

- `Depends` 和普通函数调用有什么区别？（可复用、可覆盖（测试时 `dependency_overrides`）、可嵌套、有缓存）
- 为什么 FastAPI 快？（ASGI 异步 + Starlette + Pydantic v2 的 Rust 核心）
- 你项目里怎么处理模型调用超时和 429？（超时参数 + 指数退避重试 + 降级返回）

---

## 5. 第 2 课 · 业务系统 + AI 助手（实验室预约，27 集）

**一句话**：这门课的价值不在"预约系统"，而在**它把 AI 能力嵌进了一个有登录、有权限、有数据库的真实系统**。

### 5.1 工程分层（照这个结构抄，别写单文件）

```
app/
├── main.py            # 创建 app、挂中间件、include_router、lifespan
├── core/              # config.py（pydantic-settings）、security.py（JWT/哈希）
├── models/            # SQLAlchemy ORM
├── schemas/           # Pydantic 出入参
├── routers/           # 路由层：只做参数校验与转发
├── services/          # 业务层：真正的逻辑在这里
├── utils/             # 响应封装、异常、工具
└── static/ uploads/   # 静态资源
```

> 分层核心：**router 不写业务，service 不碰 HTTP**。面试问"你怎么组织代码"，答这个结构。

### 5.2 从 0 到 1 的顺序（课里的顺序，也是你自己项目的顺序）

1. 后端工程脚手架 → 2. 登录接口 → 3. JWT → 4. 统一响应 + 全局异常 → 5. 前端 axios 封装 + 联调 → 6. 注册 → 7. 文件上传 → 8. 用户 CRUD → 9. 业务实体（实验室/设备）→ 10. 预约流程（状态机）→ 11. AI 助手 → 12. RAG 接知识库 → 13. Tool Calling → 14. LangGraph Agent → 15. SSE 过程可见。

**注意第 4 步**：统一响应和全局异常要在写业务之前定死，否则后面改一遍要改几百处。

### 5.3 预约状态机（业务逻辑的考点）

```
待审核 ──通过──> 已通过 ──开始──> 使用中 ──结束──> 已完成
   │                 │
    └──拒绝──> 已拒绝   └──取消──> 已取消
```

- **冲突检测**：同一实验室、时间段重叠则拒绝。SQL 里用 `start < new_end AND end > new_start` 判断重叠（不是 `between`，这是经典错误）。
- 状态流转要有非法转移保护（已完成不能再取消）。
- 面试加分：**并发下两人同时抢同一时段**——用唯一约束 / 行锁 / 乐观锁。

### 5.4 会话与消息（AI 助手的存储设计）

```
chat_session(id, user_id, title, created_at, updated_at)
chat_message(id, session_id, role, content, created_at, tokens)
```

- 两表结构 + 按 `session_id` 取历史 → 重建上下文。
- **上下文不能无限拼**：滑窗（保留最近 N 轮）或摘要（早期对话压缩成一句）。
- 会话标题自动生成（首条问题摘要）是提升体验的小技巧。

### 5.5 Tool Calling（先手写，别一开始就上框架）

```python
tools = [{
    "type": "function",
    "function": {
        "name": "query_free_rooms",
        "description": "查询某天某个时段可用的实验室",
        "parameters": {"type": "object",
                       "properties": {"date": {"type": "string"},
                                      "start": {"type": "string"},
                                      "end": {"type": "string"}},
                       "required": ["date", "start", "end"]},
    },
}]
```

循环：**模型返回 tool_calls → 你执行函数 → 把结果作为 `role="tool"` 消息塞回去 → 再请求模型 → 直到模型不再调用工具**。

- 必须加：**最大轮次熔断**（比如 5 轮）、异常兜底、工具结果截断、参数校验。
- 工具描述（description）写得好不好，直接决定模型选不选对工具 —— 这就是 Prompt 工程。

### 5.6 LangGraph（状态机式 Agent）

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]

g = StateGraph(State)
g.add_node("agent", call_model)
g.add_node("tools", ToolNode(tools))
g.add_edge(START, "agent")
g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
g.add_edge("tools", "agent")
app = g.compile(checkpointer=MemorySaver())

app.invoke({"messages": [("user", "帮我约明天下午 3 点的实验室")]},
           config={"configurable": {"thread_id": user_id}})   # thread_id = 会话隔离
```

| 概念 | 一句话 |
|---|---|
| State | 全局共享的"黑板"，节点读它写它 |
| Node | 一个函数：`state -> 局部更新` |
| Edge / 条件边 | 控制流转，条件边 = if/else 路由 |
| Checkpointer | 持久化状态，`thread_id` 区分用户/会话 |
| interrupt | 人工介入（human-in-the-loop）：先停下等人确认再继续 |

**为什么用图而不是链**：链是线性的，Agent 需要**循环 + 分支 + 可恢复**，图天然表达这些。

### 5.7 SSE 让过程可见

推送的事件不要只有 token：

```json
{"type":"stage","stage":"retrieving"}
{"type":"tool","name":"query_free_rooms","args":{...},"result":"..."}
{"type":"delta","content":"明天下午"}
{"type":"done","citations":[...]}
```

> 前端把 stage 渲染成"正在检索知识库…"——**可观测性既是体验，也是面试时的工程感**。

### 5.8 面试会怎么问

- 你的 Agent 会不会死循环？怎么防？（轮次上限 + 状态检测 + 工具报错回填）
- `thread_id` 和 `user_id` 的关系？（一个用户多个会话 → thread_id 用 session_id）
- RAG 接进业务系统后，权限怎么管？（检索时按 user_id 过滤 metadata，别只在前端过滤）

---

## 6. 第 3 课 · Milvus + RAG 工程化（【RAG】01-20）

**一句话**：这门课补的是 **"向量库不是 Chroma 就完事"**——真实项目里还有稀疏检索、混合排序、服务器部署。

### 6.1 离线 / 在线两条流水线

```
离线（建库，可慢）：文档 → 解析 → 清洗 → 结构化切分 → 稠密+稀疏向量化 → 建索引 → 入库
在线（问答，要快）：query → （改写）→ 稠密召回 + 稀疏召回 → 融合 → rerank → 拼 Prompt → 生成 → 出处
```

### 6.2 Milvus 部署三形态

| 形态 | 启动方式 | 适用 |
|---|---|---|
| **Milvus Lite** | `MilvusClient(uri="./milvus.db")`，纯 pip | 本地开发、原型、单机小数据 |
| **Standalone** | docker-compose（etcd + MinIO + milvus） | 单机生产、测试环境 |
| **Distributed** | K8s | 亿级向量 |

> 开发期用 Lite，代码不变；上服务器换 `uri="http://ip:19530"` 即可 —— 这就是它比 SQLite 版 Chroma 更"生产友好"的地方。

### 6.3 核心概念对照

| Milvus | 类比 | 说明 |
|---|---|---|
| Collection | 表 | 一组同构向量 + 标量字段 |
| Schema | 表结构 | 字段名/类型/维度/metric_type |
| Primary key | 主键 | 常用 VARCHAR(业务 id) 或自增 int64 |
| Partition | 分区 | 按租户/日期切，缩小检索范围 |
| Segment | 段 | 存储与索引的基本单位（面试爱问） |
| Index | 索引 | HNSW / IVF_FLAT / DISKANN / SPARSE_INVERTED_INDEX |
| Alias | 别名 | 指向 collection，支持零停机切换重建 |

### 6.4 建库标准写法（Lite/Standalone 通用）

```python
from pymilvus import MilvusClient, DataType

client = MilvusClient(uri="./milvus_kb.db")

schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
schema.add_field("id",     DataType.VARCHAR, is_primary=True, max_length=64)
schema.add_field("text",   DataType.VARCHAR, max_length=8000)
schema.add_field("dense",  DataType.FLOAT_VECTOR, dim=1024)      # bge-large / 百炼 v4
schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)          # BM25 权重
schema.add_field("source", DataType.VARCHAR, max_length=512)      # 出处：文件名
schema.add_field("page",   DataType.INT32)                        # 出处：页码

idx = client.prepare_index_params()
idx.add_index(field_name="dense",  index_type="HNSW", metric_type="COSINE",
              params={"M": 16, "efConstruction": 200})
idx.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")

client.create_collection("kb", schema=schema, index_params=idx)
```

**必须记住的三个坑**：
1. 换 embedding 模型 → **维度变了，旧 collection 作废，必须重建**（参考你项目里 `EMBED_DIM` 校验的做法）。
2. `metric_type` 建库时定死，检索时必须一致。
3. `max_length` 按**字节**算，中文一个字 3 字节——`max_length=2000` 只够约 660 个汉字。

### 6.5 相似度度量

| metric | 含义 | 什么时候用 |
|---|---|---|
| L2 | 欧氏距离，越小越近 | 未归一化向量 |
| IP | 内积，越大越近 | **向量已归一化**（此时 IP ≡ COSINE，且更快） |
| COSINE | 余弦相似度 | 文本 embedding 默认 |

### 6.6 PDF 解析：基础 vs 高级

| | 简单解析（pypdf） | 高级解析（unstructured） |
|---|---|---|
| 依赖 | 纯 Python | 需要 `poppler` / `tesseract` / `libmagic`，体积大 |
| 能处理 | 文字版 PDF | 双栏、表格、图片、扫描件（OCR） |
| 输出 | 纯文本，**顺序易乱、表格易丢** | 带元素类型（Title / Table / NarrativeText） |
| 部署 | 本地即可 | **建议单独部署到服务器**，主服务只调 API |

- **策略**：先用 pypdf 跑通，抽检 20 页质量；表格多/扫描件再上 unstructured。别一上来就装 2GB 依赖。
- 服务器装 HuggingFace 模型慢 → 配镜像：`HF_ENDPOINT=https://hf-mirror.com`（课程第 08 集专门讲这个，国内必踩）。

### 6.7 结构化切分（这门课最值钱的一段）

1. **按标题层级拆**：Markdown `#/##/###` 解析成块，每个块带上**标题路径**（`第3章 > 3.2 部署 > 环境要求`）写进 metadata。
2. **合并标题 Document**：标题和紧跟的正文合并成一个语义单元，否则会检索出**一个孤零零的标题**——模型拿到"3.2 部署"四个字什么也答不出。
3. **语义切分**：句子间算相似度，**在相似度骤降处断开**，比固定 500 字更贴合语义边界。
4. 每个 chunk 的 metadata 至少保留：`source / page / section / chunk_id / hash`。

> 面试原题："你为什么这么切？"——用第 3 点的实验数据回答，别答"网上说 500"。

### 6.8 稠密 + 稀疏（HyDE 之外的必会项）

| | 稠密向量（BGE-Large） | 稀疏向量（BM25） |
|---|---|---|
| 表示 | 1024 维语义 | 词 → 权重（维度=词表大小，绝大多数为 0） |
| 强项 | 近义、改写、跨表述 | 专有名词、编号、代码、人名 |
| 弱项 | 精确匹配差 | 不懂同义 |
| 存储 | FLOAT_VECTOR | SPARSE_FLOAT_VECTOR |

**所以必须混合检索**：两路各召回 top-N，再融合。

### 6.9 融合：RRF 与加权

```python
score(d) = Σ_i  1 / (k + rank_i(d))        # k 常取 60，只看名次，不看原始分数
```

- **RRF 的好处**：稠密分数（余弦 0~1）和稀疏分数（BM25 无上界）量纲不同，直接加权要归一化；**RRF 只用排名，天然免归一化**，是最稳的默认选择。
- 加权融合需要先做 min-max 归一化，调权重（0.7 稠密 + 0.3 稀疏）——**要跑评估才能定**。

Milvus 混合检索：
```python
from pymilvus import AnnSearchRequest, RRFRanker

reqs = [
    AnnSearchRequest(data=[q_dense],  anns_field="dense",  param={"metric_type": "COSINE", "params": {"ef": 64}}, limit=20),
    AnnSearchRequest(data=[q_sparse], anns_field="sparse", param={"metric_type": "IP"},                                     limit=20),
]
res = client.hybrid_search("kb", reqs, ranker=RRFRanker(60), limit=10,
                           output_fields=["text", "source", "page"])
```

### 6.10 索引参数速查

| 索引 | 关键参数 | 特点 |
|---|---|---|
| HNSW | `M`（每层连接数, 16~64）、`efConstruction`（建索引）、`ef`（检索时，越大越准越慢） | 综合最好，内存占用高，**默认选它** |
| IVF_FLAT | `nlist`（聚类数）、`nprobe`（探测数） | 内存友好，要调 nprobe |
| DISKANN | — | 超大数据 + 内存不够 |
| SPARSE_INVERTED_INDEX | — | 稀疏倒排 |

> 一句话答面试：**ef / nprobe 是"精度-延迟旋钮"，调大召回高但慢。**

### 6.11 面试会怎么问

- 为什么要有 rerank？（见第 0 课）
- Milvus 和 Chroma 的区别？（分布式/索引类型/稀疏支持/部署形态）
- 十亿向量怎么优化？（分区、索引选型、标量过滤、量化、分片）
- 你怎么评估检索效果？（构造 QA 集，测 recall@k / MRR，改一个变量跑一次）

---

## 7. 第 4 课 · MCP（8 集）

**一句话**：MCP 是**模型 ↔ 工具/数据**之间的标准协议，把"每家客户端各写一套集成"变成"写一次 Server，所有客户端都能用"。

### 7.1 为什么需要它

```
没有 MCP：N 个客户端 × M 个工具 = N×M 套集成代码
有了 MCP：N 个客户端 + M 个 Server  = N+M
```
类比：**USB-C 之于外设**。Claude Desktop、Cursor、各种 IDE 都支持。

### 7.2 架构三层

| 角色 | 是什么 | 例子 |
|---|---|---|
| Host | 宿主应用，管用户与权限 | Claude Desktop、你的 Agent 后端 |
| Client | 与某个 Server 的 1:1 连接 | SDK 里的 `ClientSession` |
| Server | 提供工具/资源/提示词 | 你写的课表查询服务 |

### 7.3 原语（高频考点）

| 服务端提供 | 含义 |
|---|---|
| **Tools** | 可被模型调用的函数（有副作用） |
| **Resources** | 可读取的数据（文件、表、URL），由用户/应用选择 |
| **Prompts** | 可复用的提示词模板 |

| 客户端提供 | 含义 |
|---|---|
| Sampling | 让服务端"反向"请求宿主的大模型 |
| Roots | 告知服务端可访问的目录边界 |
| Elicitation | 服务端向用户追问补充信息 |

### 7.4 传输方式

| 传输 | 场景 | 说明 |
|---|---|---|
| **stdio** | 本地进程 | 宿主启动子进程，走标准输入输出，最简单 |
| **Streamable HTTP** | 远程/多用户 | 走 HTTP，可带鉴权头；早期的 SSE 传输已被它取代 |

### 7.5 握手协议（理解这个就懂 MCP 了）

```
1. initialize          客户端↔服务端交换 protocolVersion / capabilities
2. initialized 通知
3. tools/list          拿到工具清单（name + description + inputSchema）
4. tools/call          传参执行，返回 content（文本/图片/资源引用）
```

> **Schema 是自动生成的**：FastMCP 从函数签名和类型注解生成 JSON Schema，从 docstring 生成 description —— 所以**类型注解和文档字符串写不好，模型就不会用你的工具**。

### 7.6 写一个 Server（FastMCP）

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("campus-tools")

@mcp.tool()
def query_timetable(student_id: str, week: int = 1) -> list[dict]:
    """查询某学生某一周的课表。week 为第几教学周，从 1 开始。"""
    return db.query(...)

@mcp.tool()
def query_free_rooms(date: str, start: str, end: str) -> list[dict]:
    """查询指定日期时段内空闲的实验室。date 格式 YYYY-MM-DD。"""
    ...

if __name__ == "__main__":
    mcp.run()                            # stdio
    # mcp.run(transport="streamable-http")  # 远程，可配 JWT
```

本课第 06 集做的就是这件事（FastMCP 课表查询工具）。

### 7.7 写一个 Client（接到自己的 Agent 上）

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(URL, headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
    async with ClientSession(r, w) as s:
        await s.initialize()
        tools  = await s.list_tools()                  # 转成 OpenAI tools 格式
        result = await s.call_tool("query_timetable", {"student_id": "2023001", "week": 3})
```

- 把 `tools` 的 `inputSchema` 直接塞进 `function.parameters`，**MCP 工具就变成了 function calling 工具**——这就是"结合 Agent"的全部秘密。

### 7.8 JWT 转发（本课第 07 集，差异化亮点）

问题：Agent 后端有用户身份，MCP Server 是另一个服务，怎么知道"这次调用是哪个用户"？

方案：**Host 把用户 token 放进 HTTP Header → MCP Server 中间件校验 → 注入当前用户上下文 → 工具内按 user_id 过滤数据**。

> 不做的后果：任何人都能查别人课表（越权）。面试问"你的 MCP 安全怎么做的"，答这一段。

### 7.9 ReAct vs Function Calling

| | Function Calling | ReAct |
|---|---|---|
| 形态 | 结构化输出决定调用 | Thought → Action → Observation 文本循环 |
| 依赖 | 模型原生支持 tools | 提示词驱动，任何模型可近似实现 |
| 稳定性 | 高（有 schema） | 依赖模型能力，易跑偏 |

本课第 08 集用 ReAct 串起对话；工程上**优先用原生 function calling**，ReAct 作为兜底/教学理解。

### 7.10 面试会怎么问

- MCP 和 function calling 是什么关系？（不同层：一个是**协议/传输与能力发现**，一个是**模型输出格式**；MCP 工具最终转成 FC 工具）
- 为什么 MCP 会火？（生态解耦，工具可复用；一次编写，多客户端可用）
- MCP Server 怎么防止工具被滥用？（鉴权、最小权限、参数校验、超时、白名单）

---

## 8. 五门课 → 你的项目：对照表

| 手册 Step | 要做的事 | 看哪门课的哪段 |
|---|---|---|
| Step 8-9 | FastAPI + 流式 + 错误处理 | 第 1 课 04-18；第 2 课 04-07、25 |
| Step 13-15 | 选题、解析、切分 | 第 3 课 05-13 |
| Step 16 | Embedding + 向量库 | 第 3 课 14-19 |
| Step 17 | 检索→生成闭环 | 第 2 课 22；第 3 课 20 |
| Step 18 | 混合检索 + Rerank + 改写 | 第 3 课 14-16；备用课 `BV14ap461EXQ` 177-186 |
| Step 19 | 评估 | 无课覆盖 → 自己写脚本（RAGAS 或手写） |
| Step 21 | 手写 Function Calling | 第 2 课 23 |
| Step 22 | LangGraph | 第 2 课 24 |
| Step 23-25 | 记忆 / 稳定性 / HITL | 第 2 课 24-25 + 官方文档 |
| Step 26 | MCP Server | 第 4 课 06-08 |

> ⚠️ **五门课都没覆盖好的只有两件事：评估（Step 19）和"讲清取舍"**。这两块恰恰是面试区分度最高的地方，必须自己补。

---

## 9. 自测题库（30 题 · 先看题，再点答案）

> 用法：遮住答案，心里或纸上作答；答完点开对照。答错的题号记到文末"错题表"，3 天后重做。
> 难度：⭐ 基础记忆 · ⭐⭐ 需要理解 · ⭐⭐⭐ 需要项目经验

### 9.1 FastAPI（Q1-Q6）

**Q1 ⭐** FastAPI 依赖的 ASGI 服务器是什么？它和 Flask 用的 WSGI 最大区别在哪？

<details><summary><b>查看答案</b></summary>

**uvicorn**（也可以 uvicorn + gunicorn 多进程）。

- WSGI：同步、调用阻塞、一个请求占一个线程，并发靠线程数。
- ASGI：原生异步（`async/await`），单线程事件循环处理大量并发 I/O；还支持 WebSocket、SSE 长连接。

**关键推论**：ASGI 里一旦有同步阻塞调用（`requests`、同步 `OpenAI`、`time.sleep`），整个事件循环会停摆——这是第 1 课反复强调的坑。

</details>

**Q2 ⭐** 什么情况下会返回 422？给出一个 422 响应体并解释 `loc` 的含义。

<details><summary><b>查看答案</b></summary>

**请求参数校验失败**时（缺字段、类型不对、超出 `gt/le/max_length` 约束）。

```json
{"detail":[{"type":"missing","loc":["body","question"],"msg":"Field required","input":{}}]}
```

`loc` 是错误位置路径：第一段是**来源**（`body` / `query` / `path` / `header`），后面是**字段名**（嵌套模型会继续往下）。先看 loc 定位字段，再看 type 判断是缺失 / 类型错 / 超范围。

</details>

**Q3 ⭐⭐** `Depends` 用 `yield` 写和直接 `return` 写，区别是什么？举一个必须用 `yield` 的场景。

<details><summary><b>查看答案</b></summary>

- `return`：函数执行完就结束。
- `yield`：**yield 之前是"准备"，yield 之后是"清理"**，清理代码在**响应发送完成后**执行。

必须用 yield 的场景：**数据库会话**（`async with SessionLocal() as s: yield s`），保证请求结束一定 close；同理还有临时文件、锁、连接池借出。

补充：同一请求内相同参数的依赖会被缓存，只执行一次。

</details>

**Q4 ⭐⭐** 为什么不能在 `async def` 路由里调用同步的 `openai.OpenAI().chat.completions.create()`？怎么改？

<details><summary><b>查看答案</b></summary>

同步客户端内部是阻塞的 HTTP 调用，会**占住事件循环**，导致其他请求全部排队等待——并发数一上来就"整体变慢"，流式场景更明显。

改法（任选）：
1. 用 `AsyncOpenAI` + `await client.chat.completions.create(...)`（首选）。
2. `await run_in_threadpool(fn)` 或 `asyncio.to_thread(fn)`。
3. 把路由写成普通 `def`，FastAPI 会自动丢进线程池（但这样就失去了异步带来的并发优势，只适合 CPU 密集的短任务）。

</details>

**Q5 ⭐⭐** 实现 SSE 流式的三个必做细节是什么？

<details><summary><b>查看答案</b></summary>

1. **格式**：每行 `data: xxx`，**空行分隔**（`\n\n`），结束发 `data: [DONE]`；`media_type="text/event-stream"`。
2. **禁用缓冲**：响应头 `X-Accel-Buffering: no`（nginx 会默认缓冲，导致"本地流式、线上一次性返回"），必要时加 `Cache-Control: no-cache`。
3. **保活与错误**：长时间无输出发心跳注释行防代理超时；生成过程中抛异常要在流内发一条 error 事件，而不是让连接直接断。

</details>

**Q6 ⭐⭐** JWT 登录链路的完整步骤，以及"密码该怎么做"和"token 里放什么"。

<details><summary><b>查看答案</b></summary>

链路：**注册（唯一性校验 → 用 bcrypt 哈希存密码）→ 登录（按用户名查用户 → 校验哈希 → 签发 token）→ 客户端带 `Authorization: Bearer <token>` → 依赖里解码并校验 `exp` → 取出 user_id 查库 → 注入 `current_user`**。

- 密码：只存哈希（bcrypt/argon2），**永不存明文，也不用 md5/sha1**。
- payload：`sub`（用户 id）+ `exp`（过期时间），可以放角色；**不要放敏感信息**（JWT 只是 base64，不是加密）。
- 权限校验必须放在**后端路由依赖**上，前端隐藏按钮不算权限控制。

</details>

### 9.2 业务系统 & Agent（Q7-Q12）

**Q7 ⭐** 一个 FastAPI 项目里，`router / service / model / schema` 各自该放什么？为什么不能写在一个文件里？

<details><summary><b>查看答案</b></summary>

- **router**：HTTP 层，只管收参、校验、调用 service、返回；不写业务逻辑。
- **service**：业务逻辑（预约冲突检测、调用模型、检索）；不依赖 HTTP，可被 CLI/测试直接调用。
- **model**：SQLAlchemy ORM，数据库表结构。
- **schema**：Pydantic 出入参，接口契约（和对外的数据形状），和 ORM 解耦。

好处：**可测试**（service 不用起 HTTP）、**可替换**（换数据库不动路由）、**可协作**。单文件写到 800 行后，改一个字段要翻半小时。

</details>

**Q8 ⭐⭐** 预约系统里判断"时间段冲突"的 SQL 条件怎么写？为什么不能用 `BETWEEN`？

<details><summary><b>查看答案</b></summary>

```sql
WHERE room_id = :room
  AND start_time < :new_end
  AND end_time   > :new_start
```

即"**已有开始早于新结束，且已有结束晚于新开始**"→ 必相交。这样能覆盖"包含、被包含、左交、右交"四种重叠。

`BETWEEN` 只能判断"点落在区间内"，漏掉"新区间完全包住旧区间"的情况。

加分：并发抢同一时段要加**唯一约束/行锁/乐观锁**，否则检测通过后仍会双写。

</details>

**Q9 ⭐⭐** 手写 Function Calling 的循环，必须加哪三个保护？

<details><summary><b>查看答案</b></summary>

循环：模型返回 `tool_calls` → 执行 → 结果以 `role="tool"` 消息回填 → 再次请求 → 直到不再调用工具。

三个保护：
1. **最大轮次熔断**（如 5 轮），防止模型反复调用同一工具死循环。
2. **工具异常兜底**：工具报错不能抛穿整个请求，要把错误信息作为工具结果返回给模型，让它自我修正。
3. **参数校验 + 结果截断**：模型可能给出非法参数（不存在的 date 格式），执行前用 Pydantic 校验；工具返回过长要截断，防止爆上下文。

（进阶：工具白名单、超时、幂等、日志追踪。）

</details>

**Q10 ⭐⭐** LangGraph 里 State、Node、条件边、checkpointer 分别解决什么问题？`thread_id` 用来干什么？

<details><summary><b>查看答案</b></summary>

- **State**：全局共享状态（黑板上写 `messages`、`retrieved`、`tool_result`），节点只返回局部更新，框架负责合并（`Annotated[list, add_messages]` 决定合并方式）。
- **Node**：一个函数，输入 state、输出局部更新，是"一步动作"。
- **条件边**：根据 state 决定下一步去哪（要不要调工具、要不要检索），实现**分支 + 循环**。
- **checkpointer**：把每步状态持久化，支持中断恢复、重放、人工介入（interrupt）。
- **thread_id**：checkpointer 的索引键，**一个会话一个 thread_id**，用来隔离不同用户/会话的历史。

为什么用图不用链：链是线性的，Agent 需要**循环和分支**，图上天然能表达。

</details>

**Q11 ⭐⭐** 通义/OpenAI 的流式接口怎么做到"让用户看到 Agent 在干什么"，而不是干等？

<details><summary><b>查看答案</b></summary>

在 SSE 里推**多种事件类型**，而不是只推 token：

```json
{"type":"stage","stage":"retrieving"}
{"type":"tool","name":"query_free_rooms","args":{...}}
{"type":"tool_result","name":"query_free_rooms","summary":"找到 3 间"}
{"type":"delta","content":"明天下午"}
{"type":"done","citations":[{"source":"实验室管理办法.pdf","page":12}]}
```

前端按 type 分别渲染成状态条 / 工具卡片 / 打字机 / 出处列表。**这既是体验，也是可观测性**（出问题能看到卡在哪一步）。

</details>

**Q12 ⭐⭐⭐** RAG 接进业务系统后，权限怎么保证"用户只检索到自己有权限的文档"？

<details><summary><b>查看答案</b></summary>

**在检索层过滤，而不是在生成后过滤，更不是在前端过滤。**

做法：
1. 入库时把 `owner_id / dept_id / visibility` 写进向量库的标量字段（metadata）。
2. 检索时带上过滤条件：Milvus `filter='dept_id == "研发部"'`，或 Chroma `where={"dept": "研发"}`。
3. 生成后还要做**引用校验**：把答案里的引用与检索结果比对，防止模型编造来源。

⚠️ 常见错误：先检索全库再由模型"别说出去"——那是提示词层面的君子协定，越权数据已经进了上下文。

</details>

### 9.3 向量库 & RAG 工程化（Q13-Q20）

**Q13 ⭐** Milvus 的 Collection / Segment / Partition / Alias 分别是什么？

<details><summary><b>查看答案</b></summary>

- **Collection**：一张"表"，装一组同构的向量 + 标量字段。
- **Segment**：存储与索引的**基本单位**，数据按批写入、压缩合并；检索时查的是 segment 上的索引（面试爱问，因为它解释"为什么刚插入的数据要等一会才能查到"）。
- **Partition**：Collection 内的逻辑分区，检索可限定分区，**缩小搜索范围**（常用于按租户/日期隔离）。
- **Alias**：指向 Collection 的别名，重建索引时**先建新 collection 再切别名**，实现零停机。

</details>

**Q14 ⭐** L2、IP、COSINE 有什么区别？什么时候 IP 等于 COSINE？

<details><summary><b>查看答案</b></summary>

- **L2**：欧氏距离，越小越相似。受向量长度影响。
- **IP**：内积，越大越相似，受长度影响大。
- **COSINE**：夹角余弦，**只看方向不看长度**，范围 [-1,1]。

**向量做 L2 归一化后**（`v / ||v||`），`IP = COSINE`，且计算更快（省一次除法）。文本 embedding 通常已归一化，所以很多库默认用 IP。

</details>

**Q15 ⭐⭐** 为什么要做"稠密 + 稀疏"混合检索？只用一个会出什么问题？

<details><summary><b>查看答案</b></summary>

- 纯稠密：语义近义强，但**专有名词、型号、编号、代码片段、人名**匹配弱（`HNSW-16`、`BGE-Large` 这种 token 很难靠语义命中）。
- 纯稀疏（BM25）：精确匹配强，但**同义改写、口语化提问**完全失效（问"怎么部署"搜不到"安装步骤"）。

混合后：稀疏兜住"精确词"，稠密兜住"换个说法"。再叠 rerank 精排，一般能显著提召回。

**注意**：加了就要测，否则不知道到底提了多少。

</details>

**Q16 ⭐⭐** RRF（Reciprocal Rank Fusion）为什么比"加权求分数"更常用？

<details><summary><b>查看答案</b></summary>

公式：`score(d) = Σ 1/(k + rank_i(d))`，k 常取 60。

原因：**稠密分数（余弦 0~1）和稀疏分数（BM25 无上界）量纲完全不同**，直接加权必须做归一化，而归一化方式（min-max / z-score）又会引入新的超参和偏差。

RRF **只用排名**，天然免疫量纲问题，几乎不需要调参，鲁棒性好——所以是默认首选。要精细控制权重时才退回"归一化 + 加权"，且必须用评估集定权重。

</details>

**Q17 ⭐⭐** HNSW 的 `M`、`efConstruction`、`ef` 分别影响什么？

<details><summary><b>查看答案</b></summary>

- `M`：每个节点在每层的最大连接数（16~64）。**越大越准、内存越大**。
- `efConstruction`：建索引时候选池大小。**越大索引质量越好，构建越慢**（只影响构建）。
- `ef`：**检索时**的候选池大小（≥ top_k）。**越大召回越高、延迟越高**——这是线上唯一可以动态调的旋钮。

一句话：前两个在建库时定，第三个决定"精度-延迟"权衡。

</details>

**Q18 ⭐⭐** 解析 PDF 时用 pypdf 抽出来的文本顺序错乱、表格丢失，你会怎么处理？

<details><summary><b>查看答案</b></summary>

分级处理：
1. **先抽检**：抽 20 页人工看，确认是"排版复杂"还是"扫描件"。
2. **排版复杂**（双栏、表格）→ 换 `unstructured` 的 `hi_res`（layout 分析，能识别 Title/Table/NarrativeText），需要 poppler、tesseract、detectron2 等依赖，**建议独立部署成解析服务**，主服务调 HTTP。
3. **扫描件** → OCR（`tesseract` / PaddleOCR），并在 metadata 标记 `ocr=True`（OCR 文本错误率高，评估时要单独看）。
4. **表格** → 单独转成 Markdown 表格再切块，别让它变成一串错位的数字。
5. **兜底**：解析失败的文档进"待人工处理"队列，别静默丢。

</details>

**Q19 ⭐⭐⭐** 为什么要把"标题 Document"和正文合并？语义切分和固定长度切分各自的取舍？

<details><summary><b>查看答案</b></summary>

**合并标题**：如果只把标题单独成一个 chunk，检索时可能命中一个孤零零的"3.2 部署"——模型拿到 4 个字什么都答不出。合并后语义完整；同时把**标题路径**（`第3章 > 3.2 部署`）写进 metadata，检索命中时能给出上下文。

**固定长度切分**（500 字 + 50 重叠）：简单、可控、块大小均匀利于批处理；缺点是可能从句子中间切断，破坏语义。

**语义切分**：按句子向量相似度骤降处断开，边界更自然、检索命中率通常更好；缺点是**慢**（要算很多向量）、块大小不均、超参（阈值）需要调。

**结论**：先用结构（标题/段落）切，再在长段落内做语义或固定长度兜底；**用评估集证明哪个更好**，别凭感觉。

</details>

**Q20 ⭐⭐⭐** 你的 RAG 效果不好，给一个有优先级的排查顺序。

<details><summary><b>查看答案</b></summary>

**从后往前排、从便宜到贵排**：

1. **先看检索结果**（最容易被忽略）：把 top-k 片段打印出来，答案到底在不在里面？
   - 不在 → 检索问题（见 2）。
   - 在但答错 → 生成问题（Prompt 没约束"只依据资料"、上下文太长被淹没、模型太弱）。
2. **检索层**：切分是否切碎语义？embedding 是否适合中文/领域？是否缺关键词检索（专有名词）？是否有 rerank？filter 条件是否写错。
3. **数据层**：文档解析是否丢内容？知识库是否真的包含答案？是否重复/过时文档污染。
4. **Prompt 层**：是否给了出处要求、是否要求"不知道就说不知道"、检索片段是否带标题路径。
5. **评估层**：先建 50 条 QA 集，改一个变量跑一次，**别同时改三处**（否则不知道是哪一处起作用）。

一句话总结：**RAG 出问题，80% 在检索，15% 在切分，5% 在 Prompt。**

</details>

### 9.4 MCP（Q21-Q26）

**Q21 ⭐** MCP 解决的核心问题是什么？用一句话概括它的价值。

<details><summary><b>查看答案</b></summary>

**把"每个 AI 客户端 × 每个工具"的点对点集成（N×M），变成"客户端 + 标准 Server"（N+M）。**

一句话：**AI 世界的 USB-C**——工具写一次，所有支持 MCP 的宿主（Claude Desktop、Cursor、你的 Agent）都能用。

</details>

**Q22 ⭐⭐** MCP 的 Host / Client / Server 三层各是什么？stdio 和 Streamable HTTP 两种传输分别适合什么场景？

<details><summary><b>查看答案</b></summary>

- **Host**：宿主应用（管用户、管权限、管 UI），如 Claude Desktop、你的 Agent 后端。
- **Client**：Host 内部与某个 Server 的 **1:1 连接**，负责协议收发。
- **Server**：暴露 Tools / Resources / Prompts 的服务。

传输：
- **stdio**：本地子进程，用 stdin/stdout 通信，零网络配置，适合本地工具（读本地文件、查本地数据库）。
- **Streamable HTTP**：跨网络、多用户，可带 `Authorization` 头做鉴权，适合部署成服务的工具（本课第 07 集的 JWT 转发就靠它）。

</details>

**Q23 ⭐⭐** 服务端提供的三大原语是什么？Tools 和 Resources 的区别？

<details><summary><b>查看答案</b></summary>

**Tools / Resources / Prompts**。

- **Tools**：模型可调用的函数，**可能有副作用**（下单、写库），由模型决定何时调用。
- **Resources**：**只读**的数据（文件、表、URL），由应用/用户选择是否放进上下文，模型一般不主动"调用"。
- **Prompts**：可复用的提示词模板。

区别一句话：**Tools 是"做事"，Resources 是"给看"。**

</details>

**Q24 ⭐⭐** FastMCP 怎么把 Python 函数变成 MCP 工具？哪些信息会变成给模型看的描述？

<details><summary><b>查看答案</b></summary>

用 `@mcp.tool()` 装饰器 + 类型注解 + docstring：

```python
@mcp.tool()
def query_timetable(student_id: str, week: int = 1) -> list[dict]:
    """查询某学生某一周的课表。week 为第几教学周，从 1 开始。"""
```

- **函数名** → `name`
- **docstring** → `description`（模型靠它决定用不用这个工具，**要写清楚"什么时候用"**）
- **类型注解 + 默认值** → `inputSchema`（JSON Schema，含 required）
- **返回类型** → 结果序列化方式

**所以：类型注解偷懒、docstring 写"查询数据"这种废话，模型就会选错工具或用错参数。**

</details>

**Q25 ⭐⭐⭐** Agent 后端如何把用户身份透传到 MCP Server？不做的后果是什么？

<details><summary><b>查看答案</b></summary>

做法：**Host 建连时把用户 token 放进 HTTP Header（`Authorization: Bearer ...`）→ MCP Server 侧中间件校验并解析出 user_id → 注入到工具的执行上下文 → 工具内按 user_id 过滤数据。**

（stdio 模式没有 HTTP 头，通常靠环境变量或启动参数传身份，所以多用户场景更推荐 HTTP。）

不做的后果：**越权**——任何调用者都能查到别人的课表/成绩/工单。而且这种漏洞不会在功能测试里暴露，属于典型的安全缺陷。

</details>

**Q26 ⭐⭐⭐** MCP 的 Tools 和模型的 Function Calling 是什么关系？冲突吗？

<details><summary><b>查看答案</b></summary>

**不冲突，是两层东西**：

- **Function Calling** 是**模型的输出格式**：模型决定"我要调用名为 X 的函数，参数是 {...}"。
- **MCP** 是**应用侧的协议**：发现有哪些工具（`tools/list`）、怎么调用（`tools/call`）、走什么传输、怎么鉴权。

结合方式：**把 MCP 的 `tools/list` 结果转成 OpenAI 的 `tools` 数组**，模型发起调用后，由 Host 转成 `tools/call` 发给 MCP Server，结果再回填成 `role="tool"` 消息。

一句话：**MCP 负责"工具有哪些、怎么连"，FC 负责"模型说要调哪个"。**

</details>

### 9.5 综合（Q27-Q30）

**Q27 ⭐⭐** RAG 和微调（fine-tune）该怎么选？能不能一起用？

<details><summary><b>查看答案</b></summary>

- **知识频繁更新 / 需要溯源 / 私域文档多** → RAG（改数据不用重训，能给出处）。
- **风格、格式、语气、领域术语、固定输出结构** → 微调（让模型"会说话"，不擅长记事实）。
- **两者可叠加**：RAG 提供事实，微调让模型更会利用检索结果（例如微调"依据资料作答+引用"的行为）。

一句话：**RAG 管"知道什么"，微调管"怎么表达"。**

</details>

**Q28 ⭐⭐** chunk size 你怎么定？面试官追问"为什么"时，什么样的回答算合格？

<details><summary><b>查看答案</b></summary>
**不合格**："网上说 500 token + 50 overlap。"
**合格**：做过对照实验，有数据。

答法模板：
> 我先按结构切（标题/段落）保证语义完整；对长段落再做 300/500/800 三档对比，用同一份 50 条 QA 集测 `recall@5` 和答案准确率。结果是 500 字 + 10% 重叠在中文技术文档上召回最高；300 太碎导致上下文缺失，800 让单块混入多个主题、检索精度下降。

加分：说明你保留了标题路径和页码作为 metadata，让小块也能还原上下文（"小块检索、大块喂给模型"的 parent-document 策略）。

</details>

**Q29 ⭐⭐⭐** 面试官问"你这个项目哪里最难/你踩过最大的坑"，怎么答才不像背模板？

<details><summary><b>查看答案</b></summary>

结构：**现象 → 定位 → 方案对比 → 数据 → 遗留问题**。

反面示例："我用了 RAG，效果还不错。"

正面示例：
> 现象：上线后发现"问编号类问题（如 XX-2024 第 12 条）答不上来"。
> 定位：打印 top-5 检索结果，发现纯稠密检索根本没召回对应条文 —— 编号这类 token 语义区分度低。
> 方案：加了 BM25 稀疏召回 + RRF 融合，再叠 rerank；试过"只调大 top-k"，召回上去了但噪声也上去了，答案质量反而降。
> 数据：同类问题召回率从 62% → 89%，整体人工抽检准确率 +11 个点。
> 遗留：rerank 让 P95 延迟从 800ms 涨到 1.4s，正在试"只对 top-20 重排 + 缓存"。

**为什么这样答有效**：有失败尝试（说明你真的做了）、有数据（说明你会评估）、有遗留问题（说明你有工程判断，而不是"我这项目完美"）。

</details>

**Q30 ⭐⭐⭐** 只用一句话，说清楚"RAG 系统的瓶颈通常在哪"。

<details><summary><b>查看答案</b></summary>
**在检索，不在生成** —— 答不出来时，先确认"正确的片段有没有被召回"，而不是急着换更大的模型或改 Prompt。

（延伸：召回不到的原因又多在**解析丢内容**和**切分破坏语义**，所以真正该先修的是数据管线。）

</details>

---

## 10. 错题追踪表

| 题号 | 第一次 | 第二次（3 天后） | 第三次（1 周后） | 备注 |
|---|---|---|---|---|
| Q1 | ☐ | ☐ | ☐ | |
| Q2 | ☐ | ☐ | ☐ | |
| Q3 | ☐ | ☐ | ☐ | |
| Q4 | ☐ | ☐ | ☐ | |
| Q5 | ☐ | ☐ | ☐ | |
| Q6 | ☐ | ☐ | ☐ | |
| Q7 | ☐ | ☐ | ☐ | |
| Q8 | ☐ | ☐ | ☐ | |
| Q9 | ☐ | ☐ | ☐ | |
| Q10 | ☐ | ☐ | ☐ | |
| Q11 | ☐ | ☐ | ☐ | |
| Q12 | ☐ | ☐ | ☐ | |
| Q13 | ☐ | ☐ | ☐ | |
| Q14 | ☐ | ☐ | ☐ | |
| Q15 | ☐ | ☐ | ☐ | |
| Q16 | ☐ | ☐ | ☐ | |
| Q17 | ☐ | ☐ | ☐ | |
| Q18 | ☐ | ☐ | ☐ | |
| Q19 | ☐ | ☐ | ☐ | |
| Q20 | ☐ | ☐ | ☐ | |
| Q21 | ☐ | ☐ | ☐ | |
| Q22 | ☐ | ☐ | ☐ | |
| Q23 | ☐ | ☐ | ☐ | |
| Q24 | ☐ | ☐ | ☐ | |
| Q25 | ☐ | ☐ | ☐ | |
| Q26 | ☐ | ☐ | ☐ | |
| Q27 | ☐ | ☐ | ☐ | |
| Q28 | ☐ | ☐ | ☐ | |
| Q29 | ☐ | ☐ | ☐ | |
| Q30 | ☐ | ☐ | ☐ | |

**判定标准**：连续两次能**不看答案、用自己的话**讲清楚 → 这题可以划掉。只会"看着眼熟"→ 还不算会。

---

## 11. 附录

### 11.1 第 3 课【面试题】分 P 速查（不在正课里，但值得刷）

| 主题 | 对应分 P | 本文对应 |
|---|---|---|
| 五种主流大模型差异与选型 | 01-02 | — |
| Temperature 等五个参数 | 03-04 | — |
| 上下文窗口 / 有效长度 | 05-07 | — |
| Token 计数与超限处理 | 08-10 | — |
| 开源 vs 闭源、私有化部署评估 | 11-12 | — |
| Prompt → 上下文 → Harness 三阶段 | 13-15 | Q9 / Q10 |
| React 机制、workflow vs agent | 面试题 3-4 | 7.9 节 |
| MCP 如何与 Agent 结合 | 面试题 5 | Q26 |
| 多 Agent 优势、Skills 与 Multi-Agent 区别 | 面试题 6-7 | — |

### 11.2 一句话速记卡

| 概念 | 一句话 |
|---|---|
| ASGI | 异步 Web 协议，uvicorn 跑它 |
| 422 | 参数校验失败，`loc` 定位字段 |
| Depends yield | 响应后执行清理，用于 DB session |
| SSE | `data: xxx\n\n` + 关缓冲 |
| Tool Loop | 模型要工具 → 执行 → 回填 → 再问 |
| LangGraph | 图 + 状态 + 检查点，`thread_id` 隔离会话 |
| Milvus Segment | 存储与索引的基本单位 |
| 归一化后 | IP ≡ COSINE |
| 混合检索 | 稠密管语义，稀疏管关键词，RRF 融合 |
| ef / nprobe | 精度-延迟旋钮 |
| MCP | Host–Client–Server，Tools/Resources/Prompts |
| MCP + FC | 协议管发现，FC 管调用 |
| RAG 瓶颈 | 在检索，不在生成 |

---

> **最后一句**：这份文档能帮你"看懂"，但**看懂 ≠ 会做**。手册 Step 13 说得很明白——把课程项目换成自己的场景，才是简历上能写的东西。
