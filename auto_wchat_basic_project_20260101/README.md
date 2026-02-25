# WhatsApp 自动聊天机器人

一个功能完整的 WhatsApp Web 自动化聊天机器人，支持 AI 智能回复、自动翻译、批量发送等功能。

## 📋 目录

- [功能特性](#功能特性)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [配置说明](#配置说明)
- [使用方法](#使用方法)
- [核心模块说明](#核心模块说明)
- [API 接口](#api-接口)
- [常见问题](#常见问题)
- [注意事项](#注意事项)

## ✨ 功能特性

### 核心功能

1. **自动回复**
   - 关键词匹配回复
   - 本地内容库回复
   - AI 智能回复（支持 OpenAI 和通义千问）
   - 多语言自动翻译
   - 防重复回复机制
   - 只处理系统启动后收到的新消息

2. **AI 回复**
   - 支持 OpenAI GPT 系列模型（GPT-3.5, GPT-4, GPT-4o 等）
   - 支持通义千问模型（qwen-turbo, qwen-plus, qwen-max 等）
   - 可配置 AI 人物特点和聊天风格
   - 支持知识库文件上传（docx, xlsx 等）
   - 聊天历史上下文理解

3. **消息管理**
   - 单条消息发送
   - 批量消息发送
   - 定时消息发送
   - 消息频率控制（防止封号）
   - 消息历史记录和查看

4. **联系人管理**
   - 回复所有联系人
   - 指定联系人列表回复
   - 联系人消息过滤
   - 群组消息过滤
   - 聊天记录查看

5. **文件管理**
   - 支持 Word 文档（.docx, .doc）
   - 支持 Excel 表格（.xlsx, .xls）
   - 文件内容提取用于 AI 知识库
   - 文件上传和管理

6. **翻译功能**
   - 多语言自动翻译
   - 自动翻译接收的消息
   - 自动翻译发送的消息
   - 支持中文、英文、日语、俄语等

7. **Web 界面**
   - 可视化操作界面
   - 实时状态监控
   - 配置管理
   - 聊天记录查看
   - 文件管理界面

- **关键词触发**：功能"暂不可用"
- **日程管理**：功能"暂不可用"

## 📁 项目结构

```
auto_wchat_project/
├── main.py                 # 主程序入口
├── config.py               # 配置文件
├── database.py             # 数据库操作
├── whatsapp_client.py      # WhatsApp 客户端（Selenium）
├── auto_reply.py           # 自动回复模块
├── ai_reply.py             # AI 回复模块
├── message_sender.py       # 消息发送模块
├── translator.py           # 翻译模块
├── file_reader.py          # 文件读取模块
├── web_server.py           # Web 服务器
├── check_msg_container.py  # 消息容器检查工具
├── requirements.txt        # Python 依赖
├── templates/
│   └── index.html          # Web 界面模板
├── static/                 # 静态资源
├── uploads/                # 上传文件目录
├── whatsapp_bot.db         # SQLite 数据库
├── local_replies.json      # 本地回复配置
└── keyword_triggers.json   # 关键词触发配置（已废弃）
```

## 🔧 环境要求

- Python 3.8+
- Chrome 浏览器
- ChromeDriver（自动管理）
- 稳定的网络连接

## 📦 安装步骤

### 1. 克隆或下载项目

```bash
cd auto_wchat_project
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 创建环境配置文件

在项目根目录创建 `.env` 文件，配置以下内容：

```env
# AI 配置
AI_ENABLED=True
AI_PROVIDER=openai  # 或 qwen
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-3.5-turbo
QWEN_API_KEY=your_qwen_api_key
QWEN_MODEL=qwen-turbo
AI_TEMPERATURE=0.7
AI_PERSONALITY=你是一个友好、专业的助手，用简洁明了的语言回答问题。
AI_CHAT_PROMPT=请你用一个普通年轻人聊天的语气回答我，像在微信里跟好朋友说话那样。

# 自动回复配置
AUTO_REPLY_ENABLED=True
REPLY_DELAY=2
MIN_REPLY_INTERVAL=5
MAX_MESSAGES_PER_HOUR=20
AUTO_REPLY_LANGUAGE=en

# 联系人配置
LISTEN_CONTACTS=True
REPLY_TO_ALL_CONTACTS=True
SPECIFIC_CONTACTS=联系人1,联系人2

# 翻译配置
TRANSLATION_ENABLED=True
AUTO_TRANSLATE_INCOMING=True
DEFAULT_OUTGOING_LANGUAGE=en

# 浏览器配置
CHROME_PROFILE_PATH=
HEADLESS_MODE=False
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

# 批量发送配置
MAX_RECIPIENTS_PER_BATCH=10
BATCH_DELAY_BETWEEN=2

# 定时消息配置
SCHEDULED_MESSAGES_ENABLED=True

# 数据库配置
DATABASE_PATH=whatsapp_bot.db
LOCAL_CONTENT_PATH=local_replies.json
```

### 4. 运行程序

```bash
python main.py
```

程序会自动启动 Web 服务器（默认端口 5000），并在浏览器中打开管理界面。

## ⚙️ 配置说明

### AI 配置

- **AI_PROVIDER**: 选择 AI 提供商，`openai` 或 `qwen`
- **OPENAI_API_KEY**: OpenAI API 密钥（从 https://platform.openai.com 获取）
- **QWEN_API_KEY**: 通义千问 API 密钥（从 https://dashscope.console.aliyun.com 获取）
- **OPENAI_MODEL**: OpenAI 模型名称（gpt-3.5-turbo, gpt-4, gpt-4o 等）
- **QWEN_MODEL**: 通义千问模型名称（qwen-turbo, qwen-plus, qwen-max 等）
- **AI_TEMPERATURE**: AI 回复的创造性（0.0-2.0，越高越随机）
- **AI_PERSONALITY**: AI 人物特点描述
- **AI_CHAT_PROMPT**: AI 聊天风格提示词

### 自动回复配置

- **AUTO_REPLY_ENABLED**: 是否启用自动回复
- **REPLY_DELAY**: 回复延迟时间（秒）
- **MIN_REPLY_INTERVAL**: 最小回复间隔（秒）
- **MAX_MESSAGES_PER_HOUR**: 每小时最大消息数
- **AUTO_REPLY_LANGUAGE**: 自动回复语言（en, zh, ja, ru 等）

### 联系人配置

- **LISTEN_CONTACTS**: 是否监听联系人消息
- **REPLY_TO_ALL_CONTACTS**: 是否回复所有联系人（True=所有人，False=仅指定列表）
- **SPECIFIC_CONTACTS**: 指定联系人列表（逗号分隔）

### 翻译配置

- **TRANSLATION_ENABLED**: 是否启用翻译
- **AUTO_TRANSLATE_INCOMING**: 是否自动翻译接收的消息
- **DEFAULT_OUTGOING_LANGUAGE**: 默认输出语言

## 🚀 使用方法

### 1. 启动程序

运行 `python main.py`，程序会：
- 启动 Web 服务器
- 自动打开浏览器访问管理界面
- 初始化 WhatsApp 客户端

### 2. 登录 WhatsApp

在 Web 界面中：
1. 点击"获取二维码"按钮
2. 使用手机 WhatsApp 扫描二维码
3. 等待登录成功

### 3. 配置 AI

在 Web 界面中：
1. 进入"AI 配置"页面
2. 选择 AI 提供商（OpenAI 或通义千问）
3. 输入 API 密钥
4. 选择模型
5. 配置人物特点和聊天风格
6. 保存配置

### 4. 配置自动回复

在 Web 界面中：
1. 进入"自动回复设置"页面
2. 启用/禁用自动回复
3. 设置回复语言
4. 配置联系人列表
5. 保存配置

### 5. 上传知识库文件

在 Web 界面中：
1. 进入"文件管理"页面
2. 上传 Word 或 Excel 文件
3. 文件内容会自动提取并用于 AI 回复

### 6. 启动机器人

在 Web 界面中：
1. 确保已登录 WhatsApp
2. 点击"启动机器人"按钮
3. 机器人开始监听消息并自动回复

### 7. 查看聊天记录

在 Web 界面中：
1. 进入"聊天窗口"页面
2. 选择联系人查看消息历史
3. 支持中英文双语显示

## 📚 核心模块说明

### 1. WhatsAppClient (`whatsapp_client.py`)

WhatsApp Web 客户端，使用 Selenium 自动化操作。

**主要功能：**
- 二维码登录
- 消息监听
- 消息发送
- 图片发送
- 登录状态检测

**关键方法：**
- `login()`: 登录 WhatsApp
- `listen_messages()`: 监听消息
- `send_message()`: 发送消息
- `send_image()`: 发送图片
- `get_qr_code()`: 获取登录二维码

### 2. AutoReply (`auto_reply.py`)

自动回复核心模块。

**主要功能：**
- 消息处理
- 回复生成（关键词/本地内容/AI）
- 防重复回复
- 时间戳过滤（只处理启动后的消息）

**关键方法：**
- `handle_message()`: 处理收到的消息
- `generate_reply()`: 生成回复内容
- `should_reply()`: 判断是否应该回复

### 3. AIReply (`ai_reply.py`)

AI 回复模块，支持 OpenAI 和通义千问。

**主要功能：**
- AI 回复生成
- 多模型支持
- 聊天历史上下文
- 知识库内容整合

**关键方法：**
- `generate_reply()`: 生成 AI 回复
- `is_available()`: 检查 AI 是否可用
- `set_personality()`: 设置 AI 人物特点

### 4. Database (`database.py`)

数据库操作模块，使用 SQLite。

**主要表结构：**
- `messages`: 消息记录
- `scheduled_messages`: 定时消息
- `batch_messages`: 批量消息
- `message_stats`: 消息统计

**关键方法：**
- `save_message()`: 保存消息
- `get_message_history()`: 获取聊天历史
- `message_exists()`: 检查消息是否存在

### 5. MessageSender (`message_sender.py`)

消息发送模块。

**主要功能：**
- 单条消息发送
- 批量消息发送
- 定时消息发送
- 频率控制

**关键方法：**
- `send_message()`: 发送单条消息
- `send_batch_messages()`: 批量发送
- `schedule_message()`: 定时发送

### 6. Translator (`translator.py`)

翻译模块，使用 Google 翻译。

**主要功能：**
- 多语言翻译
- 自动语言检测
- 消息翻译

**关键方法：**
- `translate()`: 通用翻译
- `translate_to_chinese()`: 翻译成中文
- `translate_outgoing()`: 翻译发送的消息

### 7. FileReader (`file_reader.py`)

文件读取模块。

**支持格式：**
- Word 文档（.docx, .doc）
- Excel 表格（.xlsx, .xls）

**关键方法：**
- `read_file()`: 读取文件
- `process_file_for_ai()`: 处理文件用于 AI

### 8. WebServer (`web_server.py`)

Web 服务器，提供管理界面。

**主要路由：**
- `/`: 主页面
- `/api/status`: 获取状态
- `/api/login_qr`: 获取登录二维码
- `/api/send_message`: 发送消息
- `/api/ai_config`: AI 配置
- `/api/chat_list`: 聊天列表
- `/api/chat_messages`: 聊天消息

## 🔌 API 接口

### 状态接口

**GET** `/api/status`
- 返回机器人运行状态

### 登录接口

**GET** `/api/login_qr`
- 获取登录二维码

**POST** `/api/login`
- 执行登录操作

### 消息接口

**POST** `/api/send_message`
- 发送单条消息
- 参数：`chat_id`, `message`, `translate`, `target_lang`

**POST** `/api/send_batch`
- 批量发送消息
- 参数：`chat_ids`, `message`, `translate`, `target_lang`

**POST** `/api/ai_reply_batch`
- AI 批量回复
- 参数：`chat_ids`, `prompt`, `target_lang`, `max_recipients`

### 配置接口

**GET/POST** `/api/ai_config`
- 获取/保存 AI 配置

**GET/POST** `/api/auto_reply_contacts`
- 获取/保存自动回复联系人配置

**GET/POST** `/api/ai_reply_rhythm`
- 获取/保存 AI 回复节奏设置

### 文件接口

**POST** `/api/upload_file`
- 上传知识库文件

**GET** `/api/uploaded_files`
- 获取已上传文件列表

**POST** `/api/remove_file`
- 移除文件（从内存）

**POST** `/api/delete_uploaded_file`
- 删除已上传文件

### 聊天接口

**GET** `/api/chat_list`
- 获取聊天列表

**GET** `/api/chat_messages`
- 获取聊天消息
- 参数：`chat_id`


## ❓ 常见问题

### 1. 无法登录 WhatsApp

**可能原因：**
- 网络连接问题
- 二维码过期
- 浏览器驱动问题

**解决方法：**
- 检查网络连接
- 重新获取二维码
- 更新 Chrome 浏览器和 ChromeDriver

### 2. AI 回复失败

**可能原因：**
- API 密钥错误
- API 余额不足
- 网络问题

**解决方法：**
- 检查 API 密钥是否正确
- 检查账户余额
- 检查网络连接
- 查看日志文件 `whatsapp_bot.log`

### 3. 消息发送失败

**可能原因：**
- 联系人不存在
- 消息格式错误
- 频率限制

**解决方法：**
- 确保联系人名称正确（使用 WhatsApp 显示的名称）
- 检查消息内容
- 调整发送频率设置

### 4. 翻译功能不工作

**可能原因：**
- 翻译服务不可用
- 网络问题

**解决方法：**
- 检查网络连接
- 尝试手动翻译测试

### 5. 文件上传失败

**可能原因：**
- 文件格式不支持
- 文件过大
- 文件损坏

**解决方法：**
- 确保文件格式为 .docx, .xlsx 等
- 检查文件大小
- 尝试重新保存文件

## ⚠️ 注意事项

### 1. 账号安全

- **不要频繁发送消息**：设置合理的发送频率，避免被 WhatsApp 封号
- **使用真实浏览器环境**：程序已内置反检测措施，但仍需谨慎使用
- **不要发送垃圾消息**：遵守 WhatsApp 使用条款

### 2. API 使用

- **控制 API 调用频率**：避免超出 API 限制
- **监控 API 使用量**：定期检查 API 余额
- **保护 API 密钥**：不要将 `.env` 文件提交到代码仓库

### 3. 数据隐私

- **保护聊天记录**：数据库文件包含敏感信息，请妥善保管
- **不要分享日志文件**：日志可能包含个人信息

### 4. 性能优化

- **限制消息历史**：定期清理旧消息记录
- **控制知识库大小**：过大的知识库可能影响 AI 回复速度
- **合理设置延迟**：根据实际情况调整回复延迟

### 5. 错误处理

- **查看日志文件**：`whatsapp_bot.log` 包含详细的运行日志
- **检查数据库**：使用 `inspect_db.py` 检查数据库状态
- **重启程序**：遇到问题时尝试重启程序

### 6. 功能状态

- **关键词触发**：功能"暂不可用"
- **日程管理**：功能"暂不可用"
- 其他功能正常工作

## 📝 更新日志


### v1.0.0
- 初始版本发布
- 支持基本的自动回复功能
- 支持 OpenAI 和通义千问
- Web 管理界面
- 文件上传和知识库功能

## 📄 许可证

本项目仅供学习和研究使用，请遵守相关法律法规和 WhatsApp 使用条款。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 📧 联系方式

如有问题或建议，请通过 Issue 反馈。

---

**免责声明**：本工具仅供学习和研究使用。使用本工具时请遵守相关法律法规和平台使用条款。作者不对因使用本工具而产生的任何后果负责。
