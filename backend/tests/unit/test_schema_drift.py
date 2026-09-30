from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_migration_schema_matches_the_design() -> None:
    design = (ROOT / "docs" / "design" / "schema.sql").read_text(encoding="utf-8")
    shipped = (ROOT / "backend" / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    assert shipped == design, "copy docs/design/schema.sql to backend/app/db/schema.sql and add a migration"
