"""
Web服务器 - 提供HTML界面
"""
import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import threading
import webbrowser
from datetime import datetime
from whatsapp_client import WhatsAppClient
from auto_reply import AutoReply, ScheduledReply
from message_sender import MessageSender
from database import Database
from file_reader import ContentManager
from ai_reply import AIReply
from translator import Translator
import urllib3
import warnings

# 修复 urllib3 连接池警告：禁用连接池警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# 禁用连接池满的警告
warnings.filterwarnings('ignore', message='.*Connection pool is full.*')
warnings.filterwarnings('ignore', category=urllib3.exceptions.HTTPWarning)

logger = logging.getLogger(__name__)


class WebServer:
    def __init__(self, bot_instance=None):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        CORS(self.app)
        self.bot = bot_instance
        self.content_manager = bot_instance.content_manager if bot_instance else ContentManager()
        
        self.setup_routes()
    
    def setup_routes(self):
        """设置路由"""
        
        def _format_env_value(value: str) -> str:
            """
            格式化环境变量值，正确处理换行符和特殊字符。
            如果值包含换行符、引号或特殊字符，用双引号包裹并转义。
            换行符会被转换为 \\n 转义序列，以便在 .env 文件中正确保存和读取。
            """
            if not isinstance(value, str):
                value = str(value)
            
            # 如果值包含换行符、引号、反斜杠或空格，需要用引号包裹
            needs_quotes = ('\n' in value or '\r' in value or 
                          '"' in value or '\\' in value or 
                          ' ' in value or value.startswith('#') or
                          '=' in value)
            
            if needs_quotes:
                # 转义顺序很重要：
                # 1. 先转义反斜杠（避免后续转义被影响）
                # 2. 转义双引号
                # 3. 最后将换行符转换为 \n 转义序列
                escaped_value = value.replace('\\', '\\\\')  # 先转义反斜杠
                escaped_value = escaped_value.replace('"', '\\"')  # 转义双引号
                # 将各种换行符统一转换为 \n 转义序列
                escaped_value = escaped_value.replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n')
                return f'"{escaped_value}"'
            else:
                return value
        
        def _update_env_vars(config_updates: dict):
            """
            通用的 .env 更新工具函数。
            将传入的键值对写入 .env（不存在则追加），并自动重新加载环境变量和 config 模块。
            支持多行值（换行符会被正确保存）。
            """
            try:
                env_file_path = os.path.join(os.getcwd(), '.env')
                env_lines = []
                if os.path.exists(env_file_path):
                    try:
                        with open(env_file_path, 'r', encoding='utf-8') as f:
                            env_lines = f.readlines()
                    except Exception as e:
                        logger.warning(f"读取.env文件失败: {e}")
                
                # 处理现有配置
                updated_lines = []
                updated_keys = set()
                for line in env_lines:
                    line_stripped = line.strip()
                    # 保留空行和注释
                    if not line_stripped or line_stripped.startswith('#'):
                        updated_lines.append(line)
                        continue
                    
                    if '=' in line_stripped:
                        key = line_stripped.split('=')[0].strip()
                        if key in config_updates:
                            # 使用格式化函数处理值
                            formatted_value = _format_env_value(config_updates[key])
                            updated_lines.append(f"{key}={formatted_value}\n")
                            updated_keys.add(key)
                        else:
                            updated_lines.append(line)
                    else:
                        updated_lines.append(line)
                
                # 添加/追加新配置项
                for key, value in config_updates.items():
                    if key not in updated_keys:
                        formatted_value = _format_env_value(value)
                        updated_lines.append(f"{key}={formatted_value}\n")
                
                # 写入文件
                with open(env_file_path, 'w', encoding='utf-8') as f:
                    f.writelines(updated_lines)
                
                # 刷新环境变量与配置
                from dotenv import load_dotenv
                load_dotenv(override=True)
                
                import importlib
                import config
                importlib.reload(config)
                
                logger.info(f"环境配置已更新并写入 {env_file_path}")
            except Exception as e:
                logger.error(f"更新环境配置失败: {e}")
                raise
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/api/status', methods=['GET'])
        def get_status():
            if not self.bot:
                return jsonify({"error": "Bot not initialized"}), 500

            # 每次请求状态时，尽量根据浏览器实际页面刷新登录状态
            try:
                self.bot.client.refresh_login_status()
            except Exception as e:
                logger.debug(f"刷新登录状态时出错: {e}")
            
            return jsonify({
                "logged_in": self.bot.client.is_logged_in,
                "running": self.bot.running,
                "auto_reply_enabled": self.bot.auto_reply.enabled,
                "min_reply_interval": self.bot.client.min_reply_interval,
                "max_recipients_per_batch": self.bot.message_sender.max_recipients_per_batch,
                "batch_delay_between": self.bot.message_sender.batch_delay_between
            })
        
        @self.app.route('/api/login_qr', methods=['GET'])
        def get_login_qr():
            """获取登录二维码"""
            try:
                if not self.bot.client.driver:
                    self.bot.client.init_driver()
                
                # 先主动刷新登录状态，检测用户是否已经扫码登录成功
                try:
                    self.bot.client.refresh_login_status()
                except Exception as e:
                    logger.debug(f"刷新登录状态时出错: {e}")
                
                # 如果已经登录，则不需要二维码
                if self.bot.client.is_logged_in:
                    return jsonify({
                        "success": True,
                        "message": "当前账号已登录，无需扫描二维码。",
                        "qr_base64": None,
                        "qr_data_ref": None,
                        "logged_in": True
                    })
                
                qr_data = self.bot.client.get_qr_code()
                
                # 获取二维码后再次检查登录状态（用户可能在获取二维码的过程中扫码登录了）
                try:
                    self.bot.client.refresh_login_status()
                    if self.bot.client.is_logged_in:
                        return jsonify({
                            "success": True,
                            "message": "检测到已登录，无需扫描二维码。",
                            "qr_base64": None,
                            "qr_data_ref": None,
                            "logged_in": True
                        })
                except Exception as e:
                    logger.debug(f"二次刷新登录状态时出错: {e}")

                # 成功获取到二维码数据
                if qr_data:
                    return jsonify({
                        "success": True,
                        "qr_base64": qr_data.get("base64"),
                        "qr_data_ref": qr_data.get("data_ref")
                    })

                # 无法获取二维码，但不再返回 400，让前端根据 success 提示用户重试
                return jsonify({
                    "success": False,
                    "message": "当前无法获取二维码，请稍后重试或手动刷新页面。"
                })
            except Exception as e:
                logger.error(f"获取二维码错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/login', methods=['POST'])
        def login():
            try:
                data = request.json
                phone_number = data.get('phone_number')

                # 根据是否有电话号码决定登录方式
                if phone_number:
                    # 使用电话号码登录
                    success = self.bot.client.login(phone_number=phone_number)
                    fail_message = "电话号码登录失败，请检查号码或改用二维码登录。"
                else:
                    # 使用二维码登录
                    success = self.bot.client.login()
                    fail_message = "登录失败，请刷新二维码后重试。"

                # 无论成功还是失败，都返回 200，由前端根据 success 字段判断
                if success:
                    return jsonify({"success": True, "message": "登录成功"})
                else:
                    return jsonify({"success": False, "message": fail_message})
            except Exception as e:
                logger.error(f"登录错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/send_message', methods=['POST'])
        def send_message():
            try:
                # 检查是否已登录
                if not self.bot.client.is_logged_in:
                    return jsonify({"success": False, "message": "请先登录WhatsApp"}), 400
                
                data = request.json
                chat_id = data.get('chat_id', '').strip()
                message = data.get('message', '').strip()
                translate = data.get('translate', True)
                target_lang = data.get('target_lang', 'en')
                
                # 验证输入
                if not chat_id:
                    return jsonify({"success": False, "message": "请输入联系人/群组名称"}), 400
                
                if not message:
                    return jsonify({"success": False, "message": "请输入消息内容"}), 400
                
                logger.info(f"准备发送消息到: {chat_id}, 消息: {message[:50]}...")
                
                success = self.bot.send_message(chat_id, message, translate=translate, target_lang=target_lang)
                
                if success:
                    return jsonify({"success": True, "message": f"消息已成功发送到 {chat_id}"})
                else:
                    return jsonify({"success": False, "message": f"发送失败，无法找到联系人 '{chat_id}'。请确保输入的是联系人在 WhatsApp 中显示的名称（昵称），而不是电话号码。如果该联系人不在您的联系人列表中，请先添加为联系人。"}), 400
            except Exception as e:
                error_msg = str(e)
                logger.error(f"发送消息错误: {e}", exc_info=True)
                
                # 提供更友好的错误信息
                if "未登录" in error_msg or "not logged in" in error_msg.lower():
                    return jsonify({"success": False, "message": "未登录，请先登录WhatsApp"}), 400
                elif "打开聊天失败" in error_msg or "open chat" in error_msg.lower() or "无法找到联系人" in error_msg:
                    return jsonify({"success": False, "message": f"无法找到联系人 '{chat_id}'。请确保输入的是联系人在 WhatsApp 中显示的名称（昵称），而不是电话号码。如果该联系人不在您的联系人列表中，请先添加为联系人。"}), 400
                elif "timeout" in error_msg.lower():
                    return jsonify({"success": False, "message": "操作超时，请稍后重试"}), 400
                else:
                    return jsonify({"success": False, "message": f"发送失败: {error_msg}"}), 500
        
        @self.app.route('/api/send_batch', methods=['POST'])
        def send_batch():
            try:
                data = request.json
                chat_ids = data.get('chat_ids', [])
                message = data.get('message')
                translate = data.get('translate', True)
                target_lang = data.get('target_lang', 'en')
                
                results = self.bot.send_batch(chat_ids, message, translate=translate, target_lang=target_lang)
                
                return jsonify({"success": True, "results": results})
            except Exception as e:
                logger.error(f"批量发送错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_reply_batch', methods=['POST'])
        def ai_reply_batch():
            """AI批量回复"""
            try:
                data = request.json
                chat_ids = data.get('chat_ids', [])
                prompt = data.get('prompt')
                target_lang = data.get('target_lang', 'en')
                max_recipients = data.get('max_recipients', 10)
                
                if not chat_ids or not prompt:
                    return jsonify({"success": False, "message": "请填写完整信息"}), 400
                
                # 使用AI生成回复
                ai_reply = AIReply()
                if not ai_reply.is_available():
                    return jsonify({"success": False, "message": "AI功能未启用"}), 400
                
                file_content = self.content_manager.get_all_content()
                ai_message, error_msg = ai_reply.generate_reply(prompt, file_content=file_content)
                
                if not ai_message:
                    # 返回详细的错误信息
                    error_message = error_msg if error_msg else "AI生成回复失败，请稍后重试"
                    return jsonify({"success": False, "message": error_message}), 400
                
                # 批量发送
                results = self.bot.message_sender.send_batch_messages(
                    chat_ids[:max_recipients],
                    ai_message,
                    translate=True,
                    target_lang=target_lang,
                    max_recipients=max_recipients
                )
                
                return jsonify({
                    "success": True,
                    "message": f"AI批量回复已发送给 {len([r for r in results.values() if r])} 个联系人",
                    "results": results
                })
            except Exception as e:
                logger.error(f"AI批量回复错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/settings/reply_limits', methods=['GET', 'POST'])
        def reply_limits():
            """获取/设置回复节奏设置"""
            if request.method == 'GET':
                return jsonify({
                    "success": True,
                    "min_reply_interval": self.bot.client.min_reply_interval,
                    "max_recipients_per_batch": self.bot.message_sender.max_recipients_per_batch,
                    "batch_delay_between": self.bot.message_sender.batch_delay_between
                })
            else:
                try:
                    data = request.json
                    min_interval = data.get('min_reply_interval')
                    max_recipients = data.get('max_recipients_per_batch')
                    batch_delay = data.get('batch_delay_between')
                    
                    self.bot.message_sender.update_settings(
                        min_reply_interval=min_interval,
                        max_recipients_per_batch=max_recipients,
                        batch_delay_between=batch_delay
                    )
                    
                    return jsonify({"success": True, "message": "设置已保存"})
                except Exception as e:
                    return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/schedule_message', methods=['POST'])
        def schedule_message():
            try:
                data = request.json
                chat_id = data.get('chat_id')
                message = data.get('message')
                scheduled_time_str = data.get('scheduled_time')
                translate = data.get('translate', True)
                target_lang = data.get('target_lang', 'en')
                
                scheduled_time = datetime.fromisoformat(scheduled_time_str)
                self.bot.schedule_message(chat_id, message, scheduled_time, translate=translate, target_lang=target_lang)
                
                return jsonify({"success": True, "message": "定时消息已添加"})
            except Exception as e:
                logger.error(f"定时消息错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_models', methods=['GET'])
        def get_ai_models():
            """获取支持的AI模型列表"""
            models = [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "description": "最新的GPT-4优化版本，性能最强",
                    "provider": "openai"
                },
                {
                    "id": "gpt-4-turbo",
                    "name": "GPT-4 Turbo",
                    "description": "GPT-4的快速版本，性能优秀",
                    "provider": "openai"
                },
                {
                    "id": "gpt-4",
                    "name": "GPT-4",
                    "description": "GPT-4标准版本，功能强大",
                    "provider": "openai"
                },
                {
                    "id": "gpt-3.5-turbo",
                    "name": "GPT-3.5 Turbo",
                    "description": "GPT-3.5快速版本，性价比高（推荐）",
                    "provider": "openai"
                },
                {
                    "id": "gpt-3.5-turbo-16k",
                    "name": "GPT-3.5 Turbo 16K",
                    "description": "GPT-3.5 Turbo，支持更长上下文",
                    "provider": "openai"
                },
                {
                    "id": "gpt-4o-mini",
                    "name": "GPT-4o Mini",
                    "description": "GPT-4o的轻量版本，速度快",
                    "provider": "openai"
                },
                {
                    "id": "qwen-turbo",
                    "name": "通义千问-Turbo",
                    "description": "通义千问快速版本，响应速度快（推荐）",
                    "provider": "qwen"
                },
                {
                    "id": "qwen-plus",
                    "name": "通义千问-Plus",
                    "description": "通义千问增强版本，性能更强",
                    "provider": "qwen"
                },
                {
                    "id": "qwen-max",
                    "name": "通义千问-Max",
                    "description": "通义千问最强版本，性能最强",
                    "provider": "qwen"
                },
                {
                    "id": "qwen-max-longcontext",
                    "name": "通义千问-Max-LongContext",
                    "description": "通义千问Max版本，支持超长上下文",
                    "provider": "qwen"
                }
            ]
            return jsonify({"success": True, "models": models})
        
        @self.app.route('/api/ai_config', methods=['GET'])
        def get_ai_config():
            """获取AI配置信息"""
            try:
                # 重新加载环境变量和配置模块，确保获取最新配置
                from dotenv import load_dotenv
                load_dotenv(override=True)
                
                import importlib
                import config
                importlib.reload(config)
                
                from config import OPENAI_MODEL, OPENAI_API_KEY, AI_ENABLED, AI_TEMPERATURE, AI_PERSONALITY
                QWEN_API_KEY = getattr(config, 'QWEN_API_KEY', '')
                QWEN_MODEL = getattr(config, 'QWEN_MODEL', 'qwen-turbo')
                AI_PROVIDER = getattr(config, 'AI_PROVIDER', 'openai').lower()
                AI_CHAT_PROMPT = getattr(config, 'AI_CHAT_PROMPT', '')
                
                # 重新加载ai_reply模块以确保使用最新配置
                import ai_reply
                importlib.reload(ai_reply)
                from ai_reply import AIReply
                
                # 检查 .env 文件是否存在
                env_file_path = os.path.join(os.getcwd(), '.env')
                env_file_exists = os.path.exists(env_file_path)
                
                ai_reply = AIReply()
                
                # 根据提供商确定使用的API密钥和模型
                if AI_PROVIDER == 'qwen':
                    api_key = QWEN_API_KEY
                    model = QWEN_MODEL
                    api_key_status = "已配置" if QWEN_API_KEY else "未配置"
                else:
                    api_key = OPENAI_API_KEY
                    model = OPENAI_MODEL
                    api_key_status = "已配置" if OPENAI_API_KEY else "未配置"
                
                api_key_preview = ""
                if api_key:
                    # 只显示前4位和后4位，中间用*代替
                    if len(api_key) > 8:
                        api_key_preview = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
                    else:
                        api_key_preview = "*" * len(api_key)
                else:
                    api_key_preview = "未配置"
                
                # 生成配置帮助信息
                if not env_file_exists:
                    config_help = f"⚠️ .env 文件不存在！\n请在项目根目录创建 .env 文件，或使用下方的配置表单直接配置。"
                elif not api_key:
                    if AI_PROVIDER == 'qwen':
                        config_help = f"✓ .env 文件存在\n请在下方表单中配置通义千问API密钥（从DashScope控制台获取API Key，不是AccessKey ID/Secret）"
                    else:
                        config_help = f"✓ .env 文件存在\n请在下方表单中配置 OpenAI API 密钥"
                else:
                    config_help = "✓ 配置文件已正确设置"
                
                return jsonify({
                    "success": True,
                    "model": model,
                    "api_key": api_key if api_key else "",  # 返回完整密钥供编辑
                    "api_key_status": api_key_status,
                    "api_key_preview": api_key_preview,
                    "ai_enabled": AI_ENABLED,
                    "ai_available": ai_reply.is_available(),
                    "temperature": AI_TEMPERATURE,
                    "personality": AI_PERSONALITY,
                    "chat_prompt": AI_CHAT_PROMPT,
                    "ai_provider": AI_PROVIDER,
                    "qwen_api_key": QWEN_API_KEY if QWEN_API_KEY else "",
                    "qwen_model": QWEN_MODEL,
                    "env_file_exists": env_file_exists,
                    "env_file_path": env_file_path,
                    "config_help": config_help
                })
            except Exception as e:
                logger.error(f"获取AI配置错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_config', methods=['POST'])
        def save_ai_config():
            """保存AI配置到.env文件"""
            try:
                data = request.json
                api_key = data.get('api_key', '').strip()
                qwen_api_key = data.get('qwen_api_key', '').strip()
                model = data.get('model', 'gpt-3.5-turbo').strip()
                ai_provider = data.get('ai_provider', 'openai').strip().lower()
                ai_enabled = data.get('ai_enabled', True)
                temperature = float(data.get('temperature', 0.7))
                # 保留所有换行符，只去掉首尾的空格和制表符（不包含换行符）
                personality_raw = data.get('personality', '')
                if personality_raw and personality_raw.strip():
                    # 去掉首尾空白但保留换行符
                    personality = personality_raw.rstrip(' \t').lstrip(' \t')
                else:
                    personality = '你是一个友好、专业的助手，用简洁明了的语言回答问题。'
                chat_prompt = data.get('chat_prompt', '').strip() or '请你用一个普通年轻人聊天的语气回答我，像在微信里跟好朋友说话那样。可以适当用\'嘛\'\'啦\'\'呀\'这些语气词，加点生活化的表达，别说教，别太规整，最好带点小情绪或小幽默，让人感觉是真人而不是AI在回。'
                
                # 验证温度范围
                if temperature < 0.0 or temperature > 2.0:
                    return jsonify({"success": False, "message": "温度参数必须在0.0-2.0之间"}), 400
                
                # 验证提供商
                if ai_provider not in ['openai', 'qwen']:
                    return jsonify({"success": False, "message": "不支持的AI提供商，请选择OpenAI或通义千问"}), 400
                
                # 验证模型
                if ai_provider == 'openai':
                    valid_models = ['gpt-4o', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo', 'gpt-3.5-turbo-16k', 'gpt-4o-mini']
                else:  # qwen
                    valid_models = ['qwen-turbo', 'qwen-plus', 'qwen-max', 'qwen-max-longcontext']
                
                if model not in valid_models:
                    return jsonify({"success": False, "message": f"不支持的模型，请从列表中选择"}), 400
                
                # 需要更新到 .env 的配置项
                config_updates = {
                    'OPENAI_API_KEY': api_key,
                    'OPENAI_MODEL': model if ai_provider == 'openai' else '',
                    'QWEN_API_KEY': qwen_api_key,
                    'QWEN_MODEL': model if ai_provider == 'qwen' else '',
                    'AI_PROVIDER': ai_provider,
                    'AI_ENABLED': str(ai_enabled),
                    'AI_TEMPERATURE': str(temperature),
                    'AI_PERSONALITY': personality,
                    'AI_CHAT_PROMPT': chat_prompt
                }
                
                # 统一通过工具函数写入并刷新环境变量
                try:
                    _update_env_vars(config_updates)
                    return jsonify({
                        "success": True,
                        "message": "AI配置已保存成功！请刷新页面查看更新后的配置。"
                    })
                except Exception as e:
                    logger.error(f"保存.env文件失败: {e}")
                    return jsonify({"success": False, "message": f"保存配置文件失败: {str(e)}"}), 500
                    
            except Exception as e:
                logger.error(f"保存AI配置错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_personality', methods=['POST'])
        def set_ai_personality():
            try:
                data = request.json
                personality_raw = data.get('personality')
                
                if not personality_raw or not personality_raw.strip():
                    return jsonify({"success": False, "message": "人物特点不能为空"}), 400
                
                # 保留所有换行符，只去掉首尾的空格和制表符（不包含换行符）
                personality = personality_raw.rstrip(' \t').lstrip(' \t')
                
                # 先将人物特点持久化到 .env，并刷新配置
                try:
                    _update_env_vars({'AI_PERSONALITY': personality})
                except Exception as e:
                    logger.error(f"保存AI人物特点到.env失败: {e}")
                    return jsonify({"success": False, "message": f'保存人物特点到配置文件失败: {e}'}), 500
                
                # 更新当前运行中的 AutoReply / AIReply 配置
                if self.bot and self.bot.auto_reply:
                    self.bot.auto_reply.set_ai_personality(personality)
                
                # 返回保存的值，确保前端能正确显示
                return jsonify({
                    "success": True, 
                    "message": "AI人物特点已保存，并将在下次启动时自动生效",
                    "personality": personality  # 返回保存的值
                })
            except Exception as e:
                logger.error(f"设置AI人物特点错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_chat_prompt', methods=['POST'])
        def set_ai_chat_prompt():
            """设置AI聊天提示词"""
            try:
                data = request.json
                chat_prompt = data.get('chat_prompt', '').strip()
                
                # 如果为空，使用默认值
                if not chat_prompt:
                    chat_prompt = "请你用一个普通年轻人聊天的语气回答我，像在微信里跟好朋友说话那样。可以适当用'嘛''啦''呀'这些语气词，加点生活化的表达，别说教，别太规整，最好带点小情绪或小幽默，让人感觉是真人而不是AI在回。"
                
                # 将聊天提示词持久化到 .env，并刷新配置
                try:
                    _update_env_vars({'AI_CHAT_PROMPT': chat_prompt})
                    logger.info(f"AI聊天提示词已保存，长度: {len(chat_prompt)} 字符,内容：{chat_prompt}")
                except Exception as e:
                    logger.info(f"保存AI聊天提示词到.env失败: {e}")
                    return jsonify({"success": False, "message": f'保存聊天提示词到配置文件失败: {e}'}), 500
                
                # 返回保存的值，确保前端能正确显示
                return jsonify({
                    "success": True, 
                    "message": "AI聊天提示词已保存，将在下次生成回复时生效",
                    "chat_prompt": chat_prompt  # 返回保存的值
                })
            except Exception as e:
                logger.error(f"设置AI聊天提示词错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/keyword_triggers', methods=['GET'])
        def get_keyword_triggers():
            """获取关键词触发配置（功能已禁用）"""
            return jsonify({
                "success": False,
                "enabled": False,
                "rules": [],
                "message": "关键词触发功能已禁用"
            })
        
        @self.app.route('/api/keyword_triggers', methods=['POST'])
        def save_keyword_triggers():
            """保存关键词触发配置（功能已禁用）"""
            return jsonify({
                "success": False,
                "message": "关键词触发功能已禁用"
            }), 400
        
        @self.app.route('/api/auto_reply_contacts', methods=['GET'])
        def get_auto_reply_contacts():
            """获取自动回复联系人配置"""
            try:
                from dotenv import load_dotenv
                load_dotenv(override=True)
                
                import importlib
                import config
                importlib.reload(config)
                
                from config import LISTEN_CONTACTS, SPECIFIC_CONTACTS, AUTO_REPLY_ENABLED, REPLY_TO_ALL_CONTACTS, DEFAULT_OUTGOING_LANGUAGE
                
                # 将列表转换为逗号分隔的字符串
                specific_contacts_str = ",".join(SPECIFIC_CONTACTS) if SPECIFIC_CONTACTS else ""
                
                # 获取自动回复语言设置（如果存在）
                auto_reply_language = os.getenv("AUTO_REPLY_LANGUAGE", DEFAULT_OUTGOING_LANGUAGE)
                
                return jsonify({
                    "success": True,
                    "auto_reply_enabled": AUTO_REPLY_ENABLED,
                    "listen_contacts": LISTEN_CONTACTS,
                    "reply_to_all_contacts": REPLY_TO_ALL_CONTACTS,
                    "specific_contacts": specific_contacts_str,
                    "auto_reply_language": auto_reply_language
                })
            except Exception as e:
                logger.error(f"获取自动回复联系人配置错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/auto_reply_contacts', methods=['POST'])
        def save_auto_reply_contacts():
            """保存自动回复联系人配置到.env文件"""
            try:
                data = request.json
                auto_reply_enabled = data.get('auto_reply_enabled', True)
                listen_contacts = data.get('listen_contacts', True)
                reply_to_all_contacts = data.get('reply_to_all_contacts', True)
                specific_contacts = data.get('specific_contacts', '').strip()
                auto_reply_language = data.get('auto_reply_language', 'en').strip()
                
                # 读取现有的.env文件内容
                env_file_path = os.path.join(os.getcwd(), '.env')
                env_lines = []
                if os.path.exists(env_file_path):
                    try:
                        with open(env_file_path, 'r', encoding='utf-8') as f:
                            env_lines = f.readlines()
                    except Exception as e:
                        logger.warning(f"读取.env文件失败: {e}")
                
                # 更新或添加配置项
                config_updates = {
                    'AUTO_REPLY_ENABLED': str(auto_reply_enabled),
                    'LISTEN_CONTACTS': str(listen_contacts),
                    'REPLY_TO_ALL_CONTACTS': str(reply_to_all_contacts),
                    'SPECIFIC_CONTACTS': specific_contacts,
                    'AUTO_REPLY_LANGUAGE': auto_reply_language
                }
                
                # 处理现有配置
                updated_lines = []
                updated_keys = set()
                for line in env_lines:
                    line_stripped = line.strip()
                    if not line_stripped or line_stripped.startswith('#'):
                        updated_lines.append(line)
                        continue
                    
                    if '=' in line_stripped:
                        key = line_stripped.split('=')[0].strip()
                        if key in config_updates:
                            updated_lines.append(f"{key}={config_updates[key]}\n")
                            updated_keys.add(key)
                        else:
                            updated_lines.append(line)
                    else:
                        updated_lines.append(line)
                
                # 添加新配置项
                for key, value in config_updates.items():
                    if key not in updated_keys:
                        updated_lines.append(f"{key}={value}\n")
                
                # 写入.env文件
                try:
                    with open(env_file_path, 'w', encoding='utf-8') as f:
                        f.writelines(updated_lines)
                    
                    # 重新加载环境变量
                    from dotenv import load_dotenv
                    load_dotenv(override=True)
                    
                    # 重新导入配置以更新
                    import importlib
                    import config
                    importlib.reload(config)
                    
                    # 更新bot实例的自动回复设置
                    if self.bot and self.bot.auto_reply:
                        self.bot.auto_reply.enabled = auto_reply_enabled
                        # 强制重新加载配置（通过调用_get_config方法）
                        try:
                            # 触发配置重新加载
                            self.bot.auto_reply._get_config()
                            logger.info("自动回复配置已重新加载")
                        except Exception as e:
                            logger.warning(f"重新加载自动回复配置时出错: {e}")
                    
                    logger.info(f"自动回复联系人配置已保存到 {env_file_path}")
                    return jsonify({
                        "success": True,
                        "message": "自动回复联系人配置已保存成功！配置已立即生效。"
                    })
                except Exception as e:
                    logger.error(f"保存.env文件失败: {e}")
                    return jsonify({"success": False, "message": f"保存配置文件失败: {str(e)}"}), 500
                    
            except Exception as e:
                logger.error(f"保存自动回复联系人配置错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/upload_file', methods=['POST'])
        def upload_file():
            try:
                if 'file' not in request.files:
                    return jsonify({"success": False, "message": "没有文件"}), 400
                
                file = request.files['file']
                if file.filename == '':
                    return jsonify({"success": False, "message": "文件名为空"}), 400
                
                upload_dir = 'uploads'
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, file.filename)
                file.save(file_path)
                
                # 确保使用绝对路径
                if not os.path.isabs(file_path):
                    file_path = os.path.abspath(file_path)
                
                success = self.content_manager.load_file(file_path)
                
                if success:
                    return jsonify({
                        "success": True,
                        "message": "文件已上传并加载",
                        "file_path": file_path,
                        "content_preview": self.content_manager.get_content(file_path)[:200] if self.content_manager.get_content(file_path) else ""
                    })
                else:
                    # 获取更详细的错误信息
                    error_msg = "文件加载失败"
                    try:
                        # 尝试读取文件以获取具体错误
                        test_content = self.content_manager.file_reader.read_file(file_path)
                        if test_content is None:
                            file_ext = os.path.splitext(file_path)[1].lower()
                            if file_ext == '.doc':
                                error_msg = "无法读取 .doc 格式文件。请将文件转换为 .docx 格式后重新上传，或安装 textract 库以支持 .doc 格式。"
                    except Exception as read_error:
                        error_msg = str(read_error)
                    
                    return jsonify({"success": False, "message": error_msg}), 400
            except Exception as e:
                logger.error(f"上传文件错误: {e}")
                error_msg = str(e)
                # 提供更友好的错误信息
                if ".doc" in error_msg.lower() and "docx" in error_msg.lower():
                    error_msg = "无法读取 .doc 格式文件。请将文件转换为 .docx 格式后重新上传，或安装 textract 库以支持 .doc 格式。"
                return jsonify({"success": False, "message": error_msg}), 500
        
        @self.app.route('/api/loaded_files', methods=['GET'])
        def get_loaded_files():
            files = list(self.content_manager.loaded_contents.keys())
            return jsonify({"success": True, "files": files})
        
        @self.app.route('/api/uploaded_files', methods=['GET'])
        def get_uploaded_files():
            """获取所有已上传的文件列表"""
            try:
                upload_dir = 'uploads'
                if not os.path.exists(upload_dir):
                    return jsonify({"success": True, "files": []})
                
                files = []
                for filename in os.listdir(upload_dir):
                    file_path = os.path.join(upload_dir, filename)
                    if os.path.isfile(file_path):
                        # 转换为绝对路径
                        abs_path = os.path.abspath(file_path)
                        # 检查是否已加载
                        is_loaded = abs_path in self.content_manager.loaded_contents
                        files.append({
                            "filename": filename,
                            "path": abs_path,
                            "is_loaded": is_loaded,
                            "size": os.path.getsize(file_path)
                        })
                
                return jsonify({"success": True, "files": files})
            except Exception as e:
                logger.error(f"获取已上传文件列表错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/remove_file', methods=['POST'])
        def remove_file():
            """移除文件（从内存中移除）"""
            try:
                data = request.json
                file_path = data.get('file_path')
                self.content_manager.remove_file(file_path)
                return jsonify({"success": True, "message": "文件已从内存中移除"})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/delete_uploaded_file', methods=['POST'])
        def delete_uploaded_file():
            """删除已上传的物理文件"""
            try:
                data = request.json
                file_path = data.get('file_path')
                
                if not file_path:
                    return jsonify({"success": False, "message": "文件路径不能为空"}), 400
                
                # 转换为绝对路径
                if not os.path.isabs(file_path):
                    file_path = os.path.abspath(file_path)
                
                # 安全检查：确保文件在 uploads 目录中
                upload_dir = os.path.abspath('uploads')
                if not file_path.startswith(upload_dir):
                    return jsonify({"success": False, "message": "只能删除 uploads 目录中的文件"}), 400
                
                # 检查文件是否存在
                if not os.path.exists(file_path):
                    return jsonify({"success": False, "message": "文件不存在"}), 404
                
                # 从内存中移除（如果已加载）
                if file_path in self.content_manager.loaded_contents:
                    self.content_manager.remove_file(file_path)
                
                # 删除物理文件
                os.remove(file_path)
                logger.info(f"已删除文件: {file_path}")
                
                return jsonify({"success": True, "message": "文件已删除"})
            except PermissionError:
                return jsonify({"success": False, "message": "没有权限删除文件"}), 403
            except Exception as e:
                logger.error(f"删除文件错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_reply_rhythm', methods=['GET'])
        def get_ai_reply_rhythm():
            """获取AI自动回复节奏设置"""
            try:
                from dotenv import load_dotenv
                load_dotenv(override=True)
                
                import importlib
                import config
                importlib.reload(config)
                
                from config import REPLY_DELAY, MIN_REPLY_INTERVAL, MAX_MESSAGES_PER_HOUR
                
                return jsonify({
                    "success": True,
                    "reply_delay": REPLY_DELAY,
                    "min_reply_interval": MIN_REPLY_INTERVAL,
                    "max_messages_per_hour": MAX_MESSAGES_PER_HOUR
                })
            except Exception as e:
                logger.error(f"获取AI回复节奏设置错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/ai_reply_rhythm', methods=['POST'])
        def save_ai_reply_rhythm():
            """保存AI自动回复节奏设置到.env文件"""
            try:
                data = request.json

                # 允许前端传入 "2.0" 这类字符串，统一做安全转换
                def _safe_float(v, default):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return float(default)

                def _safe_int(v, default):
                    try:
                        return int(float(v))
                    except (TypeError, ValueError):
                        return int(default)

                reply_delay = _safe_float(data.get('reply_delay', 2), 2)
                min_reply_interval = _safe_int(data.get('min_reply_interval', 5), 5)
                max_messages_per_hour = _safe_int(data.get('max_messages_per_hour', 20), 20)
                
                # 验证参数范围
                if reply_delay < 0 or reply_delay > 60:
                    return jsonify({"success": False, "message": "回复延迟必须在0-60秒之间"}), 400
                
                if min_reply_interval < 1 or min_reply_interval > 300:
                    return jsonify({"success": False, "message": "最小回复间隔必须在1-300秒之间"}), 400
                
                if max_messages_per_hour < 1 or max_messages_per_hour > 100:
                    return jsonify({"success": False, "message": "每小时最大回复数必须在1-100之间"}), 400
                
                # 读取现有的.env文件内容
                env_file_path = os.path.join(os.getcwd(), '.env')
                env_lines = []
                if os.path.exists(env_file_path):
                    try:
                        with open(env_file_path, 'r', encoding='utf-8') as f:
                            env_lines = f.readlines()
                    except Exception as e:
                        logger.warning(f"读取.env文件失败: {e}")
                
                # 更新或添加配置项
                config_updates = {
                    'REPLY_DELAY': str(reply_delay),
                    'MIN_REPLY_INTERVAL': str(min_reply_interval),
                    'MAX_MESSAGES_PER_HOUR': str(max_messages_per_hour)
                }
                
                # 处理现有配置
                updated_lines = []
                updated_keys = set()
                for line in env_lines:
                    line_stripped = line.strip()
                    if not line_stripped or line_stripped.startswith('#'):
                        updated_lines.append(line)
                        continue
                    
                    if '=' in line_stripped:
                        key = line_stripped.split('=')[0].strip()
                        if key in config_updates:
                            updated_lines.append(f"{key}={config_updates[key]}\n")
                            updated_keys.add(key)
                        else:
                            updated_lines.append(line)
                    else:
                        updated_lines.append(line)
                
                # 添加新配置项
                for key, value in config_updates.items():
                    if key not in updated_keys:
                        updated_lines.append(f"{key}={value}\n")
                
                # 写入.env文件
                try:
                    with open(env_file_path, 'w', encoding='utf-8') as f:
                        f.writelines(updated_lines)
                    
                    # 重新加载环境变量
                    from dotenv import load_dotenv
                    load_dotenv(override=True)
                    
                    # 重新导入配置以更新
                    import importlib
                    import config
                    importlib.reload(config)
                    
                    # 更新bot实例的自动回复设置
                    if self.bot and self.bot.auto_reply:
                        # 这些设置会在下次收到消息时生效
                        pass
                    
                    logger.info(f"AI回复节奏设置已保存到 {env_file_path}")
                    return jsonify({
                        "success": True,
                        "message": "AI回复节奏设置已保存成功！设置将在下次收到消息时生效。"
                    })
                except Exception as e:
                    logger.error(f"保存.env文件失败: {e}")
                    return jsonify({"success": False, "message": f"保存配置文件失败: {str(e)}"}), 500
                    
            except Exception as e:
                logger.error(f"保存AI回复节奏设置错误: {e}")
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/add_daily_content', methods=['POST'])
        def add_daily_content():
            """添加日程（功能已禁用）"""
            return jsonify({
                "success": False,
                "message": "日程管理功能已禁用"
            }), 400
        
        @self.app.route('/api/get_daily_contents', methods=['GET'])
        def get_daily_contents():
            """获取日程内容（功能已禁用）"""
            return jsonify({
                "success": True,
                "contents": [],
                "message": "日程管理功能已禁用"
            })
        
        @self.app.route('/api/delete_daily_content', methods=['POST'])
        def delete_daily_content():
            """删除日程（功能已禁用）"""
            return jsonify({
                "success": False,
                "message": "日程管理功能已禁用"
            }), 400
        
        @self.app.route('/api/start_bot', methods=['POST'])
        def start_bot():
            try:
                if not self.bot.client.is_logged_in:
                    return jsonify({"success": False, "message": "请先登录后再启动机器人"}), 400
                
                self.bot.start()
                return jsonify({"success": True, "message": "机器人已启动"})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/stop_bot', methods=['POST'])
        def stop_bot():
            try:
                self.bot.stop()
                return jsonify({"success": True, "message": "机器人已停止"})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)}), 500
        
        @self.app.route('/api/chat_list', methods=['GET'])
        def get_chat_list():
            """获取聊天列表"""
            try:
                import sqlite3
                conn = sqlite3.connect(self.bot.db.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # 获取所有有消息的聊天
                cursor.execute('''
                    SELECT DISTINCT chat_id, contact_name, 
                           MAX(timestamp) as last_time,
                           (SELECT message_text FROM messages m2 
                            WHERE m2.chat_id = m.chat_id 
                            ORDER BY m2.timestamp DESC LIMIT 1) as last_message,
                           (SELECT is_group FROM messages m3 
                            WHERE m3.chat_id = m.chat_id 
                            LIMIT 1) as is_group
                    FROM messages m
                    GROUP BY chat_id, contact_name
                    ORDER BY last_time DESC
                    LIMIT 50
                ''')
                
                rows = cursor.fetchall()
                conn.close()
                
                # 获取自动回复配置
                from dotenv import load_dotenv
                load_dotenv(override=True)
                import importlib
                import config
                importlib.reload(config)
                from config import AUTO_REPLY_ENABLED, LISTEN_CONTACTS, SPECIFIC_CONTACTS, REPLY_TO_ALL_CONTACTS
                
                # 清理联系人列表（去除空字符串和空格）
                specific_contacts_clean = [c.strip() for c in SPECIFIC_CONTACTS if c.strip()]
                
                chats = []
                existing_names = set()
                for row in rows:
                    contact_name = row['contact_name'] or row['chat_id']
                    contact_name_clean = contact_name.strip() if contact_name else ""
                    is_group = bool(row['is_group']) if row['is_group'] is not None else False
                    
                    # 跳过群组消息
                    if is_group:
                        continue
                    
                    # 记录已有的联系人名称，避免后面重复添加
                    if contact_name_clean:
                        existing_names.add(contact_name_clean.lower())
                    
                    # 判断该联系人是否配置了自动回复
                    auto_reply_enabled = False
                    if AUTO_REPLY_ENABLED:
                        # 联系人判断
                        if LISTEN_CONTACTS:
                            if REPLY_TO_ALL_CONTACTS:
                                # 如果设置为回复所有联系人
                                auto_reply_enabled = True
                            else:
                                # 如果设置为只回复指定联系人，检查是否在列表中
                                if specific_contacts_clean:
                                    for contact in specific_contacts_clean:
                                        if contact.lower() == contact_name_clean.lower():
                                            auto_reply_enabled = True
                                            break
                    
                    chats.append({
                        "chat_id": row['chat_id'],
                        "contact_name": contact_name,
                        "last_message": row['last_message'] or "",
                        "last_time": row['last_time'],
                        "is_group": False,
                        "auto_reply_enabled": auto_reply_enabled
                    })
                
                # === 额外补充：根据配置的指定联系人，生成"虚拟聊天项" ===
                # 这样即使当前数据库中还没有该联系人的消息，也可以在聊天窗口中看到并点击进入
                if AUTO_REPLY_ENABLED:
                    # 补充联系人
                    if LISTEN_CONTACTS and not REPLY_TO_ALL_CONTACTS and specific_contacts_clean:
                        for name in specific_contacts_clean:
                            name_clean = name.strip()
                            if not name_clean:
                                continue
                            # 如果数据库中已经有记录，则不重复添加
                            if name_clean.lower() in existing_names:
                                continue
                            
                            chats.append({
                                "chat_id": name_clean,
                                "contact_name": name_clean,
                                "last_message": "",
                                "last_time": None,
                                "is_group": False,
                                "auto_reply_enabled": True  # 在指定联系人列表中，且自动回复已启用
                            })
                
                return jsonify({"success": True, "chats": chats})
            except Exception as e:
                logger.error(f"获取聊天列表错误: {e}")
                return jsonify({"success": False, "message": str(e), "chats": []}), 500
        
        @self.app.route('/api/chat_messages', methods=['GET'])
        def get_chat_messages():
            """获取聊天消息"""
            try:
                chat_id = request.args.get('chat_id')
                if not chat_id:
                    return jsonify({"success": False, "message": "缺少chat_id参数"}), 400
                
                # 获取联系人信息
                import sqlite3
                conn = sqlite3.connect(self.bot.db.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT contact_name, is_group 
                    FROM messages 
                    WHERE chat_id = ? 
                    LIMIT 1
                ''', (chat_id,))
                contact_row = cursor.fetchone()
                conn.close()
                
                contact_name = contact_row['contact_name'] if contact_row else chat_id
                is_group = bool(contact_row['is_group']) if contact_row and contact_row['is_group'] is not None else False
                
                # 获取自动回复配置
                from dotenv import load_dotenv
                load_dotenv(override=True)
                import importlib
                import config
                importlib.reload(config)
                from config import AUTO_REPLY_ENABLED, LISTEN_CONTACTS, SPECIFIC_CONTACTS, REPLY_TO_ALL_CONTACTS
                
                # 清理联系人列表（去除空字符串和空格）
                specific_contacts_clean = [c.strip() for c in SPECIFIC_CONTACTS if c.strip()]
                contact_name_clean = contact_name.strip() if contact_name else ""
                
                # 判断该联系人是否配置了自动回复
                auto_reply_enabled = False
                if AUTO_REPLY_ENABLED:
                    # 不处理群组消息
                    if is_group:
                        auto_reply_enabled = False
                    else:
                        if LISTEN_CONTACTS:
                            if REPLY_TO_ALL_CONTACTS:
                                # 如果设置为回复所有联系人
                                auto_reply_enabled = True
                            else:
                                # 如果设置为只回复指定联系人，检查是否在列表中
                                if specific_contacts_clean:
                                    for contact in specific_contacts_clean:
                                        if contact.lower() == contact_name_clean.lower():
                                            auto_reply_enabled = True
                                            break
                
                messages = self.bot.db.get_message_history(chat_id, limit=100)
                
                # 确保每条消息都有翻译
                translator = Translator()
                for msg in messages:
                    message_text = msg.get('message_text', '')
                    translated_text = msg.get('translated_text', '')
                    is_sent = msg.get('is_sent', False)
                    
                    if is_sent:
                        # 发送的消息：message_text是翻译后的，translated_text是原文（中文）
                        # 如果translated_text为空，说明可能是旧数据，尝试从message_text推断
                        if not translated_text and message_text:
                            # 假设message_text可能是翻译后的，尝试翻译回中文
                            try:
                                # 检测是否为中文，如果不是则翻译
                                if not any('\u4e00' <= char <= '\u9fff' for char in message_text):
                                    # 不是中文，尝试翻译成中文作为原文
                                    translated_text = translator.translate_to_chinese(message_text)
                                    if translated_text and translated_text != message_text:
                                        msg['translated_text'] = translated_text
                            except Exception as e:
                                logger.debug(f"翻译发送消息失败: {e}")
                                msg['translated_text'] = message_text
                    else:
                        # 接收的消息：message_text是原文，translated_text应该是中文翻译
                        if not translated_text and message_text:
                            try:
                                # 检测是否为中文
                                is_chinese = any('\u4e00' <= char <= '\u9fff' for char in message_text)
                                if not is_chinese:
                                    # 不是中文，翻译成中文
                                    translated = translator.translate_to_chinese(message_text)
                                    if translated and translated != message_text:
                                        msg['translated_text'] = translated
                                        # 更新数据库
                                        import sqlite3
                                        conn = sqlite3.connect(self.bot.db.db_path)
                                        cursor = conn.cursor()
                                        cursor.execute('''
                                            UPDATE messages SET translated_text = ? 
                                            WHERE message_id = ?
                                        ''', (translated, msg.get('message_id')))
                                        conn.commit()
                                        conn.close()
                                else:
                                    # 已经是中文，不需要翻译
                                    msg['translated_text'] = message_text
                            except Exception as e:
                                logger.debug(f"翻译接收消息失败: {e}")
                                msg['translated_text'] = msg.get('message_text', '')
                        elif not translated_text:
                            msg['translated_text'] = msg.get('message_text', '')
                
                return jsonify({
                    "success": True, 
                    "messages": messages,
                    "contact_name": contact_name,
                    "is_group": is_group,
                    "auto_reply_enabled": auto_reply_enabled
                })
            except Exception as e:
                logger.error(f"获取聊天消息错误: {e}")
                return jsonify({"success": False, "message": str(e), "messages": []}), 500
    
    def run(self, host='127.0.0.1', port=5000, debug=False, open_browser=True):
        """运行服务器"""
        import socket
        
        def find_free_port(start_port, max_attempts=10):
            """查找可用端口"""
            for i in range(max_attempts):
                test_port = start_port + i
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind((host, test_port))
                        return test_port
                except OSError:
                    continue
            return None
        
        # 检查端口是否可用，如果不可用则尝试其他端口
        actual_port = port
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
        except OSError as e:
            logger.warning(f"端口 {port} 不可用: {e}")
            logger.info(f"正在尝试查找可用端口...")
            free_port = find_free_port(port)
            if free_port:
                actual_port = free_port
                logger.info(f"找到可用端口: {actual_port}")
            else:
                logger.error(f"无法找到可用端口（尝试了 {max_attempts} 个端口）")
                raise
        
        if open_browser:
            def open_browser_delayed():
                import time
                time.sleep(1.5)
                try:
                    webbrowser.open(f'http://{host}:{actual_port}')
                except Exception as e:
                    logger.debug(f"打开浏览器失败: {e}")
            
            threading.Thread(target=open_browser_delayed, daemon=True).start()
        
        try:
            logger.info(f"正在启动Web服务器: http://{host}:{actual_port}")
            self.app.run(host=host, port=actual_port, debug=debug, use_reloader=False)
        except OSError as e:
            logger.error(f"Web服务器启动失败: {e}")
            logger.error(f"可能的原因:")
            logger.error(f"  1. 端口 {actual_port} 已被占用")
            logger.error(f"  2. 权限不足（Windows可能需要管理员权限）")
            logger.error(f"  3. 防火墙阻止了端口访问")
            raise

