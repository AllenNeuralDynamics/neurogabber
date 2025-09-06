import uuid
from typing import Dict, List, Optional

import polars as pl

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB cap


class UploadedFileRecord:
    def __init__(self, file_id: str, name: str, size: int, df: pl.DataFrame):
        self.file_id = file_id
        self.name = name
        self.size = size
        self.df = df

    def to_meta(self) -> dict:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "size": self.size,
            "n_rows": self.df.height,
            "n_cols": self.df.width,
            "columns": self.df.columns,
        }


class SummaryRecord:
    def __init__(
        self,
        summary_id: str,
        source_file_id: str,
        kind: str,
        df: pl.DataFrame,
        note: Optional[str] = None,
    ):
        self.summary_id = summary_id
        self.source_file_id = source_file_id
        self.kind = kind
        self.df = df
        self.note = note

    def to_meta(self) -> dict:
        return {
            "summary_id": self.summary_id,
            "source_file_id": self.source_file_id,
            "kind": self.kind,
            "n_rows": self.df.height,
            "n_cols": self.df.width,
            "columns": self.df.columns,
            "note": self.note,
        }


class DataMemory:
    """Ephemeral session-scoped data store for uploaded CSVs & derived summaries."""

    def __init__(self):
        self.files: Dict[str, UploadedFileRecord] = {}
        self.summaries: Dict[str, SummaryRecord] = {}

    def add_file(self, name: str, raw: bytes) -> dict:
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError(f"File too large ({len(raw)} bytes > {MAX_FILE_BYTES})")
        try:
            df = pl.read_csv(raw)
        except Exception as e:  # pragma: no cover - defensive
            raise ValueError(f"Failed to parse CSV: {e}") from e
        fid = uuid.uuid4().hex[:8]
        rec = UploadedFileRecord(fid, name, len(raw), df)
        self.files[fid] = rec
        return rec.to_meta()

    def list_files(self) -> List[dict]:
        return [rec.to_meta() for rec in self.files.values()]

    def get_df(self, file_id: str) -> pl.DataFrame:
        if file_id not in self.files:
            raise KeyError(f"Unknown file_id: {file_id}")
        return self.files[file_id].df

    def add_summary(
        self, file_id: str, kind: str, df: pl.DataFrame, note: str | None = None
    ) -> dict:
        sid = uuid.uuid4().hex[:8]
        rec = SummaryRecord(sid, file_id, kind, df, note)
        self.summaries[sid] = rec
        return rec.to_meta()

    def list_summaries(self) -> List[dict]:
        return [rec.to_meta() for rec in self.summaries.values()]

    def get_summary_df(self, summary_id: str) -> pl.DataFrame:
        if summary_id not in self.summaries:
            raise KeyError(f"Unknown summary_id: {summary_id}")
        return self.summaries[summary_id].df


class InteractionMemory:
    """Simple rolling memory for recent interactions."""

    def __init__(self, max_items: int = 30, max_chars: int = 6000):
        self.events: List[str] = []
        self.max_items = max_items
        self.max_chars = max_chars

    def remember(self, interaction: str):
        self.events.append(interaction.strip())
        if len(self.events) > self.max_items:
            self.events = self.events[-self.max_items :]
        joined = " | ".join(self.events)
        if len(joined) > self.max_chars:
            while self.events and len(" | ".join(self.events)) > self.max_chars:
                self.events.pop(0)

    def recall(self) -> str:
        return " | ".join(self.events)
