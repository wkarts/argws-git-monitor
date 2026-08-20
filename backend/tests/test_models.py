from sqlalchemy import create_engine, inspect

from app.models import Base


def test_metadata_creates_on_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    table_names = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "users" in table_names
    assert "repositories" in table_names
    assert "workflow_runs" in table_names
    assert "notifications" in table_names
