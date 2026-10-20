# 上传功能说明

## 文件上传（可用）

支持格式：`.pdf` `.docx` `.txt` `.md` `.csv`

三种方式：
1. 点击 📎 按钮选择
2. 拖动文件到输入框
3. 复制文件后 `Ctrl+V` 粘贴

上传后会在输入框上方显示附件卡片，可点 × 删除。

---

## 图片上传（当前受限）

### 为什么不能用

两条路都走不通：

| 方案 | 状态 | 原因 |
|---|---|---|
| 视觉模型（qwen-vl） | ❌ | 你的百炼账号未开通，API 返回 `Model not exist` |
| 本地 OCR（Tesseract） | ❌ | `pytesseract` 已装，但 Tesseract 引擎未安装 |

### 想启用图片识别，二选一

**方案 A：开通 qwen-vl（推荐，效果最好）**

1. 去 https://bailian.console.aliyun.com
2. 找到「模型广场」→ 搜索 `qwen-vl-plus`
3. 点击开通（免费额度通常有 100 万 token）
4. 开通后告诉我，我改代码支持图片直传

优点：能真正"看懂"图片内容（图表、截图、手写）
缺点：需要开通，且超出免费额度要付费

**方案 B：装 Tesseract（只能识别文字）**

下载：https://github.com/UB-Mannheim/tesseract/wiki
- 下载 `tesseract-ocr-w64-setup-*.exe`
- 安装时**勾选 Chinese (Simplified)** 语言包
- 默认装到 `C:\Program Files\Tesseract-OCR\`

装完告诉我，我配置路径。

优点：完全免费、离线可用
缺点：只认文字，看不懂图表和照片

---

## 排查记录

### 问题：点击上传按钮没反应

**根因**：前端 JS 有语法错误，整个脚本崩溃。

具体是两处：
1. `uploadFile` 函数的 `finally` 块缺少闭合括号
2. 粘贴事件监听器写在 `const inputEl` 声明之前，触发 `ReferenceError`

**修复**：补齐括号 + 把事件监听移到变量声明之后。

### 问题：大文档上传失败

**根因**：阿里云百炼 embedding API 限制单次最多 10 条文本。

上传 48KB 文档会切成 120 块，一次性发送被拒绝。

**修复**：批处理，每批 10 条。
