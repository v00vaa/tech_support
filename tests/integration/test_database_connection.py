from flask import Flask
from sqlalchemy import text


def test_database_engine_executes_query(app: Flask) -> None:
    database = app.extensions["database"]

    with app.app_context(), database.engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1