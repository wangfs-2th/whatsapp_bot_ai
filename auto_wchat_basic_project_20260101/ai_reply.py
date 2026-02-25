"""
AI回复模块 - 支持OpenAI和通义千问API生成智能回复
"""
import openai
import json
import logging
from typing import Optional, Dict, List, Tuple
import importlib

logger = logging.getLogger(__name__)

# 尝试导入通义千问SDK
try:
    import dashscope
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logger.warning("dashscope库未安装，无法使用通义千问模型。请运行: pip install dashscope")


def _get_config():
    """动态获取配置，确保每次都能获取最新值"""
    import config
    importlib.reload(config)
    return config


class AIReply:
    def __init__(self):
        config = _get_config()
        self.enabled = config.AI_ENABLED
        self.provider = getattr(config, 'AI_PROVIDER', 'openai').lower()
        
        if not self.enabled:
            self.client = None
            self.qwen_client = None
            logger.debug("AI功能未启用")
            return
        
        # 初始化OpenAI客户端
        if self.provider == 'openai' and config.OPENAI_API_KEY:
            try:
                self.client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
                self.qwen_client = None
            except Exception as e:
                logger.error(f"初始化OpenAI客户端失败: {e}")
                self.client = None
                self.qwen_client = None
        # 初始化通义千问客户端
        elif self.provider == 'qwen' and config.QWEN_API_KEY:
            if DASHSCOPE_AVAILABLE:
                try:
                    dashscope.api_key = config.QWEN_API_KEY
                    self.qwen_client = dashscope
                    self.client = None
                    logger.info("通义千问客户端初始化成功")
                except Exception as e:
                    logger.error(f"初始化通义千问客户端失败: {e}")
                    self.qwen_client = None
                    self.client = None
            else:
                logger.warning("dashscope库未安装，无法使用通义千问")
                self.qwen_client = None
                self.client = None
        else:
            self.client = None
            self.qwen_client = None
            if self.provider == 'openai' and not config.OPENAI_API_KEY:
                logger.warning("AI功能已启用但OpenAI API密钥未配置")
            elif self.provider == 'qwen' and not config.QWEN_API_KEY:
                logger.warning("AI功能已启用但通义千问API密钥未配置")
    
    def generate_reply(self, message: str, chat_history: List[Dict] = None, 
                      personality: str = None, context: str = None,
                      file_content: str = None) -> Tuple[Optional[str], Optional[str]]:
        """
        生成AI回复
        返回: (回复内容, 错误信息)
        """
        # 先检查是否可用，这会自动更新配置和客户端
        if not self.is_available():
            return None, "AI功能未启用或API密钥未配置"
        
        config = _get_config()
        try:
            system_personality = personality or config.AI_PERSONALITY
            # 获取聊天提示词（用于引导生成聊天风格的回复）
            chat_prompt = getattr(config, 'AI_CHAT_PROMPT', '')
            
            # 组合system message：人物特点 + 聊天提示词
            system_content = system_personality
            if chat_prompt:
                system_content = f"{system_personality}\n\n{chat_prompt}"
            logger.info(f"generate_reply中未赋值前打印的message: {message}")
            messages = [
                {"role": "system", "content": system_content}
            ]
            
            if file_content:
                messages.append({
                    "role": "system", 
                    "content": f"以下是可参考的知识库内容，请根据这些内容回答问题：\n\n{file_content[:2000]}"
                })
            
            if context:
                messages.append({"role": "system", "content": f"上下文信息: {context}"})
            """
            if chat_history:
                for hist in chat_history[-5:]:
                    logger.info(f"打印hist的内容: {hist}")
                    if hist.get('is_sent'):
                        messages.append({"role": "assistant", "content": hist.get('message_text', '')})
                    else:
                        messages.append({"role": "user", "content": hist.get('message_text', '')})
            """
            messages.append({"role": "user", "content": message})
            logger.info(f"发送给大模型的数据为：{messages}")
                # 根据提供商调用不同的API
            if self.provider == 'qwen' and self.qwen_client:
                # 使用通义千问API
                model = getattr(config, 'QWEN_MODEL', 'qwen-turbo')
                
                # 记录请求参数用于调试
                logger.debug(f"通义千问API请求 - 模型: {model}, 消息数量: {len(messages)}, 温度: {config.AI_TEMPERATURE}")
                
                try:
                    # 通义千问API调用 - 使用messages格式（新版本API支持）
                    # 注意：确保messages格式正确，每个消息包含role和content字段
                    response = dashscope.Generation.call(
                        model=model,
                        messages=messages,
                        temperature=config.AI_TEMPERATURE,
                        max_tokens=500,
                        result_format='message'  # 确保返回消息格式
                    )
                except Exception as e:
                    error_msg = f"通义千问API调用异常: {str(e)}"
                    logger.error(f"通义千问生成回复失败: {error_msg}", exc_info=True)
                    # 尝试使用prompt格式作为备用方案（某些旧版本模型可能需要）
                    try:
                        # 将messages转换为prompt格式
                        prompt_text = ""
                        for msg in messages:
                            role = msg.get('role', 'user')
                            content = msg.get('content', '')
                            if role == 'system':
                                prompt_text += f"系统提示: {content}\n\n"
                            elif role == 'user':
                                prompt_text += f"用户: {content}\n\n"
                            elif role == 'assistant':
                                prompt_text += f"助手: {content}\n\n"
                        
                        logger.info("尝试使用prompt格式调用通义千问API")
                        response = dashscope.Generation.call(
                            model=model,
                            prompt=prompt_text,
                            temperature=config.AI_TEMPERATURE,
                            max_tokens=500
                        )
                    except Exception as e2:
                        logger.error(f"使用prompt格式也失败: {e2}")
                        return None, error_msg
                
                # 记录响应信息用于调试
                logger.debug(f"通义千问API响应 - 状态码: {response.status_code}, 是否有output: {hasattr(response, 'output')}")
                if hasattr(response, 'output'):
                    logger.debug(f"通义千问API响应 - output类型: {type(response.output)}")
                    try:
                        logger.debug(f"通义千问API响应 - output内容: {response.output}")
                    except:
                        pass
                # 记录响应对象的其他属性
                if hasattr(response, 'code'):
                    logger.debug(f"通义千问API响应代码: {response.code}")
                if hasattr(response, 'message'):
                    logger.debug(f"通义千问API响应消息: {response.message}")
                if hasattr(response, 'request_id'):
                    logger.debug(f"通义千问API请求ID: {response.request_id}")
                
                # 检查响应状态
                if response.status_code == 200:
                    # 检查响应结构
                    if not hasattr(response, 'output') or response.output is None:
                        error_msg = "通义千问API返回数据为空，请检查API密钥和模型配置"
                        logger.error(f"通义千问生成回复失败: {error_msg}")
                        return None, error_msg
                    
                    if not hasattr(response.output, 'choices') or not response.output.choices:
                        # 记录详细的响应信息用于调试
                        logger.error(f"通义千问API响应结构: status_code={response.status_code}, has_output={hasattr(response, 'output')}")
                        if hasattr(response, 'output'):
                            try:
                                logger.error(f"通义千问API output内容: {response.output}")
                                logger.error(f"通义千问API output类型: {type(response.output)}")
                                logger.error(f"通义千问API output属性: {dir(response.output)}")
                            except Exception as e:
                                logger.error(f"无法记录output详细信息: {e}")
                        if hasattr(response, 'code'):
                            logger.error(f"通义千问API错误代码: {response.code}")
                        if hasattr(response, 'message'):
                            logger.error(f"通义千问API错误消息: {response.message}")
                        if hasattr(response, 'request_id'):
                            logger.error(f"通义千问API请求ID: {response.request_id}")
                        error_msg = "通义千问API返回的choices为空，请检查：1) API密钥是否正确 2) 模型名称是否正确 3) 账户是否有余额 4) 请求参数格式是否正确"
                        return None, error_msg
                    
                    if len(response.output.choices) == 0:
                        error_msg = "通义千问API返回的choices列表为空"
                        logger.error(f"通义千问生成回复失败: {error_msg}")
                        return None, error_msg
                    
                    choice = response.output.choices[0]
                    
                    # 处理不同的响应格式
                    reply = None
                    if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                        # messages格式的响应
                        reply = choice.message.content.strip()
                    elif hasattr(choice, 'text'):
                        # prompt格式的响应（某些旧版本）
                        reply = choice.text.strip()
                    elif hasattr(choice, 'content'):
                        # 直接content字段
                        reply = choice.content.strip()
                    else:
                        error_msg = f"通义千问API返回的消息格式不正确，choice对象: {choice}"
                        logger.error(f"通义千问生成回复失败: {error_msg}")
                        return None, error_msg
                    
                    if not reply:
                        error_msg = "通义千问API返回的回复内容为空"
                        logger.error(f"通义千问生成回复失败: {error_msg}")
                        return None, error_msg
                    
                    logger.info(f"通义千问生成回复成功: {reply[:100]}...")
                    return reply, None
                else:
                    # 处理错误响应
                    error_code = getattr(response, 'code', None)
                    error_msg_text = getattr(response, 'message', None)
                    
                    # 尝试从响应中获取更多错误信息
                    if not error_msg_text and hasattr(response, 'output'):
                        if hasattr(response.output, 'message'):
                            error_msg_text = response.output.message
                    
                    if not error_msg_text:
                        error_msg_text = f"HTTP {response.status_code}"
                    
                    # 处理通义千问的错误
                    if error_code == 'InvalidApiKey' or 'InvalidApiKey' in str(error_msg_text):
                        error_msg = "通义千问API密钥无效，请检查配置的API密钥是否正确"
                    elif error_code == 'InsufficientBalance' or 'InsufficientBalance' in str(error_msg_text) or '余额' in str(error_msg_text):
                        error_msg = "通义千问账户余额不足，请检查账户余额"
                    elif response.status_code == 429 or '429' in str(response.status_code) or 'rate limit' in str(error_msg_text).lower():
                        error_msg = "通义千问API请求频率超限，请稍后再试"
                    elif response.status_code == 401 or '401' in str(response.status_code):
                        error_msg = "通义千问API密钥无效或已过期，请检查API密钥"
                    elif response.status_code == 403 or '403' in str(response.status_code):
                        error_msg = "通义千问API访问被拒绝，请检查API密钥权限"
                    else:
                        error_msg = f"通义千问API错误（状态码: {response.status_code}）: {error_msg_text}"
                    
                    logger.error(f"通义千问生成回复失败: {error_msg}")
                    return None, error_msg
            else:
                # 使用OpenAI API
                model = config.OPENAI_MODEL
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=config.AI_TEMPERATURE,
                    max_tokens=500
                )
                
                reply = response.choices[0].message.content.strip()
                logger.info(f"OpenAI生成回复成功: {reply[:100]}...")
                return reply, None
        
        except openai.RateLimitError as e:
            error_msg = "API请求频率超限，请稍后再试"
            logger.error(f"AI生成回复失败（频率限制）: {e}")
            return None, error_msg
        except openai.APIError as e:
            # 处理各种API错误
            error_code = getattr(e, 'code', None)
            error_type = getattr(e, 'type', None)
            error_body = getattr(e, 'body', {})
            
            # 尝试从错误体中获取更详细的信息
            if isinstance(error_body, dict):
                error_detail = error_body.get('error', {})
                if isinstance(error_detail, dict):
                    error_type = error_type or error_detail.get('type')
                    if not error_code:
                        # 尝试从状态码获取
                        status_code = getattr(e, 'status_code', None)
                        if status_code:
                            error_code = status_code
            
            # 获取状态码和错误消息字符串
            status_code = getattr(e, 'status_code', None)
            error_str = str(e).lower()
            
            # 优先检查错误消息字符串和类型，因为错误信息可能包含关键信息
            if 'insufficient_quota' in error_str or error_type == 'insufficient_quota' or error_code == 'insufficient_quota' or 'quota' in error_str:
                error_msg = "API配额已用完，请检查您的OpenAI账户余额和订阅计划。详情请访问：https://platform.openai.com/account/billing"
            elif status_code == 429 or error_code == 429 or '429' in str(e) or 'rate limit' in error_str:
                error_msg = "API请求频率超限，请稍后再试"
            elif status_code == 401 or error_code == 401 or '401' in str(e):
                error_msg = "API密钥无效，请检查配置的OpenAI API密钥是否正确"
            elif status_code == 403 or error_code == 403 or '403' in str(e):
                error_msg = "API访问被拒绝，请检查API密钥权限"
            elif status_code == 500 or error_code == 500 or '500' in str(e):
                error_msg = "OpenAI服务器错误，请稍后再试"
            elif status_code == 503 or error_code == 503 or '503' in str(e):
                error_msg = "OpenAI服务暂时不可用，请稍后再试"
            else:
                error_msg = f"API错误（状态码: {status_code or '未知'}, 错误代码: {error_code or '未知'}）: {str(e)[:200]}"
            
            logger.error(f"AI生成回复失败（API错误 {error_code}，类型: {error_type}）: {e}")
            return None, error_msg
        except Exception as e:
            error_msg = f"AI生成回复失败: {str(e)}"
            logger.error(f"AI生成回复失败: {e}", exc_info=True)
            return None, error_msg
    
    def set_personality(self, personality: str):
        """设置AI人物特点"""
        config = _get_config()
        config.AI_PERSONALITY = personality
        logger.info(f"AI人物特点已更新: {personality}")
    
    def is_available(self) -> bool:
        """检查AI功能是否可用 - 动态检查最新配置"""
        config = _get_config()
        # 如果配置已更改，更新实例状态
        if self.enabled != config.AI_ENABLED:
            self.enabled = config.AI_ENABLED
        
        provider = getattr(config, 'AI_PROVIDER', 'openai').lower()
        
        # 根据提供商检查可用性
        if config.AI_ENABLED:
            if provider == 'qwen':
                if config.QWEN_API_KEY and DASHSCOPE_AVAILABLE:
                    if self.qwen_client is None:
                        try:
                            dashscope.api_key = config.QWEN_API_KEY
                            self.qwen_client = dashscope
                        except Exception as e:
                            logger.error(f"初始化通义千问客户端失败: {e}")
                            self.qwen_client = None
                    return self.qwen_client is not None
                else:
                    self.qwen_client = None
                    return False
            else:  # openai
                if config.OPENAI_API_KEY:
                    if self.client is None:
                        try:
                            self.client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
                        except Exception as e:
                            logger.error(f"初始化OpenAI客户端失败: {e}")
                            self.client = None
                    return self.client is not None
                else:
                    self.client = None
                    return False
        else:
            self.client = None
            self.qwen_client = None
            return False


class LocalContentReply:
    """本地内容回复模块"""
    
    def __init__(self, content_path: str = "local_replies.json"):
        self.content_path = content_path
        self.content_data = self.load_content()
    
    def load_content(self) -> Dict:
        """加载本地内容文件"""
        try:
            with open(self.content_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"本地内容文件不存在: {self.content_path}，将创建默认文件")
            default_content = {"replies": {}, "patterns": []}
            self.save_content(default_content)
            return default_content
        except Exception as e:
            logger.error(f"加载本地内容失败: {e}")
            return {}
    
    def save_content(self, content: Dict = None):
        """保存本地内容文件"""
        try:
            with open(self.content_path, 'w', encoding='utf-8') as f:
                json.dump(content or self.content_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存本地内容失败: {e}")
    
    def get_reply(self, message: str) -> Optional[str]:
        """根据消息内容获取本地回复"""
        message_lower = message.lower()
        
        if message_lower in self.content_data.get("replies", {}):
            return self.content_data["replies"][message_lower]
        
        for pattern in self.content_data.get("patterns", []):
            keyword = pattern.get("keyword", "").lower()
            if keyword in message_lower:
                return pattern.get("reply", "")
        
        return None
    
    def add_reply(self, keyword: str, reply: str):
        """添加关键词回复"""
        if "replies" not in self.content_data:
            self.content_data["replies"] = {}
        self.content_data["replies"][keyword.lower()] = reply
        self.save_content()
    
    def add_pattern(self, keyword: str, reply: str):
        """添加模式匹配回复"""
        if "patterns" not in self.content_data:
            self.content_data["patterns"] = []
        
        self.content_data["patterns"].append({
            "keyword": keyword,
            "reply": reply
        })
        self.save_content()



