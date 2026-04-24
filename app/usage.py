"""API用量统计模块 - 真实数据记录"""

import time
import json
from datetime import datetime, date
from pathlib import Path
from threading import Lock

STATS_FILE = Path("token.json")


class UsageTracker:
    """API用量追踪器"""

    def __init__(self):
        self.lock = Lock()
        self.stats = self._load()

    def _load(self) -> dict:
        """加载统计数据"""
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return self._empty()

    def _empty(self) -> dict:
        return {
            'total_requests': 0,
            'total_prompt_tokens': 0,
            'total_completion_tokens': 0,
            'total_seconds': 0,
            'today': str(date.today()),
            'today_requests': 0,
            'today_prompt_tokens': 0,
            'today_completion_tokens': 0,
            'today_seconds': 0,
            'requests': []  # 最近100条请求记录
        }

    def _save(self):
        """保存统计数据"""
        try:
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存统计失败: {e}")

    def record(self, prompt_tokens: int, completion_tokens: int, seconds: float, model: str = ""):
        """记录一次请求"""
        with self.lock:
            # 检查是否新的一天
            if self.stats.get('today') != str(date.today()):
                self.stats['today'] = str(date.today())
                self.stats['today_requests'] = 0
                self.stats['today_prompt_tokens'] = 0
                self.stats['today_completion_tokens'] = 0
                self.stats['today_seconds'] = 0

            # 更新总计
            self.stats['total_requests'] += 1
            self.stats['total_prompt_tokens'] += prompt_tokens
            self.stats['total_completion_tokens'] += completion_tokens
            self.stats['total_seconds'] += seconds

            # 更新今日
            self.stats['today_requests'] += 1
            self.stats['today_prompt_tokens'] += prompt_tokens
            self.stats['today_completion_tokens'] += completion_tokens
            self.stats['today_seconds'] += seconds

            # 记录请求详情
            record = {
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'model': model,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens,
                'seconds': round(seconds, 2)
            }
            self.stats['requests'].insert(0, record)
            # 只保留最近100条
            self.stats['requests'] = self.stats['requests'][:100]

            self._save()

    def get_stats(self) -> dict:
        """获取统计数据"""
        with self.lock:
            today = self.stats
            total_reqs = today['total_requests']
            today_reqs = today['today_requests']

            return {
                'date': today.get('today', str(date.today())),
                'today': {
                    'requests': today_reqs,
                    'prompt_tokens': today['today_prompt_tokens'],
                    'completion_tokens': today['today_completion_tokens'],
                    'total_tokens': today['today_prompt_tokens'] + today['today_completion_tokens'],
                    'avg_seconds': round(today['today_seconds'] / today_reqs, 2) if today_reqs > 0 else 0,
                },
                'total': {
                    'requests': total_reqs,
                    'prompt_tokens': today['total_prompt_tokens'],
                    'completion_tokens': today['total_completion_tokens'],
                    'total_tokens': today['total_prompt_tokens'] + today['total_completion_tokens'],
                    'avg_seconds': round(today['total_seconds'] / total_reqs, 2) if total_reqs > 0 else 0,
                },
                'recent': today.get('requests', [])[:10]
            }

    def reset(self):
        """重置统计数据"""
        with self.lock:
            self.stats = self._empty()
            self._save()


# 全局实例
tracker = UsageTracker()
