from pathlib import Path

from arbitrade.persistence import Persistence, REQUIRED_TABLES


def test_creates_required_tables(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    persistence = Persistence(str(db))
    persistence.initialize()
    tables = persistence.list_tables()
    for table in REQUIRED_TABLES:
        assert table in tables
