"""
检查 WhatsApp Web 中是否存在 msg-container 元素
此脚本会打开 WhatsApp Web 并检查 DOM 结构
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_msg_container():
    """检查 WhatsApp Web 中是否存在 msg-container 元素"""
    
    # 配置 Chrome 选项
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # 设置用户代理
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = None
    try:
        logger.info("正在启动浏览器...")
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        
        logger.info("正在访问 WhatsApp Web...")
        driver.get("https://web.whatsapp.com")
        
        logger.info("等待页面加载...")
        logger.info("请手动扫描二维码登录（如果尚未登录）...")
        logger.info("登录后，请打开任意一个聊天窗口，然后按 Enter 继续...")
        
        # 等待用户登录并打开聊天
        input("登录并打开聊天后，按 Enter 继续检查...")
        
        # 等待页面稳定
        time.sleep(3)
        
        # 检查 msg-container 元素
        logger.info("正在检查 msg-container 元素...")
        
        # 方法1: 使用 data-testid="msg-container"
        msg_containers = driver.find_elements(By.CSS_SELECTOR, '[data-testid="msg-container"]')
        logger.info(f"找到 [data-testid='msg-container'] 元素数量: {len(msg_containers)}")
        
        if msg_containers:
            logger.info("✅ 找到 msg-container 元素！")
            # 检查第一个元素的详细信息
            first_msg = msg_containers[0]
            logger.info(f"第一个消息元素的标签: {first_msg.tag_name}")
            logger.info(f"第一个消息元素的类名: {first_msg.get_attribute('class')}")
            logger.info(f"第一个消息元素的 data-testid: {first_msg.get_attribute('data-testid')}")
            
            # 尝试查找消息文本
            try:
                selectable_text = first_msg.find_elements(By.CSS_SELECTOR, 'span[data-testid="selectable-text"]')
                logger.info(f"在消息中找到 selectable-text 元素数量: {len(selectable_text)}")
            except Exception as e:
                logger.warning(f"查找 selectable-text 时出错: {e}")
        else:
            logger.warning("❌ 未找到 [data-testid='msg-container'] 元素")
            
            # 尝试查找其他可能的消息容器选择器
            logger.info("正在尝试查找其他可能的消息容器...")
            
            # 检查常见的消息容器选择器
            alternative_selectors = [
                'div[role="row"]',
                'div[data-testid*="msg"]',
                'div[class*="message"]',
                'div[class*="msg"]',
                'div[data-id]',
            ]
            
            for selector in alternative_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"找到 {selector}: {len(elements)} 个元素")
                        # 检查前几个元素的属性
                        for i, el in enumerate(elements[:3]):
                            logger.info(f"  元素 {i+1}: tag={el.tag_name}, class={el.get_attribute('class')[:100]}, data-testid={el.get_attribute('data-testid')}")
                except Exception as e:
                    logger.debug(f"检查 {selector} 时出错: {e}")
        
        # 获取页面源代码片段（用于调试）
        logger.info("\n正在获取页面结构信息...")
        page_source = driver.page_source
        if 'msg-container' in page_source.lower():
            logger.info("✅ 在页面源代码中找到了 'msg-container' 字符串")
        else:
            logger.warning("❌ 在页面源代码中未找到 'msg-container' 字符串")
        
        # 执行 JavaScript 检查
        logger.info("\n正在执行 JavaScript 检查...")
        js_result = driver.execute_script("""
            const containers = document.querySelectorAll('[data-testid="msg-container"]');
            return {
                count: containers.length,
                firstElement: containers.length > 0 ? {
                    tagName: containers[0].tagName,
                    className: containers[0].className,
                    dataTestId: containers[0].getAttribute('data-testid'),
                    innerHTML: containers[0].innerHTML.substring(0, 200)
                } : null
            };
        """)
        
        logger.info(f"JavaScript 检查结果: {js_result}")
        
        logger.info("\n检查完成！")
        logger.info("请查看上述结果以确认 msg-container 元素是否存在。")
        
        # 保持浏览器打开以便用户检查
        logger.info("\n浏览器将保持打开状态，您可以手动检查 DOM 结构。")
        logger.info("按 Enter 关闭浏览器...")
        input()
        
    except Exception as e:
        logger.error(f"检查过程中出错: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logger.info("浏览器已关闭")

if __name__ == "__main__":
    check_msg_container()

