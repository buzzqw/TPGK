import os
import sqlite3
import datetime

HISTORY_DIR = os.path.join(os.path.expanduser("~"), ".config", "tpgk")
HISTORY_DB = os.path.join(HISTORY_DIR, "history.db")


class HistoryManager:
    TRIM_CHECK_INTERVAL = 50
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        os.makedirs(HISTORY_DIR, exist_ok=True)
        self._inserts_since_trim = 0
        self._conn = sqlite3.connect(HISTORY_DB, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS commands ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  command TEXT NOT NULL,"
            "  cwd TEXT,"
            "  exit_code INTEGER,"
            "  timestamp TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_commands_ts ON commands(timestamp)"
        )
        self._conn.commit()
        self._initialized = True

    def add(self, command: str, cwd: str = "", exit_code: int = -1):
        ts = datetime.datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO commands (command, cwd, exit_code, timestamp) VALUES (?,?,?,?)",
            (command, cwd, exit_code, ts),
        )
        self._conn.commit()
        self._inserts_since_trim += 1
        if self._inserts_since_trim >= self.TRIM_CHECK_INTERVAL:
            self._inserts_since_trim = 0
            self._trim()

    @staticmethod
    def _like_escape(term: str) -> str:
        # Fix #17: escape LIKE metacharacters so literal % and _ in search terms work correctly
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search(self, terms: str, limit: int = 50):
        if not terms.strip():
            return self._conn.execute(
                "SELECT id, command, cwd, timestamp FROM commands WHERE command NOT LIKE '/%' ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        parts = terms.strip().split()
        base = " AND ".join(["command LIKE ? ESCAPE '\\'"] * len(parts))
        params = [f"%{self._like_escape(p)}%" for p in parts]
        if len(parts) == 1:
            where = f"(({base}) OR (REPLACE(command, ' ', '') LIKE ? ESCAPE '\\'))"
            params.append(params[0])
        else:
            where = f"({base})"
        where += " AND command NOT LIKE '/%' ESCAPE '\\'"
        params.append(limit)
        return self._conn.execute(
            f"SELECT id, command, cwd, timestamp FROM commands WHERE {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()

    def interactive_search(self, query: str, limit: int = 100):
        if not query.strip():
            return self._conn.execute(
                "SELECT DISTINCT command FROM commands ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        parts = query.strip().split()
        where = " AND ".join(["command LIKE ? ESCAPE '\\'"] * len(parts))
        params = [f"%{self._like_escape(p)}%" for p in parts] + [limit]
        # Fix #16: outer ORDER BY — SQLite does not guarantee subquery ordering survives.
        # GROUP BY already deduplicates, so DISTINCT is redundant; outer SELECT can use max_id.
        return self._conn.execute(
            "SELECT command FROM ("
            f"SELECT command, MAX(id) as max_id FROM commands WHERE {where} "
            "GROUP BY command LIMIT ?) "
            "ORDER BY max_id DESC",
            params,
        ).fetchall()

    def _trim(self, max_rows: int = 10000):
        count = self._conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
        if count > max_rows:
            self._conn.execute(
                "DELETE FROM commands WHERE id NOT IN (SELECT id FROM commands ORDER BY id DESC LIMIT ?)",
                (max_rows,),
            )
            self._conn.commit()

    def search_latest(self, prefix: str = "", limit: int = 20):
        if prefix:
            return self._conn.execute(
                "SELECT command FROM commands WHERE command LIKE ? GROUP BY command ORDER BY MAX(id) DESC LIMIT ?",
                (f"{prefix}%", limit),
            ).fetchall()
        return self._conn.execute(
            "SELECT command FROM commands GROUP BY command ORDER BY MAX(id) DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def get_all(self, limit: int = 500):
        return self._conn.execute(
            "SELECT command FROM commands ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def clear(self):
        self._conn.execute("DELETE FROM commands")
        self._conn.commit()
