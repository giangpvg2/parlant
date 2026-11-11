"""Small, locked JSON tables for the standalone recruitment demo (Linux/local).

Runtime writes are read-modify-write operations under one file lock. Each table
is replaced atomically; an interrupted write never silently resets a table.
"""

import copy
import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

CONFIG_TABLES = {"agents", "candidate_schema", "companies", "jobs", "knowledge"}
RUNTIME_TABLES = {
    "candidate_profiles",
    "candidate_notes",
    "candidate_evaluations",
    "crm_contacts",
    "crm_sync_operations",
}


class DataSourceError(RuntimeError):
    """A configured JSON source could not be read; not an absent business record."""


class JsonStore:
    def __init__(self, config_dir: Path, runtime_dir: Path):
        self.config_dir = Path(config_dir)
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.locked():
            for table in sorted(RUNTIME_TABLES):
                if not self.path(table).exists():
                    self._write(table, {})

    def path(self, table: str) -> Path:
        if table in CONFIG_TABLES:
            return self.config_dir / f"{table}.json"
        if table in RUNTIME_TABLES:
            return self.runtime_dir / f"{table}.json"
        raise ValueError(f"Unknown demo table: {table}")

    @contextmanager
    def locked(self):
        with self._lock, (self.runtime_dir / ".store.lock").open("a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self, table):
        document = json.loads(self.path(table).read_text(encoding="utf-8"))
        if document.get("schema_version") != 1 or not isinstance(document.get("items"), dict):
            raise ValueError(f"Invalid schema in {self.path(table)}")
        return document["items"]

    def read(self, table):
        # Invalid table names are programming errors, not source outages.
        self.path(table)
        # Keep update() strict: never replace a corrupt table with an empty one.
        try:
            with self.locked():
                return self._read(table)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise DataSourceError("JSON source unavailable") from exc

    def _write(self, table, items):
        if table not in RUNTIME_TABLES:
            raise ValueError("Demo tools cannot modify configuration tables")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.runtime_dir, suffix=".tmp", delete=False
            ) as handle:
                temporary = handle.name
                json.dump(
                    {"schema_version": 1, "items": items},
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path(table))
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def update(self, table, mutate):
        if table not in RUNTIME_TABLES:
            raise ValueError("Configuration is read-only")
        with self.locked():
            items = self._read(table)
            result = mutate(items)
            self._write(table, items)
            return copy.deepcopy(result)
