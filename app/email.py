"""邮件通知模块"""

import smtplib
import threading
import time
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional
from .config import config_manager


def send_email(subject: str, body: str) -> bool:
    """发送邮件"""
    cfg = config_manager.get_config()
    
    if not cfg.get('email_enabled'):
        return False
    
    try:
        host = cfg.get('email_host', '')
        port = cfg.get('email_port', 587)
        user = cfg.get('email_user', '')
        password = cfg.get('email_password', '')
        email_from = cfg.get('email_from', user)
        email_to = cfg.get('email_to', '')
        
        if not all([host, user, password, email_to]):
            return False
        
        msg = MIMEMultipart()
        msg['From'] = email_from
        msg['To'] = email_to
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        # 端口 465 使用 SSL，其他用 STARTTLS
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        
        server.login(user, password)
        server.sendmail(email_from, email_to, msg.as_string())
        server.quit()
        
        return True
    except Exception as e:
        print(f"发送邮件失败: {e}")
        return False


def send_account_expired_email(user_id: str, error: str) -> bool:
    """发送账号过期通知"""
    subject = f"[WebMimoToOpenAIAPI] 账号过期提醒 - {user_id}"
    body = f"""
    <html>
    <body>
        <h2>账号过期提醒</h2>
        <p>检测到以下 Mimo 账号已过期或失效：</p>
        <ul>
            <li><b>用户ID:</b> {user_id}</li>
            <li><b>错误信息:</b> {error}</li>
            <li><b>检测时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        </ul>
        <p>请及时更新账号凭证。</p>
    </body>
    </html>
    """
    return send_email(subject, body)


def send_test_email() -> bool:
    """发送测试邮件"""
    subject = "[WebMimoToOpenAIAPI] 测试邮件"
    body = f"""
    <html>
    <body>
        <h2>测试邮件</h2>
        <p>这是一封测试邮件，邮件配置正常。</p>
        <p>发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """
    return send_email(subject, body)


class AccountChecker:
    """账号检测定时任务"""
    
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
    
    def start(self):
        """启动检测"""
        if self.running:
            return
        cfg = config_manager.get_config()
        if not cfg.get('email_check_enabled'):
            return
        self.running = True
        self.thread = threading.Thread(target=self._check_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """停止检测"""
        self.running = False
    
    def restart(self):
        """重启检测"""
        self.stop()
        time.sleep(1)
        self.start()
    
    def _check_loop(self):
        """检测循环"""
        while self.running:
            try:
                self._check_accounts()
            except Exception as e:
                print(f"账号检测错误: {e}")
            
            cfg = config_manager.get_config()
            interval = cfg.get('email_check_interval', 3600)
            time.sleep(interval)
    
    def _check_accounts(self):
        """检测所有账号"""
        import asyncio
        from .mimo_client import MimoClient
        
        accounts = config_manager.get_accounts()
        if not accounts:
            return
        
        expired = []
        valid = []
        
        # 在新线程中运行异步检测
        def run_async_check():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for acc in accounts:
                    mimo_acc = None
                    for ma in config_manager.config.mimo_accounts:
                        if ma.user_id == acc.get('user_id'):
                            mimo_acc = ma
                            break
                    
                    if mimo_acc:
                        client = MimoClient(mimo_acc)
                        success, msg = loop.run_until_complete(client.test_connection())
                        
                        if success:
                            valid.append(acc.get('user_id', 'unknown'))
                        else:
                            expired.append((acc.get('user_id', 'unknown'), msg))
            finally:
                loop.close()
        
        # 在线程中运行
        thread = threading.Thread(target=run_async_check, daemon=True)
        thread.start()
        thread.join(timeout=60)
        
        # 更新检测结果
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if expired:
            result = f"过期: {', '.join([e[0] for e in expired])}"
        else:
            result = "全部正常" if valid else "无账号"
        
        # 更新检测结果
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if expired:
            result = f"过期: {', '.join([e[0] for e in expired])}"
        else:
            result = "全部正常" if valid else "无账号"
        
        # 更新配置
        config_manager.config.check_last_time = now_str
        config_manager.config.check_last_result = result
        config_manager.save()
        
        # 发送过期邮件
        for user_id, error in expired:
            send_account_expired_email(user_id, error)


# 全局检测器
email_checker = AccountChecker()