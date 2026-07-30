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
        os.chmod(HISTORY_DIR, 0o700)
        self._inserts_since_trim = 0
        self._conn = sqlite3.connect(HISTORY_DB, check_same_thread=False)
        try:
            os.chmod(HISTORY_DB, 0o600)
        except OSError:
            pass
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
        cur = self._conn.execute(
            "INSERT INTO commands (command, cwd, exit_code, timestamp) VALUES (?,?,?,?)",
            (command, cwd, exit_code, ts),
        )
        self._conn.commit()
        self._inserts_since_trim += 1
        if self._inserts_since_trim >= self.TRIM_CHECK_INTERVAL:
            self._inserts_since_trim = 0
            self._trim()
        return cur.lastrowid

    def set_exit_code(self, row_id, exit_code: int):
        # Called once the shell reports how a command finished (OSC 133 "D").
        # exit_code is unknown at add() time since that fires on command
        # start, before there's anything to report.
        if row_id is None:
            return
        self._conn.execute(
            "UPDATE commands SET exit_code = ? WHERE id = ?", (exit_code, row_id)
        )
        self._conn.commit()

    @staticmethod
    def _like_escape(term: str) -> str:
        # Fix #17: escape LIKE metacharacters so literal % and _ in search terms work correctly
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search(self, terms: str, limit: int = 50, cwd: str = ""):
        if not terms.strip():
            if cwd:
                return self._conn.execute(
                    "SELECT MAX(id) AS id, command, cwd, timestamp FROM commands "
                    "WHERE command NOT LIKE '/%' ESCAPE '\\' GROUP BY command "
                    "ORDER BY CASE WHEN cwd = ? THEN 0 ELSE 1 END, id DESC LIMIT ?",
                    (cwd, limit),
                ).fetchall()
            return self._conn.execute(
                "SELECT MAX(id) AS id, command, cwd, timestamp FROM commands "
                "WHERE command NOT LIKE '/%' ESCAPE '\\' GROUP BY command ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        parts = terms.strip().split()
        pos = []
        neg = []
        for p in parts:
            if p.startswith('-') and len(p) > 1:
                neg.append(p[1:])
            else:
                pos.append(p)
        where_clauses = []
        where_params = []
        if len(pos) == 1:
            escaped = self._like_escape(pos[0])
            where_clauses.append(
                "((command LIKE ? ESCAPE '\\') OR (REPLACE(command, ' ', '') LIKE ? ESCAPE '\\'))"
            )
            where_params.extend([f"%{escaped}%", f"%{escaped}%"])
        elif len(pos) > 1:
            where_clauses.append(
                "(" + " AND ".join(["command LIKE ? ESCAPE '\\'"] * len(pos)) + ")"
            )
            where_params.extend([f"%{self._like_escape(p)}%" for p in pos])
        for n in neg:
            where_clauses.append("command NOT LIKE ? ESCAPE '\\'")
            where_params.append(f"%{self._like_escape(n)}%")
        where_clauses.append("command NOT LIKE '/%' ESCAPE '\\'")
        where = " AND ".join(where_clauses)

        # A query made up entirely of exclusion terms (e.g. "-hello -world")
        # leaves pos empty - there's no positive term to rank prefix matches
        # against, so that ordering clause is simply skipped rather than
        # assumed to always exist.
        order_parts = []
        order_params = []
        if pos:
            first_term = pos[0]
            order_parts.append("CASE WHEN command LIKE ? ESCAPE '\\' THEN 0 ELSE 1 END")
            order_params.append(f"{self._like_escape(first_term)}%")

        if cwd:
            # Tie-break in favor of commands last run in the caller's current
            # directory - a substring match here still beats a same-cwd
            # match elsewhere, but among similar matches "you ran this here
            # before" is a stronger signal than raw recency or length.
            order_parts.append("CASE WHEN cwd = ? THEN 0 ELSE 1 END")
            order_params.append(cwd)

        if len(pos) > 1:
            instr_sum = " + ".join([f"INSTR(LOWER(command), ?)" for _ in pos])
            order_parts.append(f"({instr_sum})")
            order_params.extend(t.lower() for t in pos)

        order_parts += [
            "LENGTH(command)",
            "id DESC",
        ]
        order_clause = ", ".join(order_parts)

        params = where_params + order_params + [limit]
        # GROUP BY command dedupes repeated commands; SQLite's bare-column rule
        # with a single MAX() aggregate means cwd/timestamp come from the most
        # recent (max id) row in each group.
        return self._conn.execute(
            f"SELECT MAX(id) AS id, command, cwd, timestamp FROM commands "
            f"WHERE {where} GROUP BY command ORDER BY {order_clause} LIMIT ?",
            params,
        ).fetchall()

    def sql_search(self, sql: str):
        sql_stripped = sql.strip()
        sql_upper = sql_stripped.upper()
        if not any(sql_upper.startswith(kw) for kw in ('SELECT', 'EXPLAIN')):
            raise ValueError("Only SELECT and EXPLAIN queries are supported")

        ro_conn = sqlite3.connect(f"file:{HISTORY_DB}?mode=ro", uri=True)
        try:
            ro_conn.set_progress_handler(lambda: 2_000_000, 10000)
            cur = ro_conn.execute(sql_stripped)
            rows = cur.fetchall()
            if len(rows) > 1000:
                rows = rows[:1000]
            return rows
        finally:
            ro_conn.close()

    def interactive_search(self, query: str, limit: int = 100):
        if not query.strip():
            return self._conn.execute(
                "SELECT DISTINCT command FROM commands ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        parts = query.strip().split()
        where = " AND ".join(["command LIKE ? ESCAPE '\\'"] * len(parts))
        where_params = [f"%{self._like_escape(p)}%" for p in parts]

        first_term = parts[0]
        order_parts = [
            f"CASE WHEN command LIKE ? ESCAPE '\\' THEN 0 ELSE 1 END",
        ]
        order_params = [f"{self._like_escape(first_term)}%"]

        if len(parts) > 1:
            instr_sum = " + ".join([f"INSTR(LOWER(command), ?)" for _ in parts])
            order_parts.append(f"({instr_sum})")
            order_params.extend(t.lower() for t in parts)

        order_parts += [
            "LENGTH(command)",
            "max_id DESC",
        ]
        order_clause = ", ".join(order_parts)

        # Placeholder order in the SQL is: where_params..., inner LIMIT,
        # order_params..., outer LIMIT — params must follow that exact
        # sequence or SQLite binds values to the wrong slot (e.g. an int
        # limit landing where a LIKE pattern is expected, or vice versa),
        # which raises "datatype mismatch" once it hits the outer LIMIT.
        params = where_params + [limit] + order_params + [limit]
        # Fix #16: outer ORDER BY — SQLite does not guarantee subquery ordering survives.
        return self._conn.execute(
            "SELECT command FROM ("
            f"SELECT command, MAX(id) as max_id FROM commands WHERE {where} "
            "GROUP BY command LIMIT ?) "
            f"ORDER BY {order_clause} LIMIT ?",
            params,
        ).fetchall()

    def _trim(self, max_rows: int = 1_000_000):
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

    def optimize(self):
        """Dedup, reclaim space and refresh query-planner stats.

        Keeps only the most recent row for each (command, cwd) pair —
        same idea as bash's HISTCONTROL=erasedups — then checkpoints the
        WAL, VACUUMs and ANALYZEs. Returns before/after stats for display.
        """
        rows_before = self._conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
        size_before = os.path.getsize(HISTORY_DB) if os.path.exists(HISTORY_DB) else 0

        self._conn.execute(
            "DELETE FROM commands WHERE id NOT IN ("
            "  SELECT MAX(id) FROM commands GROUP BY command, cwd"
            ")"
        )
        self._conn.commit()
        rows_after = self._conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0]

        # VACUUM/checkpoint need no transaction open; the commit() above covers that.
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.execute("ANALYZE")
        self._conn.execute("VACUUM")
        self._conn.commit()

        size_after = os.path.getsize(HISTORY_DB) if os.path.exists(HISTORY_DB) else 0
        self._inserts_since_trim = 0

        return {
            "rows_before": rows_before,
            "rows_after": rows_after,
            "duplicates_removed": rows_before - rows_after,
            "size_before": size_before,
            "size_after": size_after,
        }
