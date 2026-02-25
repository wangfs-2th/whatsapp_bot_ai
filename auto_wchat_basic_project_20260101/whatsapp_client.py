"""
WhatsApp客户端 - 使用selenium实现，添加反检测措施降低封号风险
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging
import qrcode
import platform
import os
import shutil
import re
from io import BytesIO
from PIL import Image
import base64
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Dict
from config import (
    CHROME_PROFILE_PATH, HEADLESS_MODE, USER_AGENT,
    WHATSAPP_WEB_URL, MIN_REPLY_INTERVAL
)

logger = logging.getLogger(__name__)
# 确保 whatsapp_client 的日志级别正确
logger.setLevel(logging.INFO)
# 确保日志传播到根日志记录器（这样 main.py 中的 StreamHandler 才能捕获）
logger.propagate = True


class WhatsAppClient:
    def __init__(self):
        self.driver = None
        self.is_logged_in = False
        self.message_handlers: List[Callable] = []
        self.last_reply_time = {}
        self.min_reply_interval = MIN_REPLY_INTERVAL
        self.user_name = None  # 登录账号的昵称
        import threading
        self.message_lock = threading.Lock()  # 添加锁，防止多联系人并发冲突

    def get_user_name(self) -> Optional[str]:
        """获取登录账号的昵称（从设置页面获取）"""
        if self.user_name:
            return self.user_name
        
        if not self.driver or not self.is_logged_in:
            return None
        
        try:
            # 方法1: 从设置页面获取账号昵称（最可靠）
            try:
                # 第一步：点击设置按钮
                logger.info("🔍 正在查找设置按钮...")
                settings_selectors = [
                    'button[aria-label="设置"]',
                    'button[data-navbar-item="true"][data-navbar-item-index="3"]',
                    'button[aria-label="设置"][data-navbar-item="true"]',
                    'button.xjb2p0i[aria-label="设置"]',
                ]
                
                settings_button = None
                for selector in settings_selectors:
                    try:
                        settings_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        if settings_button and settings_button.is_displayed():
                            logger.info(f"✅ 找到设置按钮: {selector}")
                            break
                    except:
                        continue
                
                if not settings_button:
                    logger.warning("⚠️  未找到设置按钮，尝试其他方法")
                    raise Exception("未找到设置按钮")
                
                # 点击设置按钮
                try:
                    settings_button.click()
                    logger.info("✅ 已点击设置按钮")
                    time.sleep(1.5)  # 等待设置页面加载
                except Exception as e:
                    # 如果普通点击失败，尝试使用JavaScript点击
                    try:
                        self.driver.execute_script("arguments[0].click();", settings_button)
                        logger.info("✅ 已使用JavaScript点击设置按钮")
                        time.sleep(1.5)
                    except Exception as e2:
                        logger.warning(f"⚠️  点击设置按钮失败: {e2}")
                        raise
                
                # 第二步：获取账号昵称
                logger.info("🔍 正在从设置页面获取账号昵称...")
                name_selectors = [
                    'span[title][dir="auto"].x1iyjqo2',
                    'span.x1iyjqo2[dir="auto"][title]',
                    'span[title].x1iyjqo2.x6ikm8r.x10wlt62',
                    'span._ao3e[title][dir="auto"]',
                    'span[title][dir="auto"]',
                ]
                
                account_name = None
                for selector in name_selectors:
                    try:
                        name_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in name_elements:
                            # 优先从title属性获取
                            title = element.get_attribute('title')
                            if title and title.strip():
                                account_name = title.strip()
                                logger.info(f"✅ 从title属性获取到账号昵称: {account_name}")
                                break
                            
                            # 如果title为空，尝试从文本内容获取
                            text = element.text.strip()
                            if text and len(text) > 0 and len(text) < 50:  # 限制长度，避免获取到其他文本
                                account_name = text
                                logger.info(f"✅ 从文本内容获取到账号昵称: {account_name}")
                                break
                        
                        if account_name:
                            break
                    except:
                        continue
                
                if account_name:
                    self.user_name = account_name
                    logger.info(f"✅ 成功获取账号昵称: {account_name}")
                    
                    # 关闭设置页面（点击返回或点击聊天列表）
                    try:
                        # 尝试点击返回按钮或点击聊天列表
                        back_selectors = [
                            'button[aria-label="返回"]',
                            'button[aria-label="Back"]',
                            'div[data-testid="chat-list"]',
                            'button[data-navbar-item="true"][data-navbar-item-index="0"]',  # 聊天列表按钮
                        ]
                        for back_selector in back_selectors:
                            try:
                                back_button = WebDriverWait(self.driver, 2).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, back_selector))
                                )
                                if back_button and back_button.is_displayed():
                                    back_button.click()
                                    logger.info("✅ 已关闭设置页面")
                                    time.sleep(0.5)
                                    break
                            except:
                                continue
                    except:
                        pass  # 如果无法关闭设置页面，继续执行
                    
                    return self.user_name
                else:
                    logger.info("⚠️  从设置页面未找到账号昵称，尝试其他方法")
                    raise Exception("从设置页面未找到账号昵称")
                    
            except Exception as e:
                logger.info(f"⚠️  从设置页面获取账号昵称失败: {e}，尝试备用方法")
            
            # 方法2: 从所有消息中提取账号昵称，通过统计出现频率最高的发送者名称（备用方法）
            copyable_texts = self.driver.find_elements(By.CSS_SELECTOR, 'div.copyable-text[data-pre-plain-text]')
            sender_counts = {}
            sender_positions = {}  # 记录每个发送者的消息位置（用于判断是否在右侧）
            
            for copyable_text in copyable_texts:
                try:
                    pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                    if pre_plain_text:
                        # 格式: "[16:37, 2025年12月18日] Freya: " 或 "[16:37, 12/18/2025] Freya: "
                        # 提取发送者名称（冒号前的部分）
                        match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                        if match:
                            sender_name = match.group(1).strip()
                            if sender_name:
                                sender_counts[sender_name] = sender_counts.get(sender_name, 0) + 1
                                
                                # 同时检查消息位置（发送的消息通常在右侧）
                                try:
                                    parent = copyable_text.find_element(By.XPATH, './ancestor::div[@role="row"][1]')
                                    location = parent.location
                                    size = parent.size
                                    window_width = self.driver.execute_script("return window.innerWidth;")
                                    # 如果消息在右侧（x + 宽度 > 窗口宽度 * 0.6），记录为右侧消息
                                    is_right_side = location['x'] + size['width'] > window_width * 0.6
                                    if sender_name not in sender_positions:
                                        sender_positions[sender_name] = {'right': 0, 'left': 0}
                                    if is_right_side:
                                        sender_positions[sender_name]['right'] += 1
                                    else:
                                        sender_positions[sender_name]['left'] += 1
                                except:
                                    pass
                except:
                    continue
            
            # 优先选择右侧消息最多的发送者（通常是账号自己）
            if sender_positions:
                best_sender = None
                best_right_ratio = 0
                for sender_name, positions in sender_positions.items():
                    total = positions['right'] + positions['left']
                    if total > 0:
                        right_ratio = positions['right'] / total
                        # 如果右侧消息比例 > 0.7，很可能是账号自己
                        if right_ratio > best_right_ratio and right_ratio > 0.7:
                            best_right_ratio = right_ratio
                            best_sender = sender_name
                
                if best_sender:
                    self.user_name = best_sender
                    logger.info(f"✅ 检测到登录账号昵称: {best_sender} (右侧消息比例: {best_right_ratio:.2%})")
                    return self.user_name
            
            # 方法3: 如果方法2失败，选择出现频率最高的发送者
            if sender_counts:
                sorted_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)
                if len(sorted_senders) > 0:
                    most_common_sender, count = sorted_senders[0]
                    # 如果最高频率的发送者出现次数 >= 2，或者只有一个发送者，则认为是账号昵称
                    if count >= 2 or len(sorted_senders) == 1:
                        self.user_name = most_common_sender
                        logger.info(f"✅ 检测到登录账号昵称: {most_common_sender} (出现 {count} 次)")
                        return self.user_name
            
            # 方法4: 如果方法2和3都失败，尝试从最近发送的消息中提取（通过位置判断）
            messages = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="row"]')
            for message in reversed(messages[-20:]):  # 检查最近20条消息
                try:
                    copyable_text = message.find_element(By.CSS_SELECTOR, 'div.copyable-text[data-pre-plain-text]')
                    pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                    match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                    if match:
                        sender_name = match.group(1).strip()
                        if sender_name:
                            # 检查消息位置（发送的消息通常在右侧）
                            try:
                                location = message.location
                                size = message.size
                                window_width = self.driver.execute_script("return window.innerWidth;")
                                # 如果消息在右侧（x + 宽度 > 窗口宽度 * 0.6），可能是发送的消息
                                if location['x'] + size['width'] > window_width * 0.6:
                                    self.user_name = sender_name
                                    logger.info(f"✅ 检测到登录账号昵称: {sender_name} (通过位置判断)")
                                    return self.user_name
                            except:
                                pass
                except:
                    continue
            
            logger.info("⚠️  未能检测到登录账号昵称")
            return None
        except Exception as e:
            logger.error(f"获取账号昵称时出错: {e}")
            return None

    def refresh_login_status(self) -> bool:
        """通过检查页面元素刷新当前是否已登录的状态"""
        if not self.driver:
            return False
        try:
            current_url = ""
            try:
                current_url = self.driver.current_url
            except:
                pass
            
            # 首先检查是否在 WhatsApp Web 页面
            if current_url and "web.whatsapp.com" not in current_url:
                # 不在 WhatsApp Web 页面，无法判断登录状态
                return self.is_logged_in
            
            # 方法1: 检查是否有二维码（最可靠的未登录标志）
            # 如果找到二维码，明确说明未登录
            try:
                qr_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                    'canvas[aria-label*="二维码"], canvas[aria-label*="QR"], div[data-ref]')
                if qr_elements:
                    # 检查二维码是否可见（可能在页面中但被隐藏）
                    for qr in qr_elements:
                        if qr.is_displayed():
                            if self.is_logged_in:
                                logger.info("检测到二维码，更新登录状态为未登录")
                            self.is_logged_in = False
                            return False
            except:
                pass
            
            # 方法2: 检查聊天项容器（更稳定的选择器）
            # WhatsApp Web 登录后，侧边栏会有聊天项容器
            try:
                # 新版 WhatsApp Web 中，聊天列表项通常是 role="gridcell" 的 div
                chat_items = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="gridcell"]')
                if chat_items and len(chat_items) > 0:
                    # 找到聊天项，说明已登录
                    if not self.is_logged_in:
                        logger.info("检测到WhatsApp已登录（通过聊天项容器），更新登录状态标记")
                    self.is_logged_in = True
                    return True
            except:
                pass
            
            # 方法3: 检查消息输入框（已登录页面会有消息输入框）
            try:
                input_box = self._find_message_input_box(timeout=3)
                if input_box:
                    if not self.is_logged_in:
                        logger.info("检测到WhatsApp已登录（通过消息输入框），更新登录状态标记")
                    self.is_logged_in = True
                    return True
            except:
                pass
            
            # 方法4: 检查侧边栏搜索框（登录后会有搜索框）
            try:
                search_box = self.driver.find_element(By.CSS_SELECTOR, 
                    'div[contenteditable="true"][data-tab="3"], div[contenteditable="true"][role="textbox"][placeholder*="搜索"]')
                if search_box and search_box.is_displayed():
                    if not self.is_logged_in:
                        logger.info("检测到WhatsApp已登录（通过搜索框），更新登录状态标记")
                    self.is_logged_in = True
                    return True
            except:
                pass
            
            # 方法5: 检查聊天列表元素（作为备用，可能不稳定）
            try:
                chat_list = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list"]')
                if chat_list and chat_list.is_displayed():
                    if not self.is_logged_in:
                        logger.info("检测到WhatsApp已登录（通过聊天列表），更新登录状态标记")
                    self.is_logged_in = True
                    return True
            except:
                pass
            
            # 方法6: 检查页面标题或特定文本
            try:
                page_title = self.driver.title
                if page_title and ("WhatsApp" in page_title or "WhatsApp Web" in page_title):
                    # 如果页面标题包含 WhatsApp，且没有二维码，可能是已登录
                    # 但为了安全，需要其他证据
                    pass
            except:
                pass
            
            # 如果所有方法都检测不到登录状态，保持当前状态不变
            # 不要轻易设置为False，因为可能是页面正在加载
            return self.is_logged_in
            
        except Exception as e:
            logger.debug(f"刷新登录状态时出错: {e}")
            # 出错时保持当前状态，不改变
            return self.is_logged_in
        
    def init_driver(self):
        """初始化浏览器驱动（添加反检测措施）"""
        chrome_options = Options()
        
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument(f'user-agent={USER_AGENT}')
        
        if CHROME_PROFILE_PATH:
            chrome_options.add_argument(f'user-data-dir={CHROME_PROFILE_PATH}')
        
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # 禁用不必要的服务和功能，减少错误日志
        chrome_options.add_argument('--disable-background-networking')  # 禁用后台网络请求（包括GCM）
        chrome_options.add_argument('--disable-sync')  # 禁用同步功能
        chrome_options.add_argument('--disable-default-apps')  # 禁用默认应用
        chrome_options.add_argument('--disable-background-timer-throttling')  # 禁用后台定时器节流
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')  # 禁用被遮挡窗口的后台处理
        chrome_options.add_argument('--disable-breakpad')  # 禁用崩溃报告
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')  # 禁用有后台页面的组件扩展
        chrome_options.add_argument('--disable-features=TranslateUI')  # 禁用翻译UI
        chrome_options.add_argument('--disable-ipc-flooding-protection')  # 禁用IPC洪水保护
        chrome_options.add_argument('--no-first-run')  # 不运行首次运行向导
        chrome_options.add_argument('--disable-features=ChromeWhatsNewUI')  # 禁用Chrome新功能UI
        chrome_options.add_argument('--disable-features=MediaRouter')  # 禁用媒体路由器
        chrome_options.add_argument('--disable-features=AudioServiceOutOfProcess')  # 禁用音频服务
        chrome_options.add_argument('--disable-logging')  # 禁用日志记录（减少控制台输出）
        chrome_options.add_argument('--log-level=3')  # 设置日志级别为ERROR（只显示错误）
        chrome_options.add_argument('--silent')  # 静默模式
        
        # 修复Windows上的ChromeDriver兼容性问题
        try:
            # 在Windows上，确保使用正确的ChromeDriver版本
            if platform.system() == 'Windows':
                # 清除可能损坏的缓存
                cache_path = os.path.join(os.path.expanduser('~'), '.wdm', 'drivers', 'chromedriver')
                if os.path.exists(cache_path):
                    try:
                        for root, dirs, files in os.walk(cache_path):
                            for f in files:
                                try:
                                    os.remove(os.path.join(root, f))
                                except:
                                    pass
                    except:
                        pass
                
                # 使用ChromeDriverManager，但添加错误处理
                try:
                    driver_path = ChromeDriverManager().install()
                    # 验证文件是否存在且可执行
                    if not os.path.exists(driver_path):
                        raise FileNotFoundError(f"ChromeDriver not found at {driver_path}")
                    service = Service(driver_path)
                except Exception as e:
                    logger.warning(f"ChromeDriverManager安装失败: {e}，尝试使用系统PATH中的chromedriver")
                    # 回退到使用系统PATH中的chromedriver
                    service = Service()
            else:
                service = Service(ChromeDriverManager().install())
            
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.error(f"初始化Chrome驱动失败: {e}")
            # 最后的回退方案：尝试不使用Service
            try:
                logger.info("尝试使用默认Chrome驱动...")
                self.driver = webdriver.Chrome(options=chrome_options)
            except Exception as e2:
                logger.error(f"所有Chrome驱动初始化方法都失败: {e2}")
                raise Exception(f"无法初始化Chrome浏览器驱动。请确保已安装Chrome浏览器，并且ChromeDriver版本与Chrome浏览器版本匹配。错误详情: {e2}")
        
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            '''
        })
        
        logger.info("浏览器驱动初始化成功")
    
    def login(self, phone_number: Optional[str] = None) -> bool:
        """登录WhatsApp"""
        if not self.driver:
            self.init_driver()
        
        try:
            self.driver.get(WHATSAPP_WEB_URL)
            time.sleep(3)
            
            if phone_number:
                return self._login_with_phone(phone_number)
            else:
                return self._login_with_qr()
        
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False
    
    def _login_with_phone(self, phone_number: str) -> bool:
        """使用电话号码登录"""
        try:
            phone_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="tel"]'))
            )
            phone_input.send_keys(phone_number)
            phone_input.send_keys(Keys.RETURN)
            
            time.sleep(5)
            logger.info("请输入验证码...")
            
            # 等待登录成功，使用多种选择器确保检测到登录
            WebDriverWait(self.driver, 120).until(
                lambda driver: any([
                    len(driver.find_elements(By.CSS_SELECTOR, 'div[role="gridcell"]')) > 0,
                    len(driver.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"][role="textbox"][data-tab="10"]')) > 0,
                    len(driver.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="10"]')) > 0,
                    len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="chat-list"]')) > 0
                ])
            )
            
            self.is_logged_in = True
            logger.info("电话号码登录成功")
            return True
        
        except Exception as e:
            logger.error(f"电话号码登录失败: {e}")
            return False
    
    def _login_with_qr(self) -> bool:
        """使用二维码登录"""
        try:
            qr_element = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[aria-label*="二维码"], canvas[aria-label*="QR"]'))
            )
            
            logger.info("请使用WhatsApp扫描二维码...")
            
            # 等待登录成功，使用多种选择器确保检测到登录
            WebDriverWait(self.driver, 120).until(
                lambda driver: any([
                    len(driver.find_elements(By.CSS_SELECTOR, 'div[role="gridcell"]')) > 0,
                    len(driver.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"][role="textbox"][data-tab="10"]')) > 0,
                    len(driver.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="10"]')) > 0,
                    len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="chat-list"]')) > 0
                ])
            )
            
            self.is_logged_in = True
            logger.info("二维码登录成功")
            return True
        
        except Exception as e:
            logger.error(f"二维码登录失败: {e}")
            return False
    
    def get_qr_code(self) -> Optional[Dict]:
        """获取登录二维码（带会话失效自动恢复）"""

        def _do_get_qr() -> Optional[Dict]:
            """内部实际获取二维码的逻辑，便于在会话失效时重试"""
            if not self.driver:
                self.init_driver()

            if self.is_logged_in:
                return None

            # 检查当前页面是否已经是 WhatsApp Web，避免不必要的刷新
            current_url = ""
            need_open_page = True
            try:
                current_url = self.driver.current_url
                # 如果已经在 WhatsApp Web 页面，不需要重新打开
                if "web.whatsapp.com" in current_url:
                    need_open_page = False
                    logger.debug("当前页面已是WhatsApp Web，尝试直接获取二维码（不刷新页面）")
            except Exception:
                # 如果无法获取当前URL，说明会话可能失效，需要重新打开
                logger.debug("无法获取当前URL，将打开新页面")
                need_open_page = True

            # 只有在需要时才打开页面
            if need_open_page:
                logger.info("正在打开WhatsApp Web页面...")
                self.driver.get(WHATSAPP_WEB_URL)
                time.sleep(3)

            # 检查是否已登录（使用多种方法检测）
            # 方法1: 检查聊天项容器（最可靠）
            try:
                # 使用通用的聊天行选择器，而不是 data-testid（更稳定）
                chat_items = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="gridcell"]')
                if chat_items and len(chat_items) > 0:
                    if not self.is_logged_in:
                        logger.info("在获取二维码时检测到WhatsApp已登录（通过聊天项），更新登录状态")
                    self.is_logged_in = True
                    return None
            except:
                pass
            
            # 方法2: 检查消息输入框（已登录页面会有）
            try:
                input_box = self._find_message_input_box(timeout=3)
                if input_box:
                    if not self.is_logged_in:
                        logger.info("在获取二维码时检测到WhatsApp已登录（通过输入框），更新登录状态")
                    self.is_logged_in = True
                    return None
            except:
                pass
            
            # 方法3: 检查搜索框（已登录页面会有）
            try:
                search_box = self.driver.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="3"]')
                if search_box and search_box.is_displayed():
                    if not self.is_logged_in:
                        logger.info("在获取二维码时检测到WhatsApp已登录（通过搜索框），更新登录状态")
                    self.is_logged_in = True
                    return None
            except:
                pass
            
            # 方法4: 检查聊天列表（作为备用）
            try:
                chat_list = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list"]')
                if chat_list and chat_list.is_displayed():
                    if not self.is_logged_in:
                        logger.info("在获取二维码时检测到WhatsApp已登录（通过聊天列表），更新登录状态")
                    self.is_logged_in = True
                    return None
            except:
                pass

            # 尝试获取canvas二维码
            try:
                qr_canvas = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'canvas[aria-label*="二维码"], canvas[aria-label*="QR"]')
                    )
                )
                qr_base64 = qr_canvas.screenshot_as_base64
                return {"base64": qr_base64, "data_ref": None}
            except Exception:
                pass

            # 尝试从data-ref属性获取
            try:
                qr_div = self.driver.find_element(By.CSS_SELECTOR, 'div[data-ref]')
                data_ref = qr_div.get_attribute('data-ref')
                if data_ref:
                    return {"base64": None, "data_ref": data_ref}
            except Exception:
                pass

            # 如果已经在 WhatsApp Web 页面但无法获取二维码，可能是页面加载不完整
            # 只有在第一次打开页面时才刷新，避免在用户扫描时刷新
            if "web.whatsapp.com" not in current_url:
                logger.warning("无法获取二维码，页面可能未完全加载，等待后重试...")
                time.sleep(2)
                # 再次尝试获取
                try:
                    qr_canvas = self.driver.find_element(
                        By.CSS_SELECTOR, 'canvas[aria-label*="二维码"], canvas[aria-label*="QR"]'
                    )
                    qr_base64 = qr_canvas.screenshot_as_base64
                    return {"base64": qr_base64, "data_ref": None}
                except Exception:
                    pass

            return None

        try:
            try:
                # 第一次尝试获取二维码
                return _do_get_qr()
            except Exception as e:
                error_msg = str(e).lower()
                # 处理 Selenium 会话相关错误：会话失效或窗口关闭，重建 driver 后再试一次
                if "invalid session id" in error_msg or "no such window" in error_msg or "target window already closed" in error_msg:
                    error_type = "浏览器会话失效" if "invalid session id" in error_msg else "浏览器窗口已关闭"
                    logger.warning(f"检测到{error_type}，尝试重新初始化driver并重新获取二维码...")
                    try:
                        # 尝试关闭旧的失效会话
                        try:
                            if self.driver:
                                self.driver.quit()
                        except Exception:
                            pass
                        self.driver = None
                        self.is_logged_in = False
                        # 重新初始化并再试一次
                        return _do_get_qr()
                    except Exception as e2:
                        logger.error(f"重新初始化driver后仍然无法获取二维码: {e2}")
                        return None
                # 其他异常直接抛给外层
                raise
        except Exception as e:
            logger.error(f"获取二维码失败: {e}")
            return None
    
    def _find_message_input_box(self, timeout: int = 10):
        """
        查找消息输入框（根据实际HTML结构优化）
        返回: WebElement 或 None
        """
        # 根据提供的HTML结构，尝试多种选择器
        # 优先级：精确匹配 > 部分匹配 > 通用选择器
        selectors = [
            # 最精确的选择器（根据提供的HTML结构）
            'div[contenteditable="true"][role="textbox"][data-tab="10"]',
            'div[contenteditable="true"][data-tab="10"]',
            'div[contenteditable="true"][role="textbox"][tabindex="10"]',
            # 通过aria-label查找（包含"输入要向"和"发送的消息"）
            'div[contenteditable="true"][role="textbox"][aria-label*="输入要向"][aria-label*="发送的消息"]',
            'div[contenteditable="true"][aria-label*="输入要向"][aria-label*="发送的消息"]',
            # 通过父元素查找
            'div.lexical-rich-text-input div[contenteditable="true"][role="textbox"]',
            'div.lexical-rich-text-input div[contenteditable="true"]',
            # 通用选择器（备选）
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"][data-tab="10"]',
        ]
        
        for selector in selectors:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                # 验证元素是否可用
                if element and element.is_displayed():
                    # 验证关键属性
                    contenteditable = element.get_attribute('contenteditable')
                    data_tab = element.get_attribute('data-tab')
                    role = element.get_attribute('role')
                    
                    if contenteditable == 'true' and (data_tab == '10' or role == 'textbox'):
                        logger.debug(f"✅ 找到消息输入框: {selector}")
                        return element
            except Exception as e:
                logger.debug(f"选择器 {selector} 查找失败: {e}")
                continue
        
        # 如果所有选择器都失败，尝试通过XPath查找
        try:
            xpath_selectors = [
                # 通过aria-label的XPath
                '//div[@contenteditable="true" and @role="textbox" and contains(@aria-label, "输入要向") and contains(@aria-label, "发送的消息")]',
                # 通过data-tab的XPath
                '//div[@contenteditable="true" and @data-tab="10"]',
                # 通过父元素的XPath
                '//div[contains(@class, "lexical-rich-text-input")]//div[@contenteditable="true" and @role="textbox"]',
            ]
            
            for xpath in xpath_selectors:
                try:
                    element = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    if element and element.is_displayed():
                        logger.debug(f"✅ 通过XPath找到消息输入框: {xpath}")
                        return element
                except:
                    continue
        except Exception as e:
            logger.debug(f"XPath查找失败: {e}")
        
        logger.warning(f"⚠️  无法找到消息输入框，已尝试所有选择器")
        return None
    
    def _get_current_chat_name(self) -> Optional[str]:
        """获取当前打开的聊天窗口的联系人名称（使用多个备选选择器，根据实际HTML结构优化）"""
        # 根据提供的HTML结构，优先级排序
        selectors = [
            # 最精确的选择器（根据提供的HTML结构）
            'div[role="button"][data-tab="6"] span[dir="auto"]',
            'div[role="button"][data-tab="6"] span',
            'div[data-tab="6"][role="button"] span[dir="auto"]',
            'div[data-tab="6"][role="button"] span',
            # 通过XPath查找（更精确）
            '//div[@role="button" and @data-tab="6"]//span[@dir="auto"]',
            '//div[@role="button" and @data-tab="6"]//span',
            # 其他可能的选择器（备选） 这些应该找不到，但是不影响结果故不删除。
            '[data-testid="conversation-header"] span[title]',
            '[data-testid="conversation-header"] span[dir="auto"]',
            '[data-testid="conversation-header"] span',
            '[data-testid="conversation-header"]',
            'header[data-testid="conversation-header"] span[title]',
            'header[data-testid="conversation-header"] span[dir="auto"]',
            'header[data-testid="conversation-header"] span',
            'header[data-testid="conversation-header"]',
            'div[role="main"] header span[title]',
            'div[role="main"] header span[dir="auto"]',
            'div[role="main"] header span',
            # 通用选择器（最后备选）
            'div[role="button"][data-tab="6"]',
        ]
        
        for selector in selectors:
            try:
                # 判断是CSS选择器还是XPath
                if selector.startswith('//'):
                    elements = self.driver.find_elements(By.XPATH, selector)
                else:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for element in elements:
                    if not element.is_displayed():
                        continue
                    
                    # 尝试多种方式获取文本
                    text = None
                    
                    # 方法1: 获取title属性
                    text = element.get_attribute('title') or ""
                    
                    # 方法2: 获取文本内容
                    if not text:
                        text = element.text or ""
                    
                    # 方法3: 使用JavaScript获取textContent
                    if not text:
                        try:
                            text = self.driver.execute_script(
                                "return arguments[0].textContent || arguments[0].getAttribute('title') || arguments[0].innerText || '';",
                                element
                            ) or ""
                        except:
                            pass
                    
                    # 方法4: 如果是外层div，尝试查找内部的span
                    if not text and element.tag_name == 'div':
                        try:
                            # 查找内部的span元素
                            inner_spans = element.find_elements(By.CSS_SELECTOR, 'span[dir="auto"], span')
                            for span in inner_spans:
                                span_text = span.text or span.get_attribute('textContent') or ""
                                if span_text.strip():
                                    text = span_text.strip()
                                    break
                        except:
                            pass
                    
                    text = text.strip() if text else ""
                    if text:
                        logger.debug(f"✅ 找到联系人名称: {text} (选择器: {selector})")
                        return text
            except Exception:
                continue
        
        return None
    
    def send_message(self, chat_id: str, message: str, delay: float = None) -> bool:
        """发送消息"""
        if not self.is_logged_in:
            logger.error("未登录，无法发送消息")
            return False
        
        # 🔒 使用锁防止多联系人并发冲突
        with self.message_lock:
            try:
                current_time = time.time()
                if chat_id in self.last_reply_time:
                    elapsed = current_time - self.last_reply_time[chat_id]
                    if elapsed < self.min_reply_interval:
                        wait_time = self.min_reply_interval - elapsed
                        logger.info(f"等待 {wait_time:.1f} 秒后发送（防止封号）")
                        time.sleep(wait_time)
                
                # 打开聊天
                self._open_chat(chat_id)
                
                # 🔒 验证当前打开的聊天窗口是否正确（防止发送到错误的联系人）
                try:
                    current_chat_name = self._get_current_chat_name()
                    
                    if current_chat_name:
                        # 归一化比较（忽略大小写和空格）
                        def _normalize_name(name: str) -> str:
                            return " ".join(name.split()).strip().lower()
                        
                        current_normalized = _normalize_name(current_chat_name)
                        target_normalized = _normalize_name(chat_id)
                        
                        if current_normalized != target_normalized:
                            logger.warning(f"⚠️  聊天窗口不匹配！当前: '{current_chat_name}', 期望: '{chat_id}'")
                            logger.warning(f"   重新打开正确的聊天窗口...")
                            # 重新打开正确的聊天
                            self._open_chat(chat_id)
                            # 再次验证
                            time.sleep(0.5)  # 等待窗口切换
                            current_chat_name = self._get_current_chat_name()
                            
                            if current_chat_name:
                                current_normalized = _normalize_name(current_chat_name)
                                if current_normalized != target_normalized:
                                    logger.error(f"❌ 无法打开正确的聊天窗口，取消发送")
                                    logger.error(f"   当前聊天: '{current_chat_name}'")
                                    logger.error(f"   目标聊天: '{chat_id}'")
                                    return False
                                else:
                                    logger.info(f"✅ 已成功切换到正确的聊天窗口: '{current_chat_name}'")
                            else:
                                logger.warning(f"⚠️  无法获取当前聊天窗口名称，继续发送（可能页面结构已变化）")
                        else:
                            logger.debug(f"✅ 聊天窗口验证通过: '{current_chat_name}'")
                    else:
                        logger.warning(f"⚠️  无法获取当前聊天窗口名称，继续发送（可能页面结构已变化）")
                except Exception as e:
                    logger.warning(f"⚠️  验证聊天窗口时出错: {e}，继续发送（可能页面结构已变化）")
                
                # 使用优化的方法查找消息输入框
                message_box = self._find_message_input_box(timeout=10)
                if not message_box:
                    logger.error(f"❌ 无法找到消息输入框，取消发送")
                    return False
                
                logger.info("✅ 找到了可编辑的消息输入框")
                print()
                # 🔒 过滤非BMP字符（ChromeDriver只支持BMP字符）
                def filter_bmp_chars(text: str) -> str:
                    """过滤掉非BMP字符（超出U+FFFF的字符），ChromeDriver不支持"""
                    if not text:
                        return text
                    # BMP字符范围：U+0000 到 U+FFFF
                    # 过滤掉超出BMP范围的字符（如某些emoji）
                    filtered = []
                    removed_chars = []
                    for char in text:
                        code_point = ord(char)
                        if code_point <= 0xFFFF:  # BMP字符
                            filtered.append(char)
                        else:
                            # 非BMP字符，尝试转换为BMP字符或移除
                            removed_chars.append(char)
                            # 对于某些常见的非BMP字符，可以尝试转换
                            # 但为了安全，这里直接移除
                    
                    if removed_chars:
                        logger.warning(f"⚠️  检测到非BMP字符，已移除: {''.join(removed_chars[:10])}{'...' if len(removed_chars) > 10 else ''}")
                        logger.info(f"   原始消息长度: {len(text)} 字符，过滤后: {len(''.join(filtered))} 字符")
                    
                    return ''.join(filtered)
                
                # 过滤消息中的非BMP字符
                filtered_message = filter_bmp_chars(message)
                if filtered_message != message:
                    logger.warning(f"⚠️  消息包含非BMP字符，已过滤")
                    logger.info(f"   原始消息: {message[:100]}{'...' if len(message) > 100 else ''}")
                    logger.info(f"   过滤后消息: {filtered_message[:100]}{'...' if len(filtered_message) > 100 else ''}")
                
                if not filtered_message:
                    logger.error(f"❌ 过滤后消息为空，取消发送")
                    return False
                
                # 先点击消息框，确保获得焦点（根据WhatsApp的lexical编辑器特性）
                try:
                    # 点击消息框，确保可以输入
                    message_box.click()
                    time.sleep(0.1)  # 等待焦点切换
                    logger.debug(f"✅ 已点击消息框，获得焦点")
                except Exception as e:
                    logger.debug(f"点击消息框时出错: {e}，继续尝试输入")
                    # 如果点击失败，尝试使用JavaScript聚焦
                    try:
                        self.driver.execute_script("arguments[0].focus();", message_box)
                        time.sleep(0.1)
                        logger.debug(f"✅ 已使用JavaScript聚焦消息框")
                    except Exception as e2:
                        logger.debug(f"聚焦消息框时出错: {e2}，继续尝试输入")
                
                # 方式1: 尝试使用JavaScript设置文本内容（针对lexical编辑器优化）
                message_written = False
                try:
                    # 根据提供的HTML结构，消息显示在 span[data-lexical-text="true"] 中
                    # 使用JavaScript直接操作lexical编辑器的内部结构
                    self.driver.execute_script("""
                        var element = arguments[0];
                        var message = arguments[1];
                        
                        // 确保元素获得焦点
                        element.focus();
                        
                        // 方法1: 尝试直接设置textContent和innerText
                        element.textContent = message;
                        element.innerText = message;
                        
                        // 方法2: 查找并更新内部的span[data-lexical-text="true"]
                        var spans = element.querySelectorAll('span[data-lexical-text="true"]');
                        if (spans.length > 0) {
                            // 更新所有lexical-text span的内容
                            spans.forEach(function(span) {
                                span.textContent = message;
                            });
                        } else {
                            // 如果没有找到span，尝试创建或更新p标签内的内容
                            var paragraphs = element.querySelectorAll('p');
                            if (paragraphs.length > 0) {
                                paragraphs.forEach(function(p) {
                                    // 查找或创建span
                                    var span = p.querySelector('span[data-lexical-text="true"]');
                                    if (!span) {
                                        span = document.createElement('span');
                                        span.className = '_aupe copyable-text xkrh14z';
                                        span.setAttribute('data-lexical-text', 'true');
                                        p.appendChild(span);
                                    }
                                    span.textContent = message;
                                });
                            } else {
                                // 如果没有p标签，创建一个
                                var p = document.createElement('p');
                                p.className = '_aupe copyable-text x15bjb6t x1n2onr6';
                                p.setAttribute('dir', 'ltr');
                                p.style.cssText = 'text-indent: 0px; margin-top: 0px; margin-bottom: 0px;';
                                
                                var span = document.createElement('span');
                                span.className = '_aupe copyable-text xkrh14z';
                                span.setAttribute('data-lexical-text', 'true');
                                span.textContent = message;
                                
                                p.appendChild(span);
                                element.appendChild(p);
                            }
                        }
                        
                        // 触发beforeinput事件（lexical编辑器可能需要）
                        var beforeInputEvent = new InputEvent('beforeinput', { 
                            bubbles: true, 
                            cancelable: true,
                            inputType: 'insertText',
                            data: message
                        });
                        element.dispatchEvent(beforeInputEvent);
                        
                        // 触发input事件，确保WhatsApp识别到文本变化
                        var inputEvent = new Event('input', { bubbles: true, cancelable: true });
                        element.dispatchEvent(inputEvent);
                        
                        // 触发compositionstart和compositionend事件（处理中文输入）
                        var compositionStartEvent = new CompositionEvent('compositionstart', { bubbles: true });
                        element.dispatchEvent(compositionStartEvent);
                        
                        var compositionEndEvent = new CompositionEvent('compositionend', { 
                            bubbles: true,
                            data: message
                        });
                        element.dispatchEvent(compositionEndEvent);
                        
                        // 确保元素保持焦点
                        element.focus();
                    """, message_box, filtered_message)
                    logger.debug(f"✅ 使用JavaScript设置消息内容（针对lexical编辑器优化）")
                    message_written = True
                except Exception as e:
                    logger.warning(f"⚠️  使用JavaScript设置消息失败: {e}，尝试使用send_keys")
                    # 方式2: 降级到send_keys（已过滤非BMP字符）
                    try:
                        # 先点击消息框确保获得焦点
                        message_box.click()
                        time.sleep(0.1)
                        # 使用Ctrl+A全选，然后输入新内容
                        from selenium.webdriver.common.keys import Keys
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
                        time.sleep(0.1)
                        message_box.send_keys(filtered_message)
                        message_written = True
                        logger.debug(f"✅ 使用send_keys设置消息内容")
                    except Exception as e2:
                        logger.error(f"❌ send_keys也失败: {e2}")
                        return False
                
                # 验证消息是否成功写入消息框（检查span中的内容）
                if message_written:
                    try:
                        # 等待一下，让消息写入完成
                        time.sleep(0.3)
                        
                        # 方法1: 检查整个消息框的内容
                        written_content = message_box.text or message_box.get_attribute('textContent') or ''
                        
                        # 方法2: 检查内部的span[data-lexical-text="true"]内容（更准确）
                        try:
                            lexical_spans = message_box.find_elements(By.CSS_SELECTOR, 'span[data-lexical-text="true"]')
                            if lexical_spans:
                                span_content = ' '.join([span.text or span.get_attribute('textContent') or '' for span in lexical_spans])
                                if span_content:
                                    written_content = span_content
                                    logger.debug(f"   从span[data-lexical-text]中获取内容: {span_content[:50]}...")
                        except Exception as e:
                            logger.debug(f"查找lexical-text span时出错: {e}")
                        
                        # 验证消息是否成功写入
                        if written_content and (filtered_message[:50] in written_content or written_content[:50] in filtered_message):
                            logger.info(f"✅ 成功将消息写入消息框")
                            logger.info(f"   消息内容: {filtered_message[:100]}{'...' if len(filtered_message) > 100 else ''}")
                            logger.info(f"   消息长度: {len(filtered_message)} 字符")
                            logger.debug(f"   验证：消息框内容包含发送的消息")
                        else:
                            logger.warning(f"⚠️  消息可能未完全写入消息框")
                            logger.warning(f"   期望内容: {filtered_message[:50]}...")
                            logger.warning(f"   实际内容: {written_content[:50] if written_content else '(空)'}...")
                            # 即使验证失败，也继续尝试发送（可能是验证逻辑问题）
                    except Exception as e:
                        logger.debug(f"验证消息写入时出错: {e}，继续发送流程")
                
                if delay is None:
                    delay = self.min_reply_interval + (time.time() % 2)
                time.sleep(delay)
                
                # 记录发送前的输入框内容，用于验证
                initial_content = message_box.text or message_box.get_attribute('textContent') or ''
                
                # 发送消息 - 尝试多种方式确保成功
                send_success = False
                max_send_attempts = 3
                
                for attempt in range(max_send_attempts):
                    try:
                        # 方式1: 尝试按Enter键（最常用方式）
                        if attempt == 0:
                            try:
                                message_box.send_keys(Keys.RETURN)
                                logger.info(f"✅ 使用Enter键发送消息（尝试 {attempt + 1}）")
                                send_success = True
                            except Exception as e:
                                logger.warning(f"⚠️  按Enter键失败: {e}，尝试其他方式")
                        
                        # 方式2: 尝试使用JavaScript触发Enter事件
                        if not send_success and attempt == 1:
                            try:
                                self.driver.execute_script("""
                                    var element = arguments[0];
                                    // 触发keydown事件
                                    var keydownEvent = new KeyboardEvent('keydown', {
                                        key: 'Enter',
                                        code: 'Enter',
                                        keyCode: 13,
                                        which: 13,
                                        bubbles: true,
                                        cancelable: true
                                    });
                                    element.dispatchEvent(keydownEvent);
                                    
                                    // 触发keypress事件
                                    var keypressEvent = new KeyboardEvent('keypress', {
                                        key: 'Enter',
                                        code: 'Enter',
                                        keyCode: 13,
                                        which: 13,
                                        bubbles: true,
                                        cancelable: true
                                    });
                                    element.dispatchEvent(keypressEvent);
                                    
                                    // 触发keyup事件
                                    var keyupEvent = new KeyboardEvent('keyup', {
                                        key: 'Enter',
                                        code: 'Enter',
                                        keyCode: 13,
                                        which: 13,
                                        bubbles: true,
                                        cancelable: true
                                    });
                                    element.dispatchEvent(keyupEvent);
                                """, message_box)
                                logger.info(f"✅ 使用JavaScript触发Enter事件发送消息（尝试 {attempt + 1}）")
                                send_success = True
                            except Exception as e:
                                logger.warning(f"⚠️  JavaScript触发Enter事件失败: {e}")
                        
                        # 方式3: 尝试查找并点击发送按钮
                        if not send_success and attempt == 2:
                            try:
                                # 等待一下，让发送按钮出现
                                time.sleep(0.5)
                                
                                # 尝试多种选择器查找发送按钮（根据实际HTML结构优化）
                                # 优先级：精确匹配 > 部分匹配 > 通用选择器
                                send_button_selectors = [
                                    # 最精确的选择器（根据提供的HTML结构）
                                    'button[data-tab="11"][aria-label="发送"]',
                                    'button[data-tab="11"]',
                                    'button[aria-label="发送"]',
                                    # 通过内部图标查找按钮（span的父元素）
                                    'span[data-icon="wds-ic-send-filled"]',
                                    # 其他可能的选择器
                                    'button[aria-label*="发送"]',
                                    'button[aria-label*="Send"]',
                                    'span[data-testid="send"]',
                                    'span[data-icon="send"]',
                                    'button[data-testid="send"]',
                                    'button[title*="发送"]',
                                    'button[title*="Send"]',
                                ]
                                
                                send_button = None
                                for selector in send_button_selectors:
                                    try:
                                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                        for el in elements:
                                            # 如果是span元素，需要找到其父button元素
                                            if el.tag_name == 'span':
                                                # 向上查找button父元素
                                                try:
                                                    # 尝试多种方式找到父button
                                                    parent_button = el.find_element(By.XPATH, './ancestor::button[1]')
                                                    if parent_button and parent_button.is_displayed() and parent_button.is_enabled():
                                                        send_button = parent_button
                                                        logger.info(f"通过span找到父button: {selector}")
                                                        break
                                                except:
                                                    # 如果找不到父button，尝试通过JavaScript查找
                                                    try:
                                                        parent_button = self.driver.execute_script("""
                                                            var span = arguments[0];
                                                            var button = span.closest('button');
                                                            return button && button.offsetParent !== null ? button : null;
                                                        """, el)
                                                        if parent_button:
                                                            send_button = parent_button
                                                            logger.info(f"通过JavaScript找到父button: {selector}")
                                                            break
                                                    except:
                                                        continue
                                            else:
                                                # 直接是button元素
                                                if el.is_displayed() and el.is_enabled():
                                                    # 检查aria-disabled属性（如果存在且为true，则不可用）
                                                    aria_disabled = el.get_attribute('aria-disabled')
                                                    if aria_disabled != 'true':
                                                        send_button = el
                                                        logger.info(f"找到发送按钮: {selector}")
                                                        break
                                            if send_button:
                                                break
                                        if send_button:
                                            break
                                    except Exception as e:
                                        logger.info(f"选择器 {selector} 查找失败: {e}")
                                        continue
                                
                                if send_button:
                                    # 使用JavaScript点击发送按钮（更可靠）
                                    try:
                                        self.driver.execute_script("arguments[0].click();", send_button)
                                        logger.info(f"✅ 使用发送按钮发送消息（尝试 {attempt + 1}）")
                                        send_success = True
                                    except Exception as e:
                                        # 如果JavaScript点击失败，尝试普通点击
                                        try:
                                            send_button.click()
                                            logger.info(f"✅ 使用发送按钮发送消息（普通点击，尝试 {attempt + 1}）")
                                            send_success = True
                                        except Exception as e2:
                                            logger.warning(f"⚠️  点击发送按钮失败: {e2}")
                                else:
                                    logger.warning(f"⚠️  未找到发送按钮，已尝试所有选择器")
                            except Exception as e:
                                logger.warning(f"⚠️  查找发送按钮时出错: {e}")
                        
                        # 如果发送成功，等待并验证（必须同时满足两个条件）
                        if send_success:
                            # 等待消息发送完成
                            time.sleep(1.5)
                            
                            # 条件1: 检查输入框是否被清空
                            input_box_empty = False
                            try:
                                # 重新获取输入框元素（可能已刷新）
                                message_box = self._find_message_input_box(timeout=5)
                                if message_box:
                                    current_content = message_box.text or message_box.get_attribute('textContent') or ''
                                    # 输入框必须为空才认为满足条件1
                                    if not current_content.strip():
                                        input_box_empty = True
                                        logger.debug(f"✅ 条件1满足：输入框已清空")
                                    else:
                                        logger.debug(f"❌ 条件1不满足：输入框仍有内容: '{current_content[:50]}...'")
                                else:
                                    logger.debug("无法重新获取消息输入框，无法验证条件1")
                            except Exception as e:
                                logger.debug(f"验证输入框时出错: {e}")
                            
                            # 条件2: 检查消息是否出现在聊天窗口中或聊天列表中
                            message_found_in_chat = False
                            message_found_in_list = False
                            
                            # 方法1: 检查聊天窗口中的消息
                            try:
                                time.sleep(0.5)  # 再等待一下，让消息出现在聊天窗口
                                
                                # 查找最新的消息气泡（右侧，自己发送的消息）
                                message_selectors = [
                                    'div.message-out',
                                    'div[data-testid="msg-container"][data-id*="true"]',
                                    'div[data-id*="true"]',
                                    'div[class*="message-out"]',
                                ]
                                
                                recent_messages = []
                                for selector in message_selectors:
                                    try:
                                        messages = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                        if messages:
                                            recent_messages = messages
                                            break
                                    except:
                                        continue
                                
                                if recent_messages:
                                    # 检查最后几条消息是否包含我们发送的内容
                                    check_count = min(5, len(recent_messages))  # 检查最后5条消息
                                    for i in range(-check_count, 0):
                                        try:
                                            last_message = recent_messages[i]
                                            last_message_text = last_message.text or last_message.get_attribute('textContent') or ''
                                            # 使用相似度检查（至少前30个字符匹配，或相似度超过70%）
                                            message_preview = filtered_message[:30] if len(filtered_message) >= 30 else filtered_message
                                            if (message_preview in last_message_text or 
                                                last_message_text[:30] in filtered_message or
                                                self._messages_similar(filtered_message, last_message_text)):
                                                message_found_in_chat = True
                                                logger.debug(f"✅ 条件2满足（聊天窗口）：消息已出现在聊天窗口中")
                                                logger.debug(f"   发送的消息: {filtered_message[:50]}...")
                                                logger.debug(f"   找到的消息: {last_message_text[:50]}...")
                                                break
                                        except Exception as e:
                                            logger.debug(f"检查消息时出错: {e}")
                                            continue
                            except Exception as e:
                                logger.debug(f"验证聊天窗口消息时出错: {e}")
                            
                            # 方法2: 检查聊天列表中的最新消息（如果聊天窗口验证失败）
                            if not message_found_in_chat:
                                try:
                                    # 查找聊天列表项
                                    chat_list_selectors = [
                                        'div[role="gridcell"]',
                                        'div[data-testid="cell-frame-container"]',
                                    ]
                                    
                                    for selector in chat_list_selectors:
                                        try:
                                            chat_items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                            if chat_items:
                                                # 查找当前联系人的聊天项
                                                for item in chat_items:
                                                    try:
                                                        # 获取联系人名称
                                                        name_elements = item.find_elements(By.CSS_SELECTOR, 'span[title]')
                                                        if name_elements:
                                                            item_name = name_elements[0].get_attribute('title') or ''
                                                            # 归一化比较联系人名称
                                                            def _normalize(s: str) -> str:
                                                                return " ".join(s.split()).strip().lower()
                                                            
                                                            if _normalize(item_name) == _normalize(chat_id):
                                                                # 找到当前联系人的聊天项，检查最新消息预览
                                                                preview_selectors = [
                                                                    'span[title] + span',
                                                                    'div[dir="ltr"]',
                                                                    'span[class*="text"]',
                                                                ]
                                                                
                                                                for preview_selector in preview_selectors:
                                                                    try:
                                                                        preview_elements = item.find_elements(By.CSS_SELECTOR, preview_selector)
                                                                        for preview_el in preview_elements:
                                                                            preview_text = preview_el.text or preview_el.get_attribute('textContent') or ''
                                                                            if preview_text:
                                                                                # 检查预览文本是否与发送的消息相似
                                                                                if (filtered_message[:30] in preview_text or 
                                                                                    preview_text[:30] in filtered_message or
                                                                                    self._messages_similar(filtered_message, preview_text)):
                                                                                    message_found_in_list = True
                                                                                    logger.debug(f"✅ 条件2满足（聊天列表）：消息已出现在聊天列表的最新消息中")
                                                                                    logger.debug(f"   发送的消息: {filtered_message[:50]}...")
                                                                                    logger.debug(f"   列表预览: {preview_text[:50]}...")
                                                                                    break
                                                                        if message_found_in_list:
                                                                            break
                                                                    except:
                                                                        continue
                                                                
                                                                if message_found_in_list:
                                                                    break
                                                    except:
                                                        continue
                                                
                                                if message_found_in_list:
                                                    break
                                        except:
                                            continue
                                except Exception as e:
                                    logger.debug(f"验证聊天列表消息时出错: {e}")
                            
                            # 条件2满足：消息出现在聊天窗口或聊天列表中
                            message_found = message_found_in_chat or message_found_in_list
                            
                            # 综合判断：两个条件必须同时满足
                            if input_box_empty and message_found:
                                self.last_reply_time[chat_id] = time.time()
                                logger.info(f"✅ 消息已成功发送到 {chat_id}: {filtered_message[:50]}...")
                                logger.info(f"   验证结果：输入框已清空 ✓ | 消息已出现在聊天中 ✓")
                                return True
                            else:
                                # 记录详细的验证失败信息
                                logger.warning(f"⚠️  消息发送验证未完全通过")
                                logger.warning(f"   条件1（输入框为空）: {'✓' if input_box_empty else '✗'}")
                                logger.warning(f"   条件2（消息出现在聊天中）: {'✓' if message_found else '✗'}")
                                
                                if not input_box_empty:
                                    logger.warning(f"   原因：输入框仍有内容，消息可能未发送")
                                if not message_found:
                                    logger.warning(f"   原因：未在聊天窗口或聊天列表中找到发送的消息")
                                
                                # 如果验证失败，返回False（不再默认返回True）
                                logger.error(f"❌ 消息发送验证失败，返回False")
                                return False
                        
                    except Exception as e:
                        logger.warning(f"⚠️  发送尝试 {attempt + 1} 失败: {e}")
                        if attempt < max_send_attempts - 1:
                            time.sleep(0.5)  # 等待后重试
                        continue
                
                # 所有发送方式都失败
                logger.error(f"❌ 所有发送方式都失败，无法发送消息")
                return False
            
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                return False
    
    def _messages_similar(self, msg1: str, msg2: str, threshold: float = 0.7) -> bool:
        """
        判断两条消息是否相似
        使用简单的字符匹配算法，计算相似度
        返回: True if 相似度 >= threshold
        """
        if not msg1 or not msg2:
            return False
        
        # 去除空格和换行符进行比较
        msg1_clean = ''.join(msg1.split())
        msg2_clean = ''.join(msg2.split())
        
        if not msg1_clean or not msg2_clean:
            return False
        
        # 计算最长公共子序列长度
        def lcs_length(s1: str, s2: str) -> int:
            m, n = len(s1), len(s2)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if s1[i-1] == s2[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
            return dp[m][n]
        
        # 计算相似度
        lcs = lcs_length(msg1_clean, msg2_clean)
        max_len = max(len(msg1_clean), len(msg2_clean))
        similarity = lcs / max_len if max_len > 0 else 0
        
        return similarity >= threshold
    
    def send_image(self, chat_id: str, image_path: str, caption: str = "", delay: float = None) -> bool:
        """发送图片"""
        if not self.is_logged_in:
            logger.error("未登录，无法发送图片")
            return False
        
        if not os.path.exists(image_path):
            logger.error(f"图片文件不存在: {image_path}")
            return False
        
        try:
            current_time = time.time()
            if chat_id in self.last_reply_time:
                elapsed = current_time - self.last_reply_time[chat_id]
                if elapsed < self.min_reply_interval:
                    wait_time = self.min_reply_interval - elapsed
                    logger.info(f"等待 {wait_time:.1f} 秒后发送（防止封号）")
                    time.sleep(wait_time)
            
            self._open_chat(chat_id)
            time.sleep(1)  # 等待聊天窗口完全加载
            
            # 查找附件按钮（通常是回形针图标或加号图标）
            try:
                # 尝试多种选择器，按优先级排序
                attachment_selectors = [
                    'span[data-icon="attach-light"]',
                    'span[data-icon="attach"]',
                    'button[aria-label*="附件"]',
                    'button[aria-label*="Attach"]',
                    'button[title*="附件"]',
                    'button[title*="Attach"]',
                    'div[role="button"][title*="附件"]',
                    'div[role="button"][title*="Attach"]',
                    'button[data-tab="11"]',  # WhatsApp Web 的附件按钮可能有这个属性
                    'div[data-tab="11"]'
                ]
                
                attachment_button = None
                for selector in attachment_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for el in elements:
                            if el.is_displayed() and el.is_enabled():
                                attachment_button = el
                                break
                        if attachment_button:
                            break
                    except:
                        continue
                
                if attachment_button:
                    # 使用JavaScript点击，更可靠
                    try:
                        self.driver.execute_script("arguments[0].click();", attachment_button)
                        logger.info("已点击附件按钮（使用JavaScript）")
                    except:
                        attachment_button.click()
                        logger.info("已点击附件按钮（使用普通点击）")
                    time.sleep(1.5)  # 等待附件菜单打开
                else:
                    logger.error("无法找到附件按钮，尝试的所有选择器都失败")
                    # 尝试使用快捷键 Ctrl+Shift+A（某些版本的WhatsApp Web支持）
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        message_box = self._find_message_input_box(timeout=5)
                        if message_box:
                            ActionChains(self.driver).key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys('a').key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
                        else:
                            logger.warning("无法找到消息输入框，跳过快捷键操作")
                        time.sleep(1)
                        logger.info("使用快捷键打开附件菜单")
                    except Exception as e2:
                        logger.error(f"使用快捷键也失败: {e2}")
                        return False
            except Exception as e:
                logger.error(f"点击附件按钮失败: {e}")
                return False
            
            # 查找文件输入框
            try:
                # 等待文件输入框出现
                file_input = None
                max_attempts = 5
                for attempt in range(max_attempts):
                    # 尝试多种选择器
                    file_input_selectors = [
                        'input[type="file"][accept*="image"]',
                        'input[type="file"][accept*="image/*"]',
                        'input[type="file"][accept*="*"]',
                        'input[type="file"]'
                    ]
                    
                    for selector in file_input_selectors:
                        try:
                            file_inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for inp in file_inputs:
                                # 检查输入框是否可见（可能在DOM中但被隐藏）
                                try:
                                    if inp.is_displayed() or inp.get_attribute('style') != 'display: none;':
                                        file_input = inp
                                        break
                                except:
                                    # 如果无法检查显示状态，直接使用第一个
                                    file_input = inp
                                    break
                            if file_input:
                                break
                        except:
                            continue
                    
                    if file_input:
                        break
                    
                    if attempt < max_attempts - 1:
                        time.sleep(0.5)
                        logger.debug(f"等待文件输入框出现... (尝试 {attempt + 1}/{max_attempts})")
                
                if file_input:
                    # 获取绝对路径
                    abs_image_path = os.path.abspath(image_path)
                    logger.info(f"准备上传图片: {abs_image_path}")
                    
                    # 使用JavaScript设置文件值（更可靠）
                    try:
                        self.driver.execute_script(
                            "arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';",
                            file_input
                        )
                    except:
                        pass
                    
                    # 发送图片文件路径
                    file_input.send_keys(abs_image_path)
                    logger.info("文件路径已发送到输入框")
                    time.sleep(3)  # 等待文件上传和处理
                else:
                    logger.error("无法找到文件输入框，尝试的所有选择器都失败")
                    return False
            except Exception as e:
                logger.error(f"上传文件失败: {e}", exc_info=True)
                return False
            
            # 如果有标题，输入标题
            if caption:
                try:
                    # 等待标题输入框出现（文件上传后可能需要一点时间）
                    time.sleep(0.5)
                    
                    # 尝试多种选择器查找标题输入框
                    caption_selectors = [
                        'div[contenteditable="true"][data-placeholder*="添加"]',
                        'div[contenteditable="true"][placeholder*="Add"]',
                        'div[contenteditable="true"][data-placeholder*="Add"]',
                        'div[contenteditable="true"][data-placeholder*="Caption"]',
                        'div[contenteditable="true"][data-tab="10"]',
                        'div[contenteditable="true"][role="textbox"]'
                    ]
                    
                    caption_box = None
                    max_attempts = 3
                    for attempt in range(max_attempts):
                        for selector in caption_selectors:
                            try:
                                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                for el in elements:
                                    if el.is_displayed():
                                        caption_box = el
                                        break
                                if caption_box:
                                    break
                            except:
                                continue
                        
                        if caption_box:
                            break
                        
                        if attempt < max_attempts - 1:
                            time.sleep(0.5)
                    
                    if caption_box:
                        # 🔒 过滤非BMP字符（ChromeDriver只支持BMP字符）
                        def filter_bmp_chars(text: str) -> str:
                            """过滤掉非BMP字符（超出U+FFFF的字符），ChromeDriver不支持"""
                            if not text:
                                return text
                            filtered = []
                            removed_chars = []
                            for char in text:
                                code_point = ord(char)
                                if code_point <= 0xFFFF:  # BMP字符
                                    filtered.append(char)
                                else:
                                    removed_chars.append(char)
                            
                            if removed_chars:
                                logger.warning(f"⚠️  图片标题包含非BMP字符，已移除: {''.join(removed_chars[:10])}{'...' if len(removed_chars) > 10 else ''}")
                            
                            return ''.join(filtered)
                        
                        filtered_caption = filter_bmp_chars(caption) if caption else ""
                        
                        # 使用JavaScript设置文本内容，避免BMP限制
                        try:
                            self.driver.execute_script("""
                                var element = arguments[0];
                                element.textContent = arguments[1];
                                element.innerText = arguments[1];
                                var event = new Event('input', { bubbles: true });
                                element.dispatchEvent(event);
                            """, caption_box, filtered_caption)
                            logger.info(f"图片标题已输入（使用JavaScript）: {filtered_caption}")
                        except Exception as e:
                            logger.warning(f"⚠️  使用JavaScript设置标题失败: {e}，尝试使用send_keys")
                            # 降级到send_keys（已过滤非BMP字符）
                            try:
                                self.driver.execute_script("arguments[0].focus();", caption_box)
                                time.sleep(0.2)
                                caption_box.clear()
                                caption_box.send_keys(filtered_caption)
                                time.sleep(0.5)
                                logger.info(f"图片标题已输入（使用send_keys）: {filtered_caption}")
                            except Exception as e2:
                                logger.warning(f"⚠️  send_keys也失败: {e2}，跳过标题")
                    else:
                        logger.warning("无法找到标题输入框，将发送不带标题的图片")
                except Exception as e:
                    logger.warning(f"输入标题失败: {e}，将发送不带标题的图片")
            
            # 点击发送按钮
            try:
                if delay is None:
                    delay = self.min_reply_interval + (time.time() % 2)
                time.sleep(delay)
                
                # 等待发送按钮出现（文件上传后可能需要时间）
                max_attempts = 5
                send_button = None
                for attempt in range(max_attempts):
                    # 尝试多种选择器查找发送按钮（根据实际HTML结构优化）
                    # 优先级：精确匹配 > 部分匹配 > 通用选择器
                    send_selectors = [
                        # 最精确的选择器（根据提供的HTML结构）
                        'button[data-tab="11"][aria-label="发送"]',
                        'button[data-tab="11"]',
                        'button[aria-label="发送"]',
                        # 通过内部图标查找按钮（span的父元素）
                        'span[data-icon="wds-ic-send-filled"]',
                        # 其他可能的选择器
                        'button[aria-label*="发送"]',
                        'button[aria-label*="Send"]',
                        'span[data-icon="send"]',
                        'span[data-testid="send"]',
                        'button[data-testid="send"]',
                        'button[title*="发送"]',
                        'button[title*="Send"]',
                        'div[role="button"][aria-label*="发送"]',
                        'div[role="button"][aria-label*="Send"]'
                    ]
                    
                    for selector in send_selectors:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for el in elements:
                                # 如果是span元素，需要找到其父button元素
                                if el.tag_name == 'span':
                                    # 向上查找button父元素
                                    try:
                                        # 尝试多种方式找到父button
                                        parent_button = el.find_element(By.XPATH, './ancestor::button[1]')
                                        if parent_button and parent_button.is_displayed() and parent_button.is_enabled():
                                            aria_disabled = parent_button.get_attribute('aria-disabled')
                                            if aria_disabled != 'true':
                                                send_button = parent_button
                                                logger.debug(f"通过span找到父button: {selector}")
                                                break
                                    except:
                                        # 如果找不到父button，尝试通过JavaScript查找
                                        try:
                                            parent_button = self.driver.execute_script("""
                                                var span = arguments[0];
                                                var button = span.closest('button');
                                                return button && button.offsetParent !== null ? button : null;
                                            """, el)
                                            if parent_button:
                                                send_button = parent_button
                                                logger.debug(f"通过JavaScript找到父button: {selector}")
                                                break
                                        except:
                                            continue
                                else:
                                    # 直接是button或div元素
                                    if el.is_displayed() and el.is_enabled():
                                        # 检查aria-disabled属性（如果存在且为true，则不可用）
                                        aria_disabled = el.get_attribute('aria-disabled')
                                        if aria_disabled != 'true':
                                            send_button = el
                                            logger.debug(f"找到发送按钮: {selector}")
                                            break
                                if send_button:
                                    break
                            if send_button:
                                break
                        except Exception as e:
                            logger.debug(f"选择器 {selector} 查找失败: {e}")
                            continue
                    
                    if send_button:
                        break
                    
                    if attempt < max_attempts - 1:
                        time.sleep(0.5)
                        logger.debug(f"等待发送按钮出现... (尝试 {attempt + 1}/{max_attempts})")
                
                if send_button:
                    # 使用JavaScript点击，更可靠
                    try:
                        self.driver.execute_script("arguments[0].click();", send_button)
                        logger.info("已点击发送按钮（使用JavaScript）")
                    except Exception as e:
                        try:
                            send_button.click()
                            logger.info("已点击发送按钮（使用普通点击）")
                        except Exception as e2:
                            logger.warning(f"点击发送按钮失败: {e2}")
                    time.sleep(1)  # 等待发送完成
                else:
                    # 如果找不到发送按钮，尝试按Enter键
                    try:
                        logger.warning("无法找到发送按钮，尝试使用Enter键发送")
                        caption_box = self._find_message_input_box(timeout=5)
                        if caption_box:
                            caption_box.send_keys(Keys.RETURN)
                        else:
                            logger.error("无法找到消息输入框，无法使用Enter键发送")
                        time.sleep(1)
                        logger.info("已使用Enter键发送图片")
                    except Exception as e2:
                        logger.error(f"使用Enter键也失败: {e2}")
                        return False
            except Exception as e:
                logger.error(f"发送图片失败: {e}", exc_info=True)
                return False
            
            self.last_reply_time[chat_id] = time.time()
            logger.info(f"图片已发送到 {chat_id}: {image_path}")
            return True
        
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False
    
    def _open_chat(self, chat_id: str):
        """打开指定聊天"""
        try:
            # 确保在WhatsApp Web页面
            if "web.whatsapp.com" not in self.driver.current_url:
                self.driver.get(WHATSAPP_WEB_URL)
                time.sleep(2)
            
            # 查找搜索框
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="3"]'))
            )
            search_box.click()
            time.sleep(0.5)
            
            # 清空搜索框并输入联系人名称
            search_box.clear()
            search_keyword = chat_id.strip()
            search_box.send_keys(search_keyword)
            time.sleep(2)  # 等待搜索结果加载
            
            # 等待搜索结果出现并进行更智能的匹配
            try:
                # 获取所有搜索结果项，而不是只取第一个
                # 使用通用的聊天项选择器（role="gridcell"），兼容新版 WhatsApp Web
                results = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, 'div[role="gridcell"]')
                    )
                )
                
                if not results:
                    raise Exception("no search results")
                
                logger.info(f"搜索 '{search_keyword}' 共找到 {len(results)} 个结果，开始精确匹配联系人名称...")
                
                # 归一化函数：去掉前后空格、合并多余空格、忽略大小写
                def _normalize(s: str) -> str:
                    if not s:
                        return ""
                    return " ".join(s.split()).strip().lower()
                
                target_norm = _normalize(search_keyword)
                
                best_match_element = None
                best_match_name = None
                
                # 只查找完全匹配的联系人
                for idx, item in enumerate(results):
                    try:
                        name_el = item.find_element(By.CSS_SELECTOR, 'span[title]')
                        name = name_el.get_attribute('title') or ""
                        name_norm = _normalize(name)
                        
                        logger.info(f"搜索结果[{idx}] 联系人: '{name}', 归一化: '{name_norm}'")
                        
                        # 只接受完全匹配
                        if name_norm == target_norm:
                            best_match_element = item
                            best_match_name = name
                            logger.info(f"✓ 找到完全匹配的联系人: '{name}'")
                            break
                    except Exception as e:
                        logger.debug(f"分析搜索结果项时出错: {e}")
                        continue
                
                # 如果没有找到完全匹配的联系人，抛出异常
                if not best_match_element:
                    logger.error(f"未找到完全匹配的联系人: '{search_keyword}'")
                    logger.error(f"搜索结果列表:")
                    for idx, item in enumerate(results):
                        try:
                            name_el = item.find_element(By.CSS_SELECTOR, 'span[title]')
                            name = name_el.get_attribute('title') or ""
                            logger.error(f"  [{idx}] '{name}'")
                        except:
                            pass
                    raise Exception(f"未找到完全匹配的联系人 '{search_keyword}'，请检查联系人名称是否正确")
                
                logger.info(f"最终选中的联系人: '{best_match_name}', 搜索关键词: '{search_keyword}'")
                
                # 点击打开聊天
                best_match_element.click()
                time.sleep(2)  # 等待聊天窗口打开
                
                # 验证是否成功打开聊天（检查是否有消息输入框）
                try:
                    message_box = self._find_message_input_box(timeout=5)
                    if message_box:
                        logger.info(f"成功打开与 {best_match_name} 的聊天")
                        return True
                    else:
                        logger.warning("打开聊天后未找到消息输入框，可能未成功打开")
                        return False
                except Exception as e:
                    logger.warning(f"验证聊天窗口时出错: {e}")
                    return False
                    
            except Exception as e:
                logger.error(f"未找到联系人 '{chat_id}' 的合适搜索结果: {e}")
                # 尝试清除搜索框
                try:
                    search_box.clear()
                    search_box.send_keys(Keys.ESCAPE)
                except Exception:
                    pass
                raise Exception(f"无法找到联系人 '{chat_id}'。请确保输入的是联系人在 WhatsApp 中显示的名称（昵称），区分空格和特殊符号。如果该联系人不在您的联系人列表中，请先添加为联系人。")
        
        except Exception as e:
            logger.error(f"打开聊天失败: {e}")
            raise
    
    def listen_messages(self, callback: Callable):
        """监听新消息 - 改进版：不依赖未读标记，使用时间戳判断新消息"""
        if not self.is_logged_in:
            logger.error("❌ 未登录，无法监听消息")
            logger.error("请先在Web界面中登录WhatsApp，然后启动机器人")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 开始监听消息...")
        logger.info("📋 监听模式：遍历所有聊天列表，使用时间戳判断新消息")
        logger.info("⏱️  检查间隔：每3秒检查一次")
        logger.info("=" * 60)
        
        # 动态加载配置的函数
        def get_listen_config():
            """动态获取监听配置"""
            try:
                import importlib
                import config
                importlib.reload(config)
                from config import (
                    AUTO_REPLY_ENABLED, LISTEN_CONTACTS,
                    SPECIFIC_CONTACTS,
                    REPLY_TO_ALL_CONTACTS
                )
                return {
                    'auto_reply_enabled': AUTO_REPLY_ENABLED,
                    'listen_contacts': LISTEN_CONTACTS,
                    'reply_to_all_contacts': REPLY_TO_ALL_CONTACTS,
                    'specific_contacts': [c.strip().lower() for c in SPECIFIC_CONTACTS if c.strip()]
                }
            except Exception as e:
                logger.warning(f"获取监听配置失败: {e}，使用默认配置")
                return {
                    'auto_reply_enabled': True,
                    'listen_contacts': True,
                    'reply_to_all_contacts': True,
                    'specific_contacts': []
                }
        
        # 缓存配置，每10次循环重新加载一次（约30秒）
        cached_config = None
        config_cache_count = 0
        
        def should_listen(contact_name: str, is_group: bool) -> bool:
            """判断是否应该监听该联系人的消息"""
            nonlocal cached_config, config_cache_count
            
            # 不监听群组消息
            if is_group:
                return False
            
            # 每10次循环重新加载一次配置（约30秒），确保配置更新能及时生效
            if cached_config is None or config_cache_count >= 10:
                cached_config = get_listen_config()
                config_cache_count = 0
                if config_cache_count == 0:  # 首次或重新加载时
                    logger.debug("已重新加载监听配置")
            
            config_cache_count += 1
            config = cached_config
            
            # 如果自动回复未启用，不监听
            if not config['auto_reply_enabled']:
                return False
            
            contact_name_clean = contact_name.strip().lower() if contact_name else ""
            
            # 联系人判断
            if not config['listen_contacts']:
                return False
            
            if config['reply_to_all_contacts']:
                # 监听所有联系人
                return True
            else:
                # 只监听指定联系人 - 使用完全匹配
                if not config['specific_contacts']:
                    return False
                # 精确匹配：检查联系人名称是否完全等于配置列表中的某个联系人
                for specific_contact in config['specific_contacts']:
                    if specific_contact == contact_name_clean:
                        return True
                return False
        
        # 记录每个聊天最后处理的消息时间戳 {contact_name: last_timestamp}
        last_processed_times = {}
        # 记录已处理的消息唯一标识，避免短时间内重复处理
        processed_message_ids = set()
        loop_count = 0
        
        # 首次加载配置并显示监听范围
        cached_config = get_listen_config()
        initial_config = cached_config
        logger.info("📋 监听配置:")
        logger.info(f"   自动回复启用: {initial_config['auto_reply_enabled']}")
        logger.info(f"   监听联系人: {initial_config['listen_contacts']}")
        if initial_config['listen_contacts']:
            if initial_config['reply_to_all_contacts']:
                logger.info("   ✅ 监听范围: 所有联系人")
            else:
                specific = initial_config['specific_contacts']
                if specific:
                    logger.info(f"   ✅ 监听范围: 指定联系人 ({len(specific)} 个)")
                    logger.info(f"      联系人列表: {', '.join(specific[:5])}{'...' if len(specific) > 5 else ''}")
                else:
                    logger.warning("   ⚠️  未配置指定联系人，将不监听任何联系人")
        logger.info("=" * 60)
        
        def parse_time_string(time_str: str) -> Optional[float]:
            """解析WhatsApp时间字符串为时间戳"""
            if not time_str:
                return None
            try:
                time_str = time_str.strip()
                now = datetime.now()
                
                # 处理纯时间格式，如 "15:30"（假设是今天）
                if ":" in time_str and len(time_str.split()) == 1 and len(time_str.split(":")) == 2:
                    try:
                        hour, minute = map(int, time_str.split(":"))
                        if 0 <= hour < 24 and 0 <= minute < 60:
                            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            # 如果时间比当前时间晚，说明是昨天的时间
                            if dt > now:
                                dt = dt - timedelta(days=1)
                            return dt.timestamp()
                    except:
                        pass
                
                # 处理"今天"、"昨天"等相对时间
                if "今天" in time_str or "Today" in time_str:
                    # 提取时间部分，如 "15:30"
                    time_part = time_str.split()[-1] if " " in time_str else time_str
                    if ":" in time_part:
                        try:
                            hour, minute = map(int, time_part.split(":"))
                            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            return dt.timestamp()
                        except:
                            pass
                
                if "昨天" in time_str or "Yesterday" in time_str:
                    time_part = time_str.split()[-1] if " " in time_str else time_str
                    if ":" in time_part:
                        try:
                            hour, minute = map(int, time_part.split(":"))
                            dt = (now - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                            return dt.timestamp()
                        except:
                            pass
                
                # 处理具体日期，如 "2025/12/17" 或 "12/17"
                # 尝试多种日期格式
                date_formats = [
                    "%Y/%m/%d",
                    "%m/%d",
                    "%Y-%m-%d",
                    "%m-%d",
                    "%d/%m/%Y",
                    "%d/%m"
                ]
                
                for fmt in date_formats:
                    try:
                        if "/" in time_str or "-" in time_str:
                            parts = time_str.replace("-", "/").split()
                            date_part = parts[0]
                            dt = datetime.strptime(date_part, fmt)
                            if dt.year == 1900:  # 如果没有年份，使用当前年份
                                dt = dt.replace(year=now.year)
                            # 如果有时间部分
                            if len(parts) > 1 and ":" in parts[1]:
                                hour, minute = map(int, parts[1].split(":"))
                                dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            return dt.timestamp()
                    except:
                        continue
                
                # 如果都解析失败，返回None
                return None
            except Exception as e:
                logger.debug(f"解析时间字符串失败: {time_str}, 错误: {e}")
                return None
        
        def get_message_timestamp(message_element) -> Optional[float]:
            """从消息元素中提取时间戳"""
            timestamp_result = None
            extraction_method = ""
            raw_value = ""
            
            try:
                # 方式1: 从 data-pre-plain-text 属性中提取时间（最可靠的方式）
                # 格式示例: 
                #   - "[11:06, 12/18/2025] Jun Cu: " (月/日/年)
                #   - "[10:14, 2025年12月18日] Jun Cu: " (年月日)
                try:
                    # 查找包含 data-pre-plain-text 的元素（可能是消息元素本身或其父元素）
                    copyable_text = None
                    try:
                        # 先尝试从消息元素本身获取
                        pre_plain_text = message_element.get_attribute('data-pre-plain-text')
                        if pre_plain_text:
                            copyable_text = message_element
                            raw_value = pre_plain_text
                    except:
                        pass
                    
                    # 如果消息元素本身没有，尝试查找父元素
                    if not copyable_text:
                        try:
                            copyable_text = message_element.find_element(By.CSS_SELECTOR, 
                                'div.copyable-text[data-pre-plain-text], [data-pre-plain-text]')
                            if copyable_text:
                                raw_value = copyable_text.get_attribute('data-pre-plain-text') or ""
                        except:
                            # 尝试向上查找父元素
                            try:
                                copyable_text = message_element.find_element(By.XPATH, 
                                    './ancestor::div[@class="copyable-text"][@data-pre-plain-text]')
                                if copyable_text:
                                    raw_value = copyable_text.get_attribute('data-pre-plain-text') or ""
                            except:
                                pass
                    
                    if copyable_text and raw_value:
                        extraction_method = "data-pre-plain-text"
                        # 解析格式: "[11:06, 12/18/2025]" (月/日/年格式)
                        match = re.match(r'\[(\d{1,2}):(\d{2}),\s*(\d{1,2})/(\d{1,2})/(\d{4})\]', raw_value)
                        if match:
                            hour, minute, month, day, year = map(int, match.groups())
                            current_year = datetime.now().year
                            dt = datetime(year, month, day, hour, minute, 0)
                            # 只有当日期明显是未来时间（超过当前时间1小时以上）时，才考虑修正年份
                            # 这样可以避免误修正当前年份的正常日期
                            if dt > datetime.now() + timedelta(hours=1):
                                # 如果年份比当前年份大1年以上，可能是年份错误，修正为当前年份
                                if year > current_year + 1:
                                    logger.warning(f"⚠️  检测到异常未来年份 {year}（当前年份: {current_year}），修正为当前年份")
                                    year = current_year
                                    dt = datetime(year, month, day, hour, minute, 0)
                                # 如果修正后仍然是未来时间，尝试前一年（可能是月份/日期错误）
                                if dt > datetime.now() + timedelta(hours=1):
                                    year = current_year - 1
                                    dt = datetime(year, month, day, hour, minute, 0)
                                    logger.warning(f"⚠️  修正后的日期仍然是未来时间，尝试前一年: {year}")
                            timestamp_result = dt.timestamp()
                            logger.info(f"⏰ 提取到消息时间 [{extraction_method}]: {raw_value} -> {dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result})")
                            return timestamp_result
                        
                        # 解析格式: "[10:14, 2025年12月18日]" (年月日格式)
                        match = re.match(r'\[(\d{1,2}):(\d{2}),\s*(\d{4})年(\d{1,2})月(\d{1,2})日\]', raw_value)
                        if match:
                            hour, minute, year, month, day = map(int, match.groups())
                            current_year = datetime.now().year
                            dt = datetime(year, month, day, hour, minute, 0)
                            # 只有当日期明显是未来时间（超过当前时间1小时以上）时，才考虑修正年份
                            # 这样可以避免误修正当前年份的正常日期
                            if dt > datetime.now() + timedelta(hours=1):
                                # 如果年份比当前年份大1年以上，可能是年份错误，修正为当前年份
                                if year > current_year + 1:
                                    logger.warning(f"⚠️  检测到异常未来年份 {year}（当前年份: {current_year}），修正为当前年份")
                                    year = current_year
                                    dt = datetime(year, month, day, hour, minute, 0)
                                # 如果修正后仍然是未来时间，尝试前一年（可能是月份/日期错误）
                                if dt > datetime.now() + timedelta(hours=1):
                                    year = current_year - 1
                                    dt = datetime(year, month, day, hour, minute, 0)
                                    logger.warning(f"⚠️  修正后的日期仍然是未来时间，尝试前一年: {year}")
                            timestamp_result = dt.timestamp()
                            logger.info(f"⏰ 提取到消息时间 [{extraction_method}]: {raw_value} -> {dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result})")
                            return timestamp_result
                        
                        # 解析格式: "[11:06]" (只有时间，假设是今天)
                        match = re.match(r'\[(\d{1,2}):(\d{2})\]', raw_value)
                        if match:
                            hour, minute = map(int, match.groups())
                            now = datetime.now()
                            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            # 如果时间比当前时间晚，说明是昨天的时间
                            if dt > now:
                                dt = dt - timedelta(days=1)
                            timestamp_result = dt.timestamp()
                            logger.info(f"⏰ 提取到消息时间 [{extraction_method}]: {raw_value} -> {dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result})")
                            return timestamp_result
                        
                        # 如果匹配失败，记录原始值
                        logger.info(f"⏰ 提取消息时间 [{extraction_method}]: 原始值={raw_value}, 解析结果=空 (无法匹配已知格式)")
                except Exception as e:
                    logger.info(f"⏰ 提取消息时间 [data-pre-plain-text]: 原始值=空, 解析结果=空 (异常: {e})")
                """
                #方式2: 查找时间元素（通常在消息气泡内或旁边）  这个方法目前不用
                if not timestamp_result:
                    extraction_method = "时间元素"
                    time_elements = message_element.find_elements(
                    By.CSS_SELECTOR,
                        'span[data-testid="msg-time"], span[title*=":"], span[aria-label*=":"], .message-time'
                    )

                    if time_elements:
                        for time_el in time_elements:
                            time_text = time_el.get_attribute('title') or time_el.get_attribute('aria-label') or time_el.text
                            raw_value = time_text or ""
                            if time_text:
                                timestamp = parse_time_string(time_text)
                                if timestamp:
                                    timestamp_result = timestamp
                                    dt = datetime.fromtimestamp(timestamp)
                                    logger.info(f"⏰ 提取到消息时间 [{extraction_method}]: {raw_value} -> {dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result})")
                                    return timestamp_result
                        logger.info(f"⏰ 提取消息时间 [{extraction_method}]: 原始值={raw_value}, 解析结果=空 (无法解析时间文本)")
                    else:
                        logger.info(f"⏰ 提取消息时间 [{extraction_method}]: 原始值=空, 解析结果=空 (未找到时间元素)")

                #方式3: 从消息容器的data-*属性中获取   这个方法目前不用
                if not timestamp_result:
                    extraction_method = "data-*属性"
                    data_time = message_element.get_attribute('data-time') or message_element.get_attribute('data-timestamp')
                    raw_value = data_time or ""
                    if data_time:
                        try:
                            timestamp_result = float(data_time)
                            dt = datetime.fromtimestamp(timestamp_result)
                            logger.info(f"⏰ 提取到消息时间 [{extraction_method}]: {raw_value} -> {dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result})")
                            return timestamp_result
                        except Exception as e:
                            logger.info(f"⏰ 提取消息时间 [{extraction_method}]: 原始值={raw_value}, 解析结果=空 (转换失败: {e})")
                    else:
                        logger.info(f"⏰ 提取消息时间 [{extraction_method}]: 原始值=空, 解析结果=空 (未找到data-time或data-timestamp属性)")
                """
                # 方式4: 如果都获取不到，使用当前时间（不理想，但至少能工作）
                if not timestamp_result:
                    extraction_method = "当前时间(降级)"
                    current_time = time.time()
                    timestamp_result = current_time
                    dt = datetime.fromtimestamp(current_time)
                    logger.warning(f"⚠️  提取消息时间 [{extraction_method}]: 原始值=空, 解析结果={dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result}) - 使用当前时间作为降级方案")
                    return timestamp_result
                    
            except Exception as e:
                extraction_method = "异常处理"
                current_time = time.time()
                timestamp_result = current_time
                dt = datetime.fromtimestamp(current_time)
                logger.error(f"❌ 提取消息时间 [{extraction_method}]: 原始值=空, 解析结果={dt.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {timestamp_result}) - 异常: {e}")
                return timestamp_result
        
        while True:
            try:
                loop_count += 1
                if loop_count % 10 == 0:  # 每10次循环输出一次状态
                    logger.info(f"监听循环运行中... (第 {loop_count} 次循环)")
                
                # 确保在WhatsApp Web页面
                if "web.whatsapp.com" not in self.driver.current_url:
                    logger.info("不在WhatsApp Web页面，正在跳转...")
                    self.driver.get(WHATSAPP_WEB_URL)
                    time.sleep(2)
                
                # 获取所有聊天列表项（不依赖未读标记）
                chat_items = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="gridcell"]')
                
                if not chat_items:
                    if loop_count == 1 or loop_count % 20 == 0:  # 首次或每20次输出一次
                        logger.warning("未找到聊天列表项，可能页面未加载完成，等待...")
                    time.sleep(3)
                    continue
                
                if loop_count == 1 or loop_count % 20 == 0:
                    logger.info(f"找到 {len(chat_items)} 个聊天项，开始检查新消息...")
                
                # 记录当前检查时间
                current_check_time = time.time()
                
                logger.info(f"🔄 开始遍历 {len(chat_items)} 个聊天项...")
                for chat_item in chat_items:
                    try:
                        # 获取联系人名称
                        try:
                            name_element = chat_item.find_element(By.CSS_SELECTOR, 'span[title]')
                            contact_name = name_element.get_attribute('title') or ""
                        except:
                            logger.debug("无法获取联系人名称，跳过此项")
                            continue
                        
                        if not contact_name:
                            continue
                        
                        # 检查是否应该监听这个联系人
                        if not should_listen(contact_name, False):
                            if loop_count == 1:
                                logger.debug(f"跳过未配置的联系人: {contact_name}")
                            continue
                        
                        # 获取最后消息预览和时间（从聊天列表项中）
                        try:
                            # 尝试获取消息预览文本
                            preview_elements = chat_item.find_elements(By.CSS_SELECTOR, 
                                'span[dir="ltr"], span[dir="auto"], .selectable-text')
                            last_preview = ""
                            if preview_elements:
                                last_preview = preview_elements[-1].text.strip()
                            
                            # 尝试获取时间（通常在聊天列表项的右侧）
                            #title属性值包含冒号的<span>元素, aria-label属性值包含冒号的<span>元素
                            time_elements = chat_item.find_elements(By.CSS_SELECTOR, 
                                'span[title*=":"], span[aria-label*=":"]')
                            list_time_str = ""
                            if time_elements:
                                list_time_str = time_elements[-1].get_attribute('title') or \
                                              time_elements[-1].get_attribute('aria-label') or \
                                              time_elements[-1].text
                        except Exception as e:
                            logger.debug(f"获取聊天列表项信息失败: {e}")
                            last_preview = ""
                            list_time_str = ""
                        
                        # 检查是否需要处理这个聊天
                        # 如果之前记录过这个联系人的最后处理时间，且列表中的时间没有更新，跳过
                        if contact_name in last_processed_times:
                            list_timestamp = parse_time_string(list_time_str) if list_time_str else None
                            if list_timestamp and list_timestamp <= last_processed_times[contact_name]:
                                continue  # 没有新消息，跳过
                        
                        # 点击打开聊天（如果当前不在这个聊天窗口）
                        try:
                            current_chat_name = ""
                            try:
                                current_chat_name = self._get_current_chat_name() or ""
                            except:
                                pass
                            
                            if current_chat_name != contact_name:
                                chat_item.click()
                                time.sleep(1.5)  # 等待聊天窗口加载
                        except Exception as e:
                            logger.debug(f"打开聊天失败 {contact_name}: {e}")
                            continue
                        
                        # 获取聊天窗口中的消息
                        # 注意：最新版 WhatsApp Web 可能不再使用 msg-container
                        # 尝试多个备选选择器以提高兼容性
                        try:
                            messages = []
                            
                            # 方式1: 尝试新的消息容器选择器（role="row"）
                            try:
                                messages = self.driver.find_elements(
                                    By.CSS_SELECTOR,
                                    'div[role="row"]'
                                )
                                # 过滤掉非消息的行（如日期分隔符等）
                                # 消息行通常包含 selectable-text 或 copyable-text
                                filtered_messages = []
                                for msg in messages:
                                    try:
                                        # 检查是否包含消息文本元素
                                        if msg.find_elements(By.CSS_SELECTOR, 'span[data-testid="selectable-text"], div.copyable-text, [data-pre-plain-text]'):
                                            filtered_messages.append(msg)
                                    except:
                                        continue
                                if filtered_messages:
                                    messages = filtered_messages
                                    logger.info(f"使用 role='row' 选择器找到 {len(messages)} 条消息")
                            except Exception as e:
                                logger.info(f"尝试 role='row' 选择器失败: {e}")
                            
                            # 方式2: 如果方式1失败，尝试旧的 msg-container（向后兼容）
                            if not messages:
                                try:
                                    messages = self.driver.find_elements(
                                        By.CSS_SELECTOR,
                                        '[data-testid="msg-container"]'
                                    )
                                    if messages:
                                        logger.info(f"使用 msg-container 选择器找到 {len(messages)} 条消息")
                                except Exception as e:
                                    logger.info(f"尝试 msg-container 选择器失败: {e}")
                            
                            # 方式3: 尝试其他可能的选择器
                            if not messages:
                                try:
                                    # 尝试查找包含 copyable-text 的父容器
                                    copyable_elements = self.driver.find_elements(
                                        By.CSS_SELECTOR,
                                        'div.copyable-text[data-pre-plain-text]'
                                    )
                                    if copyable_elements:
                                        # 获取每个 copyable-text 的父容器（通常是消息容器）
                                        messages = []
                                        for el in copyable_elements:
                                            try:
                                                # 向上查找包含该元素的 role="row" 或消息容器
                                                parent = el.find_element(By.XPATH, './ancestor::div[contains(@class, "message") or @role="row"][1]')
                                                if parent not in messages:
                                                    messages.append(parent)
                                            except:
                                                # 如果找不到父容器，直接使用 copyable-text 元素本身
                                                if el not in messages:
                                                    messages.append(el)
                                        if messages:
                                            logger.info(f"使用 copyable-text 父容器找到 {len(messages)} 条消息")
                                except Exception as e:
                                    logger.info(f"尝试 copyable-text 父容器选择器失败: {e}")
                            
                            if not messages:
                                logger.info(f"未找到任何消息容器，跳过聊天: {contact_name}")
                                continue
                            
                            logger.info(f"成功找到 {len(messages)} 条消息容器")
                            
                            # 判断是否为群组（如果发现是群组，则跳过）
                            try:
                                is_group = len(self.driver.find_elements(
                                    By.CSS_SELECTOR,
                                    '[data-testid="group-info"]'
                                )) > 0
                            except:
                                is_group = False
                            
                            # 不处理群组消息
                            if is_group:
                                if loop_count == 1:
                                    logger.debug(f"跳过群组: {contact_name}")
                                continue
                            
                            # 再次检查是否应该监听
                            if not should_listen(contact_name, False):
                                if loop_count == 1:
                                    logger.debug(f"跳过未配置的联系人: {contact_name}")
                                continue

                            # 获取上次处理的消息索引（用于处理同一时间戳的多条消息）
                            last_processed_index_key = f"{contact_name}_last_index"
                            if not hasattr(self, '_last_processed_indices'):
                                self._last_processed_indices = {}
                            last_processed_index = self._last_processed_indices.get(last_processed_index_key, -1)
                            logger.debug(f"📋 联系人 {contact_name} 的处理索引: {last_processed_index}")
                            # 边界检查：如果上次处理的索引 >= 当前消息数量，说明消息数量发生了变化
                            # 可能原因：1) 消息被删除 2) WhatsApp Web 懒加载只显示了部分消息 3) 消息过滤后数量减少
                            if last_processed_index >= len(messages):
                                logger.warning(f"⚠️  上次处理索引 ({last_processed_index}) >= 当前消息数量 ({len(messages)})，可能是消息被删除或只加载了部分消息，重置索引为 -1")
                                last_processed_index = -1
                                # 重置索引，避免后续处理出错
                                self._last_processed_indices[last_processed_index_key] = -1
                            
                            # 获取上次处理的时间戳
                            last_processed_time = last_processed_times.get(contact_name, 0)
                            
                            # 处理所有可能的新消息（从上次处理的索引之后开始）
                            new_messages_processed = 0
                            
                            # 从后往前遍历消息，找到所有新消息
                            # 注意：messages[-1] 是最新的消息
                            logger.info(f"📊 开始处理聊天 {contact_name} 的消息，共 {len(messages)} 条消息，上次处理索引: {last_processed_index}")
                            
                            # 计算需要处理的消息范围
                            start_index = len(messages) - 1
                            end_index = last_processed_index
                            # 计算实际需要处理的消息数量
                            # 如果 last_processed_index = -1，需要处理所有消息（从 start_index 到 0）
                            # 如果 last_processed_index >= 0，需要处理从 start_index 到 last_processed_index + 1 的消息
                            if last_processed_index == -1:
                                # 第一次处理，需要处理所有消息
                                messages_to_process = len(messages)
                                logger.info(f"📋 消息处理范围: 从索引 {start_index} 到 0 (共 {messages_to_process} 条消息需要处理，第一次处理)")
                            else:
                                # 非第一次处理，只处理新消息
                                messages_to_process = max(0, start_index - last_processed_index)
                                logger.info(f"📋 消息处理范围: 从索引 {start_index} 到 {last_processed_index + 1} (共 {messages_to_process} 条消息需要处理)")
                            
                            if messages_to_process == 0:
                                logger.info(f"⏭️  没有新消息需要处理 (start_index={start_index}, last_processed_index={last_processed_index})")
                            else:
                                logger.info(f"✅ 开始遍历消息，从索引 {start_index} 到 {max(-1, last_processed_index)}")
                            
                            # 修复循环范围：如果 last_processed_index = -1，处理所有消息（到 -1，不包括 -1）
                            # 如果 last_processed_index >= 0，处理从 start_index 到 last_processed_index（不包括 last_processed_index）
                            # 使用 last_processed_index - 1 作为结束，这样如果 last_processed_index = 0，会处理索引 0
                            for msg_index in range(len(messages) - 1, last_processed_index - 1, -1):
                                if msg_index < 0:
                                    logger.info(f"⚠️  消息索引 {msg_index} < 0，退出循环")
                                    break
                                
                                try:
                                    message = messages[msg_index]
                                    logger.info(f"🔍 正在处理消息 [{msg_index}/{len(messages)-1}]")
                                    
                                    # 获取消息文本
                                    message_text = ""
                                    extraction_method = ""
                                    try:
                                        # 方式1: 查找 data-testid="selectable-text" 元素（最可靠的方式）
                                        # 注意：消息文本可能在 selectable-text 内的嵌套 span 中
                                        extraction_method = "selectable-text"
                                        selectable_text_elements = message.find_elements(
                                            By.CSS_SELECTOR,
                                            'span[data-testid="selectable-text"]'
                                        )
                                        
                                        if selectable_text_elements:
                                            # 获取所有 selectable-text 元素的完整文本（包括嵌套的文本）
                                            texts = []
                                            for el in selectable_text_elements:
                                                # 获取元素的完整文本内容（包括所有子元素的文本）
                                                text = el.text.strip()
                                                if text:
                                                    texts.append(text)
                                            
                                            if texts:
                                                # 合并所有文本，用空格分隔
                                                message_text = " ".join(texts).strip()
                                                
                                                # 🔒 检查并移除可能包含的发送者名称
                                                try:
                                                    # 尝试从消息元素中获取发送者名称
                                                    copyable_text = message.find_element(By.CSS_SELECTOR, 
                                                        'div.copyable-text[data-pre-plain-text], [data-pre-plain-text]')
                                                    pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                                                    if pre_plain_text:
                                                        match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                                                        if match:
                                                            sender_name = match.group(1).strip()
                                                            # 如果消息文本以发送者名称开头，移除它
                                                            if message_text.startswith(sender_name):
                                                                message_text = message_text[len(sender_name):].strip()
                                                                # 移除可能的分隔符（冒号、空格等）
                                                                message_text = re.sub(r'^[:：]\s*', '', message_text)
                                                                logger.debug(f"🔍 从消息文本开头移除了发送者名称: {sender_name}")
                                                            # 如果消息文本中包含发送者名称（可能在中间），也尝试移除
                                                            elif sender_name in message_text:
                                                                # 使用正则表达式移除发送者名称及其后的分隔符
                                                                patterns_to_remove = [
                                                                    re.escape(sender_name) + r'\s*[:：]\s*',  # "发送者: "
                                                                    re.escape(sender_name) + r'\s+',  # "发送者 "
                                                                    r'^' + re.escape(sender_name) + r'\s*',  # 开头的发送者名称
                                                                ]
                                                                for pattern in patterns_to_remove:
                                                                    message_text = re.sub(pattern, '', message_text, flags=re.IGNORECASE)
                                                                message_text = message_text.strip()
                                                                logger.debug(f"🔍 从消息文本中移除了发送者名称: {sender_name}")
                                                except:
                                                    pass
                                                
                                                logger.info(f"📝 提取到消息内容 [{extraction_method}]: {message_text}")
                                            else:
                                                logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值=找到{len(selectable_text_elements)}个元素, 解析结果=空 (元素存在但文本为空)")
                                        else:
                                            logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值=空, 解析结果=空 (未找到selectable-text元素)")
                                        """
                                        # 方式2: 如果方式1失败，尝试从 copyable-text 中获取  使用这个方法获取到的内容不够准确故先不用
                                        if not message_text:
                                            extraction_method = "copyable-text"
                                            try:
                                                copyable_text = message.find_element(By.CSS_SELECTOR, 
                                                    'div.copyable-text, [class*="copyable-text"]')
                                                if copyable_text:
                                                    # 获取整个 copyable-text 的文本，但排除时间部分和发送者名称
                                                    full_text = copyable_text.text.strip()
                                                    raw_text = full_text
                                                    
                                                    # 🔒 先尝试从 data-pre-plain-text 中提取发送者名称，然后从文本中移除
                                                    sender_name_to_remove = None
                                                    try:
                                                        pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                                                        if pre_plain_text:
                                                            # 提取发送者名称（冒号前的部分）
                                                            match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                                                            if match:
                                                                sender_name_to_remove = match.group(1).strip()
                                                    except:
                                                        pass
                                                    
                                                    # 如果找到了发送者名称，从文本中移除
                                                    if sender_name_to_remove:
                                                        # 移除发送者名称（可能在文本开头或中间）
                                                        # 使用正则表达式移除，支持多种格式
                                                        patterns_to_remove = [
                                                            re.escape(sender_name_to_remove) + r'\s*[:：]\s*',  # "发送者: "
                                                            re.escape(sender_name_to_remove) + r'\s+',  # "发送者 "
                                                            r'^' + re.escape(sender_name_to_remove) + r'\s*',  # 开头的发送者名称
                                                        ]
                                                        for pattern in patterns_to_remove:
                                                            full_text = re.sub(pattern, '', full_text, flags=re.IGNORECASE)
                                                        full_text = full_text.strip()
                                                        logger.debug(f"🔍 从消息文本中移除了发送者名称: {sender_name_to_remove}")
                                                    
                                                    # 尝试移除时间部分（格式如 "11:06"）
                                                    full_text = re.sub(r'\d{1,2}:\d{2}', '', full_text).strip()
                                                    
                                                    if full_text:
                                                        message_text = full_text
                                                        logger.info(f"📝 提取到消息内容 [{extraction_method}]: {message_text}")
                                                    else:
                                                        logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值={raw_text[:50] if raw_text else '空'}, 解析结果=空 (移除时间后为空)")
                                                else:
                                                    logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值=空, 解析结果=空 (未找到copyable-text元素)")
                                            except Exception as e:
                                                logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值=空, 解析结果=空 (异常: {e})")
                                    
                                        # 方式3: 如果前两种方式都失败，尝试其他选择器  使用这个方法容易导致获取到的是其它联系人名字
                                        if not message_text:
                                            extraction_method = "其他选择器"
                                            message_text_elements = message.find_elements(
                                                By.CSS_SELECTOR,
                                                'span[data-testid="msg-text"], span.selectable-text, span[dir="ltr"], span[dir="auto"]'
                                            )
                                            if message_text_elements:
                                                for el in reversed(message_text_elements):
                                                    text = el.text.strip()
                                                    # 排除时间文本（如 "11:06"）
                                                    if text and not re.match(r'^\d{1,2}:\d{2}$', text):
                                                        if len(text) > len(message_text):
                                                            message_text = text
                                                if message_text:
                                                    # 🔒 检查并移除可能包含的发送者名称
                                                    try:
                                                        copyable_text = message.find_element(By.CSS_SELECTOR, 
                                                            'div.copyable-text[data-pre-plain-text], [data-pre-plain-text]')
                                                        pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                                                        if pre_plain_text:
                                                            match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                                                            if match:
                                                                sender_name = match.group(1).strip()
                                                                # 移除发送者名称（可能在文本开头或中间）
                                                                patterns_to_remove = [
                                                                    re.escape(sender_name) + r'\s*[:：]\s*',  # "发送者: "
                                                                    re.escape(sender_name) + r'\s+',  # "发送者 "
                                                                    r'^' + re.escape(sender_name) + r'\s*',  # 开头的发送者名称
                                                                ]
                                                                for pattern in patterns_to_remove:
                                                                    message_text = re.sub(pattern, '', message_text, flags=re.IGNORECASE)
                                                                message_text = message_text.strip()
                                                                logger.debug(f"🔍 从消息文本中移除了发送者名称: {sender_name}")
                                                    except:
                                                        pass
                                                    
                                                    logger.info(f"📝 提取到消息内容 [{extraction_method}]: {message_text}")
                                                else:
                                                    logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值=找到{len(message_text_elements)}个元素, 解析结果=空 (所有元素文本为空或为时间)")
                                            else:
                                                logger.info(f"📝 提取消息内容 [{extraction_method}]: 原始值=空, 解析结果=空 (未找到其他选择器元素)") 
                                        
                                        # 无论是否获取到内容，都打印最终结果
                                        """
                                        if message_text:
                                            logger.info(f"📋 消息 [{msg_index}] 内容提取完成 - 内容: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")
                                        else:
                                            logger.info(f"📋 消息 [{msg_index}] 内容提取完成 - 内容: 空 (所有提取方式均失败)")
                                        
                                        if not message_text:
                                            # 跳过空消息（可能是系统消息、图片等）
                                            logger.debug(f"消息 [{msg_index}] 没有文本内容，跳过处理")
                                            continue
                                        
                                        # 🔒 检查提取的文本是否只是联系人名称（误提取）
                                        try:
                                            # 检查消息文本是否与当前聊天的联系人名称相同
                                            if message_text.strip() == contact_name.strip():
                                                logger.warning(f"⚠️  检测到消息文本与联系人名称相同，可能是误提取: {message_text}")
                                                logger.info(f"⏭️  跳过此消息: 文本='{message_text}' = 联系人名称='{contact_name}'")
                                                continue
                                            
                                            # 检查消息文本是否与发送者名称相同
                                            try:
                                                copyable_text = message.find_element(By.CSS_SELECTOR, 
                                                    'div.copyable-text[data-pre-plain-text], [data-pre-plain-text]')
                                                pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                                                if pre_plain_text:
                                                    match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                                                    if match:
                                                        sender_name = match.group(1).strip()
                                                        # 如果消息文本只包含发送者名称（没有其他内容），跳过
                                                        if message_text.strip() == sender_name.strip():
                                                            logger.warning(f"⚠️  检测到消息文本与发送者名称相同，可能是误提取: {message_text}")
                                                            logger.info(f"⏭️  跳过此消息: 文本='{message_text}' = 发送者名称='{sender_name}'")
                                                            continue
                                                        # 如果消息文本以发送者名称开头且后面没有其他有意义的内容，跳过
                                                        if message_text.strip().startswith(sender_name.strip()):
                                                            remaining_text = message_text[len(sender_name):].strip()
                                                            remaining_text = re.sub(r'^[:：]\s*', '', remaining_text)
                                                            if not remaining_text or len(remaining_text) < 2:
                                                                logger.warning(f"⚠️  检测到消息文本只包含发送者名称，可能是误提取: {message_text}")
                                                                logger.info(f"⏭️  跳过此消息: 文本='{message_text}'")
                                                                continue
                                            except:
                                                pass
                                            
                                            # 检查消息文本是否只包含联系人名称的一部分（可能是误提取的联系人名称标签）
                                            # 如果消息文本很短（少于5个字符）且与联系人名称相似，可能是误提取
                                            if len(message_text.strip()) < 5:
                                                # 检查是否与联系人名称的开头或结尾匹配
                                                contact_name_lower = contact_name.strip().lower()
                                                message_text_lower = message_text.strip().lower()
                                                if (contact_name_lower.startswith(message_text_lower) or 
                                                    contact_name_lower.endswith(message_text_lower) or
                                                    message_text_lower in contact_name_lower):
                                                    logger.warning(f"⚠️  检测到消息文本可能是联系人名称的一部分: {message_text}")
                                                    logger.info(f"⏭️  跳过此消息: 文本='{message_text}' (可能是联系人名称的一部分)")
                                                    continue
                                        except Exception as e:
                                            logger.debug(f"检查联系人名称匹配时出错: {e}")
                                        
                                        # 🔒 检查是否为系统消息（系统提示信息）
                                        is_system_message = False
                                        try:
                                            # 方式1: 检查消息元素的CSS类名或属性（系统消息通常有特定标识）
                                            message_classes = message.get_attribute('class') or ''
                                            message_aria_label = message.get_attribute('aria-label') or ''
                                            
                                            # 系统消息的常见特征
                                            system_indicators = [
                                                'system', 'notification', 'info', 'encryption',
                                                '端到端', '加密', '系统', '通知'
                                            ]
                                            
                                            if any(indicator.lower() in message_classes.lower() or 
                                                   indicator.lower() in message_aria_label.lower() 
                                                   for indicator in system_indicators):
                                                is_system_message = True
                                                logger.info(f"🔍 检测到系统消息 [CSS/属性]: 类名={message_classes[:50]}, aria-label={message_aria_label[:50]}")
                                            
                                            # 方式2: 检查消息文本内容（常见的系统提示文本）
                                            if not is_system_message:
                                                system_message_patterns = [
                                                    r'消息和通话已进行端到端加密',
                                                    r'Messages and calls are end-to-end encrypted',
                                                    r'端到端加密',
                                                    r'end-to-end encrypted',
                                                    r'只有此聊天中的成员可以',
                                                    r'Only members in this chat can',
                                                    r'点击了解更多',
                                                    r'Click to learn more',
                                                    r'此消息已删除',
                                                    r'This message was deleted',
                                                    r'已撤回',
                                                    r'deleted',
                                                    r'系统消息',
                                                    r'System message',
                                                ]
                                                
                                                for pattern in system_message_patterns:
                                                    if re.search(pattern, message_text, re.IGNORECASE):
                                                        is_system_message = True
                                                        logger.info(f"🔍 检测到系统消息 [文本匹配]: 匹配模式={pattern}, 消息内容={message_text[:100]}")
                                                        break
                                            
                                            # 方式3: 检查是否有发送者信息（系统消息通常没有发送者）
                                            if not is_system_message:
                                                try:
                                                    copyable_text = message.find_element(By.CSS_SELECTOR, 
                                                        'div.copyable-text[data-pre-plain-text], [data-pre-plain-text]')
                                                    pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''
                                                    
                                                    # 如果没有data-pre-plain-text或格式不包含发送者名称，可能是系统消息
                                                    if not pre_plain_text or not re.search(r'\]\s*([^:]+):\s*$', pre_plain_text):
                                                        # 进一步检查：如果消息在中间位置（不是左侧也不是右侧），可能是系统消息
                                                        try:
                                                            parent = message.find_element(By.XPATH, './ancestor::div[@role="row"][1]')
                                                            location = parent.location
                                                            size = parent.size
                                                            window_width = self.driver.execute_script("return window.innerWidth;")
                                                            
                                                            # 系统消息通常在中间位置（不在左侧也不在右侧）
                                                            message_center = location['x'] + size['width'] / 2
                                                            window_center = window_width / 2
                                                            is_center = abs(message_center - window_center) < window_width * 0.2
                                                            
                                                            # 如果消息在中间位置且没有发送者信息，很可能是系统消息
                                                            if is_center and not pre_plain_text:
                                                                is_system_message = True
                                                                logger.info(f"🔍 检测到系统消息 [位置+无发送者]: 消息在中间位置(x={location['x']:.0f}, 中心={message_center:.0f}, 窗口中心={window_center:.0f})且无发送者信息")
                                                        except Exception as e:
                                                            logger.debug(f"检查消息位置时出错: {e}")
                                                except:
                                                    # 如果找不到data-pre-plain-text，可能是系统消息
                                                    # 但需要进一步确认（可能是图片消息或其他类型消息）
                                                    pass
                                            
                                            # 方式4: 检查消息气泡的样式（系统消息通常有特殊的背景色或样式）
                                            if not is_system_message:
                                                try:
                                                    # 查找消息气泡元素
                                                    bubble_elements = message.find_elements(By.CSS_SELECTOR, 
                                                        'div[class*="message"], div[class*="bubble"], div[class*="system"]')
                                                    
                                                    for bubble in bubble_elements:
                                                        bubble_classes = bubble.get_attribute('class') or ''
                                                        bubble_style = bubble.get_attribute('style') or ''
                                                        
                                                        # 系统消息通常有特定的类名或样式
                                                        if any(keyword in bubble_classes.lower() for keyword in ['system', 'notification', 'info', 'encryption']):
                                                            is_system_message = True
                                                            logger.info(f"🔍 检测到系统消息 [气泡样式]: 类名={bubble_classes[:50]}")
                                                            break
                                                except:
                                                    pass
                                            
                                        except Exception as e:
                                            logger.debug(f"检查系统消息时出错: {e}")
                                        
                                        # 如果是系统消息，跳过处理
                                        if is_system_message:
                                            logger.info(f"⏭️  跳过系统消息 [{msg_index}]: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")
                                            continue
                                        
                                    except Exception as e:
                                        logger.error(f"❌ 提取消息内容 [{extraction_method}]: 原始值=空, 解析结果=空 (异常: {e})")
                                        logger.info(f"📋 消息 [{msg_index}] 内容提取完成 - 内容: 空 (提取过程异常)")
                                        continue
                                    
                                    # 判断消息是否是自己发送的（优先使用 data-pre-plain-text 中的发送者名称）
                                    # 这是最可靠的方法，因为 data-pre-plain-text 明确标识了消息的发送者
                                    is_sent = False
                                    sender_name = None
                                    direction_determined = False

                                    try:
                                        # 方式1: 优先从 data-pre-plain-text 中提取发送者名称并判断（最可靠）
                                        try:
                                            copyable_text = message.find_element(By.CSS_SELECTOR,
                                                'div.copyable-text[data-pre-plain-text], [data-pre-plain-text]')
                                            pre_plain_text = copyable_text.get_attribute('data-pre-plain-text') or ''

                                            if pre_plain_text:
                                                # 格式: "[16:37, 2025年12月18日] Freya: " 或 "[16:37, 12/18/2025] Freya: "
                                                # 提取发送者名称（冒号前的部分）
                                                match = re.search(r'\]\s*([^:]+):\s*$', pre_plain_text)
                                                if match:
                                                    sender_name = match.group(1).strip()

                                                    if sender_name:
                                                        # 获取登录账号昵称（如果还没有获取，尝试获取）
                                                        user_name = self.get_user_name()
                                                        
                                                        # 优先使用名称判断（最可靠）
                                                        try:
                                                            if user_name:
                                                                # 方式1: 优先使用名称判断
                                                                if sender_name == user_name:
                                                                    is_sent = True
                                                                    direction_determined = True
                                                                    logger.info(f"📤 消息方向判断 [名称优先]: 发送 (发送者: {sender_name} = 账号昵称: {user_name})")
                                                                else:
                                                                    is_sent = False
                                                                    direction_determined = True
                                                                    logger.info(f"📤 消息方向判断 [名称优先]: 接收 (发送者: {sender_name} ≠ 账号昵称: {user_name})")
                                                            else:
                                                                # 无法获取账号昵称，使用位置判断
                                                                logger.info(f"📤 无法获取账号昵称，使用位置判断 (发送者: {sender_name})")
                                                                # 不设置 direction_determined，让位置判断来处理
                                                        except Exception as e:
                                                            logger.warning(f"📤 名称判断失败: {e}，使用位置判断")
                                                            # 不设置 direction_determined，让位置判断来处理
                                                        
                                                        # 如果名称判断未确定方向，使用位置判断
                                                        if not direction_determined:
                                                            try:
                                                                parent = copyable_text.find_element(By.XPATH,
                                                                                                    './ancestor::div[@role="row"][1]')
                                                                location = parent.location
                                                                size = parent.size
                                                                window_width = self.driver.execute_script("return window.innerWidth;")
                                                                
                                                                # 计算消息位置
                                                                message_right_edge = location['x'] + size['width']
                                                                is_right_side = message_right_edge > window_width * 0.6
                                                                is_left_side = location['x'] < window_width * 0.4
                                                                
                                                                # 使用位置判断
                                                                if is_right_side:
                                                                    is_sent = True
                                                                    direction_determined = True
                                                                    logger.info(f"📤 消息方向判断 [位置判断]: 发送 (发送者: {sender_name}, 消息在右侧, 右边缘: {message_right_edge:.0f}, 窗口宽度: {window_width:.0f})")
                                                                    # 如果发送者名称与账号昵称不同，更新账号昵称
                                                                    if user_name and sender_name != user_name:
                                                                        logger.warning(f"⚠️  账号昵称不匹配: 当前={user_name}, 消息发送者={sender_name}, 将更新账号昵称")
                                                                        self.user_name = sender_name
                                                                        logger.info(f"✅ 已更新账号昵称: {sender_name}")
                                                                    elif not user_name:
                                                                        self.user_name = sender_name
                                                                        logger.info(f"✅ 首次记录账号昵称: {sender_name}")
                                                                elif is_left_side:
                                                                    is_sent = False
                                                                    direction_determined = True
                                                                    logger.info(f"📤 消息方向判断 [位置判断]: 接收 (发送者: {sender_name}, 消息在左侧, x坐标: {location['x']:.0f}, 窗口宽度: {window_width:.0f})")
                                                                    # 如果消息在左侧但发送者名称等于账号昵称，说明账号昵称识别错误，清除它
                                                                    if user_name and sender_name == user_name:
                                                                        logger.warning(f"⚠️  消息在左侧但发送者名称等于账号昵称，说明账号昵称识别错误，清除账号昵称: {user_name}")
                                                                        self.user_name = None
                                                                        logger.info(f"✅ 已清除错误的账号昵称，将重新识别")
                                                                else:
                                                                    # 位置不明确，使用默认值（发送）
                                                                    is_sent = True
                                                                    direction_determined = True
                                                                    logger.info(f"📤 消息方向判断 [位置不明确]: 发送 (发送者: {sender_name}, 位置不明确，默认认为是发送的消息)")
                                                            except Exception as e:
                                                                # 位置判断也失败，使用默认值（发送）
                                                                logger.warning(f"📤 位置判断失败: {e}，使用默认值")
                                                                is_sent = True
                                                                direction_determined = True
                                                                logger.info(f"📤 消息方向判断 [默认]: 发送 (发送者: {sender_name}, 所有判断方法都失败，默认认为是发送的消息)")

                                                    else:
                                                        logger.debug(f"无法从 data-pre-plain-text 中提取发送者名称: {pre_plain_text}")
                                                else:
                                                    logger.debug(f"data-pre-plain-text 格式不匹配: {pre_plain_text}")
                                            else:
                                                logger.debug(f"data-pre-plain-text 为空")
                                        except Exception as e:
                                            logger.debug(f"从 data-pre-plain-text 判断消息方向失败: {e}")

                                        # 方式2: 如果方式1失败（无法从 data-pre-plain-text 判断），使用其他方法判断
                                        if not direction_determined:
                                            # 检查消息容器及其父元素的类名
                                            message_classes = message.get_attribute('class') or ''

                                            # 检查消息容器本身
                                            if any(keyword in message_classes.lower() for keyword in ['message-out', 'outgoing', 'sent']):
                                                is_sent = True
                                            elif any(keyword in message_classes.lower() for keyword in ['message-in', 'incoming', 'received']):
                                                is_sent = False
                                            else:
                                                # 检查父容器
                                                try:
                                                    parent = message.find_element(By.XPATH, './ancestor::div[@role="row"][1]')
                                                    parent_classes = parent.get_attribute('class') or ''

                                                    if any(keyword in parent_classes.lower() for keyword in ['message-out', 'outgoing', 'sent']):
                                                        is_sent = True
                                                    elif any(keyword in parent_classes.lower() for keyword in ['message-in', 'incoming', 'received']):
                                                        is_sent = False
                                                    else:
                                                        # 通过检查消息气泡的位置（计算 x 坐标）
                                                        try:
                                                            window_width = self.driver.execute_script("return window.innerWidth;")
                                                            message_location = message.location
                                                            message_size = message.size

                                                            # 如果消息的 x 坐标 + 宽度 > 窗口宽度的 60%，可能是发送的消息
                                                            if message_location['x'] + message_size['width'] > window_width * 0.6:
                                                                is_sent = True
                                                            elif message_location['x'] < window_width * 0.4:
                                                                is_sent = False
                                                        except:
                                                            pass
                                                except:
                                                    pass

                                            logger.info(f"📤 消息方向判断 [备用方法]: {'发送' if is_sent else '接收'} (类名: {message_classes[:50]})")

                                            # 如果备用方法也无法确定，默认认为是发送的消息
                                            if not direction_determined:
                                                is_sent = True
                                                direction_determined = True
                                                logger.info(f"📤 消息方向判断 [默认]: 发送 (无法确定，默认认为是发送的消息)")
                                    except Exception as e:
                                        logger.debug(f"判断消息方向时出错: {e}，默认标记为发送")
                                        is_sent = True
                                        direction_determined = True

                                    # 最终确认：如果无法确定方向，默认认为是发送的消息
                                    if not direction_determined:
                                        is_sent = True
                                        direction_determined = True
                                        logger.info(f"📤 消息方向判断 [最终默认]: 发送 (所有方法都失败，默认认为是发送的消息)")
                                    
                                    # 打印最终判断结果
                                    direction_text = "发送" if is_sent else "接收"
                                    logger.info(f"✅ 消息方向最终判断结果: {direction_text} (is_sent={is_sent})")
                                    
                                    # 获取消息时间戳
                                    logger.info(f"🔍 开始提取消息 [{msg_index}] 的时间戳...")
                                    message_timestamp = get_message_timestamp(message)
                                    dt_str = datetime.fromtimestamp(message_timestamp).strftime('%Y-%m-%d %H:%M:%S') if message_timestamp else "未知"
                                    logger.info(f"✅ 消息 [{msg_index}] 时间戳提取完成: {dt_str} (时间戳: {message_timestamp})")
                                    
                                    # 生成消息唯一标识（包含索引，确保同一时间戳的多条消息也能区分）
                                    # 使用：联系人 + 消息文本 + 时间戳 + 消息索引
                                    message_id = f"{contact_name}_{message_text}_{message_timestamp}_{msg_index}"
                                    
                                    # 检查是否已处理过（内存中的去重）
                                    if message_id in processed_message_ids:
                                        continue
                                    
                                    # 对于发送的消息，直接跳过处理（不保存到数据库，因为手动发送的消息已经保存了）
                                    # 这样可以避免重复显示手动发送的消息
                                    if is_sent:
                                        logger.debug(f"⏭️  跳过自己发送的消息 [{msg_index}]: {message_text[:50]}... (不保存到数据库，避免重复)")
                                        processed_message_ids.add(message_id)
                                        if msg_index > last_processed_index:
                                            self._last_processed_indices[last_processed_index_key] = msg_index
                                        continue
                                    
                                    # 判断是否为新消息
                                    should_process = False
                                    
                                    if contact_name not in last_processed_times:
                                        # 第一次处理这个联系人，处理所有消息
                                        should_process = True
                                    elif message_timestamp:
                                        # 有时间戳：如果时间戳 >= 上次处理的时间，且索引 >= 上次处理的索引
                                        # 注意：使用 >= 而不是 >，因为如果 last_processed_index = 0 且只有1条消息，需要处理索引 0
                                        if message_timestamp >= last_processed_time and msg_index >= last_processed_index:
                                            should_process = True
                                        # 如果时间戳相同但索引更新，也认为是新消息（同一秒内的多条消息）
                                        elif message_timestamp == last_processed_time and msg_index >= last_processed_index:
                                            should_process = True
                                    else:
                                        # 无法获取时间戳：使用消息文本和索引判断
                                        text_hash = hash(message_text)
                                        last_text_key = f"{contact_name}_last_text"
                                        if not hasattr(self, '_last_text_hashes'):
                                            self._last_text_hashes = {}
                                        
                                        # 如果文本不同或索引更新，认为是新消息
                                        # 注意：使用 >= 而不是 >，因为如果 last_processed_index = 0 且只有1条消息，需要处理索引 0
                                        if last_text_key not in self._last_text_hashes or \
                                           self._last_text_hashes[last_text_key] != text_hash or \
                                           msg_index >= last_processed_index:
                                            should_process = True
                                            self._last_text_hashes[last_text_key] = text_hash
                                    
                                    if should_process:
                                        # 确认这是联系人的新消息，进行自动回复
                                        logger.info(f"✅ 检测到联系人的新消息 [{msg_index}]: {contact_name}, 时间戳: {message_timestamp}, 内容: {message_text[:50]}...")
                                        
                                        # 记录处理信息（只记录联系人的消息）
                                        last_processed_times[contact_name] = message_timestamp or current_check_time
                                        # 确保索引不会回退（虽然循环逻辑保证，但为了健壮性添加检查）
                                        if msg_index > last_processed_index:
                                            self._last_processed_indices[last_processed_index_key] = msg_index
                                        else:
                                            logger.warning(f"⚠️  消息索引 {msg_index} <= 上次处理索引 {last_processed_index}，跳过索引更新")
                                        processed_message_ids.add(message_id)
                                        
                                        # 清理旧的processed_message_ids（保留最近1000条）
                                        if len(processed_message_ids) > 1000:
                                            processed_message_ids = set(list(processed_message_ids)[-500:])
                                        
                                        # 调用回调函数处理联系人的新消息（触发自动回复）
                                        # 传递message_id、message_timestamp和msg_index，确保消息ID一致性
                                        callback(contact_name, contact_name, message_text, is_group, is_sent, 
                                                message_id=message_id, message_timestamp=message_timestamp, msg_index=msg_index)
                                        new_messages_processed += 1
                                        
                                        # 更新最后处理时间（使用实际时间戳或当前时间）
                                        if message_timestamp:
                                            last_processed_times[contact_name] = message_timestamp
                                        else:
                                            last_processed_times[contact_name] = current_check_time
                                
                                except Exception as e:
                                    logger.error(f"❌ 处理消息 [{msg_index}] 时出错: {e}", exc_info=True)
                                    logger.error(f"   消息内容: {message_text[:100] if 'message_text' in locals() else '无法获取'}")
                                    logger.error(f"   联系人: {contact_name}")
                                    continue
                            
                            # 如果没有处理任何新消息，但这是第一次检查，记录最后一条消息的索引
                            if new_messages_processed == 0 and contact_name not in last_processed_times:
                                self._last_processed_indices[last_processed_index_key] = len(messages) - 1
                                last_processed_times[contact_name] = current_check_time
                        
                        except Exception as e:
                            logger.error(f"❌ 处理聊天 {contact_name} 的消息时出错: {e}", exc_info=True)
                            continue
                    
                    except Exception as e:
                        logger.warning(f"⚠️  处理聊天项时出错: {e}", exc_info=True)
                        continue
                
                # 每轮检查间隔
                if loop_count == 1:
                    logger.info(f"首次检查完成，共检查 {len(chat_items)} 个聊天项，下次检查将在3秒后...")
                time.sleep(3)  # 3秒检查一次
            
            except Exception as e:
                logger.error(f"监听消息时出错: {e}", exc_info=True)
                logger.info("监听循环遇到错误，5秒后重试...")
                time.sleep(5)
    
    def set_min_reply_interval(self, interval: int):
        """设置最小回复间隔"""
        self.min_reply_interval = interval
        logger.info(f"最小回复间隔已设置为: {interval}秒")
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            logger.info("浏览器已关闭")

