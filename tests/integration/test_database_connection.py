"""Integration boundary test for the configured SQLAlchemy engine."""

from flask import Flask
from sqlalchemy import text


def test_database_engine_executes_query(app: Flask) -> None:
    database = app.extensions["database"]

    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
