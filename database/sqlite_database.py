import sqlite3
import threading
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple
from contextlib import contextmanager

class SQLiteDatabase:
    def __init__(self, db_path: str):
        """
        专注SQLite的数据库封装
        :param db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._connection_pool = []  # 简单连接池
        self._max_connections = 5
        self._init_db()

    def _init_db(self):
        """初始化数据库和表结构"""
        with self._connection_context() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS play_history (
                    series_name TEXT PRIMARY KEY,
                    episode TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 添加性能索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON play_history(timestamp)")
            conn.commit()

    @contextmanager
    def _connection_context(self):
        """连接上下文管理（带简单连接池）"""
        conn = None
        try:
            with self._lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                else:
                    conn = sqlite3.connect(self.db_path, isolation_level=None)
                    conn.execute("PRAGMA journal_mode=WAL")  # 启用WAL模式
                    conn.execute("PRAGMA synchronous=NORMAL")  # 平衡性能和数据安全
                    conn.row_factory = sqlite3.Row

            yield conn
        finally:
            if conn:
                with self._lock:
                    if len(self._connection_pool) < self._max_connections:
                        self._connection_pool.append(conn)
                    else:
                        conn.close()

    def execute(self, sql: str, params: Tuple = (), *, commit: bool = False) -> List[Dict[str, Any]]:
        """
        执行SQL查询
        :param sql: SQL语句
        :param params: 参数元组
        :param commit: 是否提交事务
        :return: 结果字典列表
        """
        with self._connection_context() as conn:
            conn.execute("BEGIN")
            try:
                cursor = conn.execute(sql, params)
                if commit:
                    conn.execute("COMMIT")
                return [dict(row) for row in cursor.fetchall()]
            except:
                conn.execute("ROLLBACK")
                raise

    def executemany(self, sql: str, params_list: List[Tuple], *, commit: bool = False) -> None:
        """批量执行SQL"""
        with self._connection_context() as conn:
            conn.execute("BEGIN")
            try:
                conn.executemany(sql, params_list)
                if commit:
                    conn.execute("COMMIT")
            except:
                conn.execute("ROLLBACK")
                raise

    def get_one(self, sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        """获取单条记录"""
        results = self.execute(sql, params)
        return results[0] if results else None
