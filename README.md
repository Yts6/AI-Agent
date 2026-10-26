# AI Agent 智能体助手

> 一个带知识库检索（RAG）、联网搜索、多模型切换和文档导出的本地 AI 助手。

支持 10+ 个模型（通义千问、DeepSeek 等），可接入任意 OpenAI 兼容接口，聊天记录本地存储，数据不出本机。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)

---

## 系统架构

```
+--------------------------------------------------------------+
|  浏览器（原生 JS，单文件 122KB）                                 |
|                                                              |
|   [对话界面]      [知识库管理]      [模型设置]                  |
+---------------------------+----------------------------------+
                            |  SSE / REST
+---------------------------v----------------------------------+
|  FastAPI (server.py)                                          |
|  路由 / 鉴权 / 会话管理 / 隧道生命周期                            |
+---------------------------------------------------------------+
|  agent.py         对话编排 / 消息组装 / 流式推送                 |
|  rag.py           切分 / 向量化 / 召回 / 重排                    |
|  query_rewrite.py 规则改写 + LLM 改写                           |
|  search.py        三引擎联网搜索                                 |
|  docgen.py        Markdown 转 Word/PDF/HTML                     |
|  model_store.py   模型配置 CRUD                                 |
+---------------------------+-----------------------------------+
                            |
+---------------------------v-----------------------------------+
|  数据层                                                        |
|  SQLite agent.db    会话 / 消息 / 文档 / 片段 / 模型              |
|  NumPy vectors.npy  向量矩阵（矩阵乘法检索）                      |
|  文件系统            上传原件 / 导出产物                          |
+---------------------------+-----------------------------------+
                            |
+---------------------------v-----------------------------------+
|  外部服务                                                       |
|  LLM API（百炼/DeepSeek）/ Embedding API                        |
|  bge-reranker（本地）/ 搜索引擎 / cpolar 隧道                    |
+---------------------------------------------------------------+
```

详细架构说明（数据流、技术选型、性能特征、扩展性）见 **[ARCHITECTURE.md](ARCHITECTURE.md)**

### 技术栈速览

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | 原生 JS + CSS | 单文件 3587 行，无框架无构建 |
| 后端 | FastAPI + Uvicorn | 异步、SSE 流式、自动文档 |
| 数据库 | SQLite | 单文件，零外部依赖 |
| 向量检索 | NumPy | 矩阵乘法，134 条 1 毫秒 |
| 重排序 | bge-reranker | 本地交叉编码器，可选 |
| 文档生成 | python-docx / reportlab | Word/PDF/HTML/MD/TXT |
| 内网穿透 | cpolar | 自动启动，冲突检测 |

### 代码规模

| 模块 | 行数 | 职责 |
|------|------|------|
| `server.py` | 1438 | 路由 + 生命周期 + 隧道 |
| `rag.py` | 809 | 检索核心 |
| `db.py` | 621 | SQLite 封装 + 迁移 |
| `docgen.py` | 488 | 文档生成 |
| `config.py` | 359 | 配置管理 |
| `agent.py` | 359 | 对话编排 |
| `rag_eval.py` | 285 | 效果评估 |
| `model_store.py` | 253 | 模型管理 |
| `query_rewrite.py` | 242 | 查询改写 |
| `search.py` | 210 | 联网搜索 |
| `main.py` | 75 | 环境自检 |
| `utils.py` | 37 | 工具 |
| **后端合计** | **5,176** | Python |
| `index.html` | 4,184 | 前端单文件 |

---

## 功能特性

### 对话能力
- **多模型切换**：内置 10 个模型，支持自定义接入任意 OpenAI 兼容 API
- **模型专属头像**：不同模型不同渐变配色 + 品牌缩写，一眼分辨
- **思考过程展示**：推理模型的思维链可折叠查看，显示思考耗时
- **流式输出**：SSE 实时推送，边生成边显示
- **消息队列**：连续发送，可插队并行
- **时间戳**：每条消息记录发送时间

### 会话管理
- **分组**：自定义分组名，折叠展开，置顶优先
- **重命名**：双击标题就地编辑，或 ⋯ 菜单
- **置顶**：重要对话钉在顶部
- **删除**：单条删除或批量清理
- **搜索**：关键词高亮 + 片段预览

### 排版与视觉
- **Markdown 渲染**：标题层级、表格斑马纹、引用块、分隔线
- **代码块**：语言标签、等宽字体、深色主题
- **思考框**：紫色竖条标记，过程与答案视觉分离
- **流式状态**：头像状态点橙色脉冲 → 完成转绿

### 知识库（RAG）
- **多格式上传**：PDF / Word / Markdown / TXT / CSV
- **混合检索**：向量相似度（70%）+ 关键词匹配（30%）
- **查询改写**：规则改写 + LLM 改写，提升召回率
- **重排序**：bge-reranker 交叉编码器精排（可选）
- **引用标注**：回答中标出来源编号

### 联网搜索
- 360 / Bing / 搜狗 三引擎兜底
- 自动判断是否需要联网（闲聊不搜）
- 结果摘要后送入模型，标注来源链接

### 文档导出
- **5 种格式**：Word / PDF / HTML / Markdown / 纯文本
- **智能推荐**：根据内容类型推荐最合适的格式
  - 含代码 → Markdown（保留高亮）
  - 含表格 → Word（便于编辑）
  - 含链接 → HTML（可点击）
  - 短回答 → 纯文本

### 附件与图片
- **文档上传**：解析后作为本轮上下文，不入知识库
- **图片识别**：使用 qwen3-vl-plus 可看图（OCR + 理解）
- **图片缩略图**：附件卡片直接显示预览
- **大小限制**：超过 20MB 前端拦截，避免白传
- **粘贴/拖拽**：Ctrl+V 粘贴截图，拖到页面任意位置都行
- **多文件**：一次拖多个，顺序解析不抢占资源

### 历史消息语义搜索
- **向量索引**：历史对话转 1024 维向量，支持模糊查找
- **设置页触发**：设置 → 工具 → 重建索引
- **阈值过滤**：相似度低于 0.25 的丢弃，避免噪音
- **只读降级**：数据库只读时自动禁用，不影响其他功能

### 数据存储
- **SQLite 单文件数据库**：AI-Agent/agent.db
- **零依赖**：Python 标准库，无需安装 MySQL/PostgreSQL
- **全文搜索**：历史对话关键词搜索，命中高亮
- **本地优先**：所有数据存本机，不上传云端

---

## 快速开始

### 1. 环境要求

- Python 3.10 或更高版本（推荐 3.11）
- Windows / macOS / Linux
- 约 2GB 磁盘空间（含依赖）

### 2. 克隆项目

```bash
git clone https://github.com/Yts6/AI-Agent.git
cd AI-Agent
```

### 3. 创建虚拟环境

**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置 API Key

复制示例配置：

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 Key：

```ini
# 阿里云百炼（推荐，有免费额度）
DASHSCOPE_API_KEY=sk-你的key
```

获取 Key 的步骤见下方「API 申请指南」。

### 6. 启动

**方式一：使用脚本（推荐）**

```powershell
# 启动服务 + 自动开公网隧道
.\run.ps1

# 只本地运行，不开隧道（启动更快）
.\run.ps1 -NoTunnel

# 指定端口
.\run.ps1 -Port 8080

# 强制新建隧道（地址会变）
.\run.ps1 -NewTunnel

# 配置局域网防火墙（需管理员）
.\run.ps1 -SetupLan

# 修复 cpolar 服务冲突（需管理员）
.\run.ps1 -FixCpolar
```

**方式二：直接运行 Python**

```bash
cd AI-Agent
python server.py              # 含隧道
python server.py --no-tunnel  # 不含隧道
```

**方式三：PyCharm 运行配置**

项目已内置两个运行配置（右上角下拉切换）：

| 配置名 | 说明 |
|--------|------|
| AI Agent Server | 含公网隧道 |
| AI Agent Server (无隧道) | 只本地运行，启动快 |

启动后会显示三个地址：

```
   ============================================================
    AI Agent 已启动
   ------------------------------------------------------------

    🖥  本机访问     http://127.0.0.1:8000
    📡 局域网访问   http://192.168.1.100:8000

    🌍 公网访问     https://xxx.cpolar.top
       发这个链接给别人，他在任何网络都能访问

   ============================================================
```

浏览器打开第一个地址即可使用。

**注意**：
- 端口被占用时会自动切换到下一个空闲端口
- 含隧道的模式会弹出 cpolar 窗口，**不要关闭**（可最小化）
- 关闭 Python 进程后隧道可能保留，下次启动会复用同一地址


## API 申请指南

### 方式一：阿里云百炼（推荐，有免费额度）

1. 访问 [阿里云百炼](https://bailian.console.aliyun.com/)
2. 用支付宝/淘宝账号登录
3. 左侧菜单 → **API-KEY 管理**
4. 点击 **创建 API-KEY**
5. 复制以 sk- 开头的密钥
6. 填入 `.env` 的 `DASHSCOPE_API_KEY`

**免费额度**：新用户通常会赠送 Token（具体以官网为准）。

**可用模型**：
- `qwen-flash` — 最快，免费额度多
- `qwen-plus` — 均衡
- `qwen-max` — 最强
- `qwen3.5-flash` / `qwen3.5-plus` — 最新一代，带思考过程
- `qwen3-vl-plus` — 视觉模型，能看图
- `qwen3-coder-flash` — 代码专用

### 方式二：其他服务商

在网页右上角 **⚙ 设置** 里可以添加任意 OpenAI 兼容接口：

| 服务商 | 接口地址 | 获取 Key |
|--------|----------|----------|
| DeepSeek | https://api.deepseek.com/v1 | platform.deepseek.com |
| 月之暗面 Kimi | https://api.moonshot.cn/v1 | platform.moonshot.cn |
| 智谱 GLM | https://open.bigmodel.cn/api/paas/v4 | open.bigmodel.cn |
| 硅基流动 | https://api.siliconflow.cn/v1 | siliconflow.cn |
| OpenAI | https://api.openai.com/v1 | platform.openai.com |

**操作步骤**：
1. 点右上角 ⚙ 齿轮图标
2. 选服务商（自动填接口地址）
3. 填 API Key 和模型名
4. 点「测试连接」验证
5. 点「添加模型」保存

---

## 公网访问（可选）

想让别人通过互联网访问你的服务，需要内网穿透。

### 使用 cpolar（免费）

1. 访问 [cpolar.com](https://www.cpolar.com/) 注册（用邮箱）
2. 登录后进入 **验证** 页面，复制 **Authtoken**
3. 下载 Windows 客户端并解压
4. 配置 token：

```powershell
.\cpolar.exe authtoken 你的authtoken
```

5. 把 `cpolar.exe` 放到项目的 `tools/cpolar/` 目录

之后每次运行会自动：
- 启动 cpolar 隧道
- 申请公网地址
- 在控制台显示

启动方式任选：
- `.\run.ps1`（推荐）
- `python server.py`
- PyCharm 运行「AI Agent Server」

**注意**：
- 免费版公网地址 **24 小时**才轮换一次，重启服务会复用同一地址
- 想强制换地址用 `--new-tunnel` 参数
- 关闭服务时隧道默认**保留**（除非加 `--kill-tunnel-on-exit`）
- 免费版有流量限制

---

## 项目结构

```
AI-Agent/
├── server.py           # FastAPI 服务，路由和接口（44KB）
├── agent.py            # 对话核心逻辑，SSE 流式输出
├── config.py           # 配置与模型客户端
├── model_store.py      # 模型配置增删改查
├── db.py               # SQLite 数据层
├── docgen.py           # 文档生成（Word/PDF/HTML）
├── rag.py              # 知识库检索（向量 + 关键词）
├── query_rewrite.py    # 查询改写
├── rag_eval.py         # 检索效果评估
├── search.py           # 联网搜索
├── utils.py            # 工具函数
├── main.py             # 环境自检入口
├── static/
│   └── index.html      # 前端页面（单文件 125KB）
├── eval_data/
│   └── cases.jsonl     # 评估用例
├── RAG.md              # 知识库实现说明
├── UPLOAD.md           # 文件上传说明
├── TUNNEL.md           # 内网穿透说明
├── SHARE-URL.md        # 公网地址说明
└── agent.db            # SQLite 数据库（运行时生成）

根目录：
├── README.md           # 本文件
├── run.ps1             # 统一启动脚本
├── requirements.txt    # 依赖列表
├── pyproject.toml      # 项目元信息
└── .env.example        # 环境变量模板
```

---

## 数据说明

### 数据存在哪里

| 数据 | 位置 | 说明 |
|------|------|------|
| 对话记录 | agent.db | SQLite 数据库 |
| 知识库向量 | rag_store/vectors.npy | numpy 数组 |
| 上传的文档 | uploads/ | 原始文件备份 |
| 自定义模型 | agent.db 的 models 表 | 含 API Key |

### 备份

```bash
# 备份整个数据库
cp AI-Agent/agent.db backup/

# 备份知识库
cp -r AI-Agent/rag_store/ backup/
```

---

## ⚠️ 安全提示

### 不要上传的文件

以下文件**已在 `.gitignore` 中排除**，不要手动添加：

| 文件 | 原因 |
|------|------|
| `.env` | **含 API Key，泄露会被人盗刷额度** |
| `agent.db` | 含聊天记录和自定义模型的 Key |
| `models.json` | 含自定义模型的 API Key |
| `session_store/` | 本地聊天记录 |
| `rag_store/` | 知识库数据 |
| `uploads/` | 你上传的私有文档 |
| `tools/` | 可执行文件，体积大 |

### 密钥泄露的后果

API Key 一旦泄露，**任何人都能用它消费你的账户额度**：
- 阿里云百炼：可能产生账单
- OpenAI：绑卡的话可能被刷爆
- 所以 `.env` **绝对不能提交到 Git**

### 如果已经泄露

1. 立即去服务商控制台**删除旧 Key**
2. 创建新 Key
3. 更新 `.env`
4. 检查账单

### 公网访问风险

开启公网隧道后，**任何人都能访问你的服务**：
- 他们会消耗你的 API 额度
- 可能上传恶意文件

**建议**：在 `.env` 里设置访问密码：

```ini
ACCESS_PASSWORD=你的密码
```

设置后打开网页需要输入密码。

---

## 常见问题

### Q: 启动报错「没有可用的 API Key」

检查 `.env` 文件是否在项目根目录：

```bash
cat .env
```

### Q: 模型调用失败 401

API Key 无效或已过期。去服务商控制台确认。

### Q: 知识库检索不到内容

1. 确认文档已上传（侧边栏能看到）
2. 检查文档内容是否被正确解析
3. 调整检索阈值（`rag.py` 里的 `MIN_SCORE`）

### Q: 公网地址打不开

1. 确认本机 http://127.0.0.1:8000 能访问
2. 检查 cpolar 进程是否在运行
3. 免费版地址可能过期，重启服务重新申请

### Q: 图片上传没反应

需要切换到 `qwen3-vl-plus` 模型（只有它支持视觉）。

其他模型只能用 OCR 提取文字，识别不了图片内容。

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 流式传输 | Server-Sent Events (SSE) |
| 数据库 | SQLite（Python 标准库） |
| 向量检索 | NumPy 暴力检索，无需 FAISS |
| 重排序 | sentence-transformers (bge-reranker) |
| 前端 | 原生 JS + CSS（单文件，无框架） |
| 文档生成 | python-docx + reportlab |

---

## 开发说明

### 启动选项

```bash
python server.py                    # 默认：0.0.0.0:8000，自动开隧道
python server.py --port 8080        # 换端口
python server.py --no-tunnel        # 不开公网隧道
python server.py --reload           # 开发模式，改代码自动重启
```

### 添加新的导出格式

在 `docgen.py` 里：

1. 写一个 `to_xxx(title, body, meta)` 函数
2. 在 `FORMATS` 字典里注册
3. 在 `build()` 里加分支
