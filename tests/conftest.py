"""Suite-wide environment, set before any test module imports the app."""
import os

import pytest

# The suite opens accounts through /signup, the way invited members did before
# registration closed on 28.9.2026. Production runs with SIGNUP_MODE unset,
# which means closed; test_signup_is_closed_by_default_and_members_still_log_in
# covers that state.
os.environ.setdefault("SIGNUP_MODE", "invite")


@pytest.fixture(scope="session", autouse=True)
def _no_table_the_models_dropped():
    """The test database outlives a checkout, and a table a migration
    dropped stays in it with its foreign keys to tables the models keep,
    which stops every module's Base.metadata.drop_all. program_items went
    on 30.10.2026 (migration 7c3bf996c983, the programmes' days): dropped
    once, before the first test, from the database the suite uses (every
    module points qmt at qmt_test before it imports it)."""
    from sqlalchemy import text

    from qmt import db

    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS program_items CASCADE"))
    yield
