"""配置管理模块"""

import json
import threading
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict


@dataclass
class MimoAccount:
    """Mimo账号配置"""
    service_token: str
    user_id: str
    xiaomichatbot_ph: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Config:
    """应用配置"""
    api_keys: str = "sk-default"
    mimo_accounts: List[MimoAccount] = None
    system_prompt: str = ""
    default_model: str = "mimo-v2.5-pro"
    account_mode: str = "random"
    email_enabled: bool = False
    email_host: str = ""
    email_port: int = 587
    email_user: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: str = ""
    email_check_enabled: bool = False
    email_check_interval: int = 3600
    check_last_time: str = ""
    check_last_result: str = ""

    def __post_init__(self):
        if self.mimo_accounts is None:
            self.mimo_accounts = []

    def to_dict(self):
        return {
            "api_keys": self.api_keys,
            "mimo_accounts": [acc.to_dict() for acc in self.mimo_accounts],
            "system_prompt": self.system_prompt,
            "default_model": self.default_model,
            "account_mode": self.account_mode,
            "email_enabled": self.email_enabled,
            "email_host": self.email_host,
            "email_port": self.email_port,
            "email_user": self.email_user,
            "email_password": self.email_password,
            "email_from": self.email_from,
            "email_to": self.email_to,
            "email_check_enabled": self.email_check_enabled,
            "email_check_interval": self.email_check_interval,
            "check_last_time": self.check_last_time,
            "check_last_result": self.check_last_result
        }


class ConfigManager:
    """配置管理器 - 线程安全"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self.config = Config()
        self.lock = threading.RLock()
        self.account_idx = 0
        self.load()

    def load(self):
        """加载配置"""
        if not self.config_file.exists():
            self.save()
            return

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                accounts = [
                    MimoAccount(**acc) for acc in data.get('mimo_accounts', [])
                ]
                self.config = Config(
                    api_keys=data.get('api_keys', 'sk-default'),
                    mimo_accounts=accounts,
                    system_prompt=data.get('system_prompt', ''),
                    default_model=data.get('default_model', 'mimo-v2.5-pro'),
                    account_mode=data.get('account_mode', 'random'),
                    email_enabled=data.get('email_enabled', False),
                    email_host=data.get('email_host', ''),
                    email_port=data.get('email_port', 587),
                    email_user=data.get('email_user', ''),
                    email_password=data.get('email_password', ''),
                    email_from=data.get('email_from', ''),
                    email_to=data.get('email_to', ''),
                    email_check_enabled=data.get('email_check_enabled', False),
                    email_check_interval=data.get('email_check_interval', 3600),
                    check_last_time=data.get('check_last_time', ''),
                    check_last_result=data.get('check_last_result', '')
                )
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.config = Config()
            self.save()

    def save(self):
        """保存配置"""
        with self.lock:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置失败: {e}")

    def validate_api_key(self, key: str) -> bool:
        """验证API Key"""
        with self.lock:
            keys = [k.strip() for k in self.config.api_keys.split(',')]
            return key in keys

    def get_next_account(self) -> Optional[MimoAccount]:
        """获取下一个账号（支持轮询和随机）"""
        with self.lock:
            if not self.config.mimo_accounts:
                return None
            
            mode = getattr(self.config, 'account_mode', 'random')
            
            if mode == 'random':
                import random
                return random.choice(self.config.mimo_accounts)
            else:
                account = self.config.mimo_accounts[self.account_idx % len(self.config.mimo_accounts)]
                self.account_idx += 1
                return account

    def add_account(self, account: MimoAccount, nickname: str = ""):
        """添加账号"""
        with self.lock:
            if not self.config.mimo_accounts:
                self.config.mimo_accounts = []
            self.config.mimo_accounts.append(account)
            self.save()

    def get_accounts(self) -> list:
        """获取账号列表"""
        with self.lock:
            return [acc.to_dict() for acc in self.config.mimo_accounts]

    def update_config(self, new_config: dict):
        """更新配置"""
        with self.lock:
            accounts = [
                MimoAccount(**acc) for acc in new_config.get('mimo_accounts', [])
            ]
            # 保留敏感字段旧值（在用户没有填写的情况下）
            old = self.config
            self.config = Config(
                api_keys=new_config.get('api_keys', old.api_keys),
                mimo_accounts=accounts,
                system_prompt=new_config.get('system_prompt', old.system_prompt),
                default_model=new_config.get('default_model', old.default_model),
                account_mode=new_config.get('account_mode', old.account_mode),
                email_enabled=new_config.get('email_enabled', old.email_enabled),
                email_host=new_config.get('email_host', old.email_host),
                email_port=new_config.get('email_port', old.email_port),
                email_user=new_config.get('email_user', old.email_user),
                email_password=new_config.get('email_password', old.email_password),
                email_from=new_config.get('email_from', old.email_from),
                email_to=new_config.get('email_to', old.email_to),
                email_check_enabled=new_config.get('email_check_enabled', old.email_check_enabled),
                email_check_interval=new_config.get('email_check_interval', old.email_check_interval),
                check_last_time=old.check_last_time,
                check_last_result=old.check_last_result
            )
            self.save()

    def get_config(self) -> dict:
        """获取配置"""
        with self.lock:
            return self.config.to_dict()


# 全局配置管理器实例
config_manager = ConfigManager()
