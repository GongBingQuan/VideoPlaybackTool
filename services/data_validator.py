import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DataValidator:
    @classmethod
    def _safe_parse_datetime(cls, timestamp_str):
        try:
            return datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
        except (TypeError, ValueError) as e:
            logger.warning(f"时间格式错误：{timestamp_str}，错误：{str(e)}")
            return datetime.now()

    @staticmethod
    def validate_url(url: str) -> bool:
        """验证订阅URL格式"""
        pattern = r'^https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*)$'
        return re.match(pattern, url) is not None

    @staticmethod
    def sanitize_episode_data(episodes: list) -> list:
        """清洗剧集数据"""
        valid_episodes = []
        required_keys = {'title', 'url', 'duration'}
        
        for ep in episodes:
            if not isinstance(ep, dict):
                logger.warning(f"无效剧集格式，类型：{type(ep)}，内容：{str(ep)[:50]}")
                continue
            
            if required_keys - ep.keys():
                logger.warning(f"剧集{ep.get('title','未知')}缺少必要字段")
                continue
            
            valid_episodes.append({
                'title': ep['title'].strip(),
                'url': ep['url'].split('?')[0],  # 去除URL参数
                'duration': int(ep['duration']) if str(ep['duration']).isdigit() else 0
            })
        return valid_episodes

    @staticmethod
    def normalize_history_record(record: dict) -> dict:
        """标准化播放历史记录"""
        return {
            'title': record.get('title', '').strip(),
            'last_position': int(record.get('last_position', 0)),
            'timestamp': self._safe_parse_datetime(record.get('timestamp')),
            'total_duration': int(record.get('total_duration', 0))
        }