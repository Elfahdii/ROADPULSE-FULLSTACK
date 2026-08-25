from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import DATA_DIR

DB_PATH = Path(DATA_DIR) / 'roadpulse.db'


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS surveys (
                survey_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL,
                road_name TEXT,
                formatted_address TEXT,
                filename TEXT,
                health_score REAL,
                status TEXT,
                total_defects INTEGER,
                roughness_index REAL,
                roughness_label TEXT,
                location_source TEXT,
                result_json TEXT NOT NULL
            )
            '''
        )
        conn.commit()


def save_survey(survey_id: str, result: dict[str, Any]) -> None:
    init_db()
    summary = result.get('summary') or {}
    location = result.get('location') or {}
    video = result.get('video') or {}
    processed_at = video.get('processed_at') or ''
    payload = json.dumps(result, ensure_ascii=False)

    with _connect() as conn:
        conn.execute(
            '''
            INSERT INTO surveys (
                survey_id, processed_at, road_name, formatted_address, filename,
                health_score, status, total_defects, roughness_index,
                roughness_label, location_source, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(survey_id) DO UPDATE SET
                processed_at=excluded.processed_at,
                road_name=excluded.road_name,
                formatted_address=excluded.formatted_address,
                filename=excluded.filename,
                health_score=excluded.health_score,
                status=excluded.status,
                total_defects=excluded.total_defects,
                roughness_index=excluded.roughness_index,
                roughness_label=excluded.roughness_label,
                location_source=excluded.location_source,
                result_json=excluded.result_json
            ''',
            (
                survey_id,
                processed_at,
                location.get('road_name'),
                location.get('formatted_address'),
                video.get('filename'),
                summary.get('health_score'),
                summary.get('status'),
                summary.get('total_defects'),
                summary.get('roughness_index'),
                summary.get('roughness_label'),
                location.get('source'),
                payload,
            ),
        )
        conn.commit()


def list_surveys(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        rows = conn.execute(
            '''
            SELECT survey_id, processed_at, road_name, formatted_address, filename,
                   health_score, status, total_defects, roughness_index,
                   roughness_label, location_source
            FROM surveys
            ORDER BY processed_at DESC, rowid DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_survey(survey_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            'SELECT survey_id, result_json FROM surveys WHERE survey_id = ?',
            (survey_id,),
        ).fetchone()
    if not row:
        return None
    try:
        result = json.loads(row['result_json'])
    except Exception:
        return None
    return {'survey_id': row['survey_id'], 'result': result}
