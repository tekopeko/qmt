"""Suite-wide environment, set before any test module imports the app."""
import os

import pytest

# The suite opens accounts through /signup, the way invited members did before
# registration closed on 28.9.2026. Production runs with SIGNUP_MODE unset,
# which means closed; test_signup_is_closed_by_default_and_members_still_log_in
# covers that state.
os.environ.setdefault("SIGNUP_MODE", "invite")


@pytest.fixture(scope="session", autouse=True)
def _cheap_password_hashes():
    """The suite's passwords are hashed at bcrypt's lowest cost (27.11.2026;
    the owner agreed: measured that day, a test member cost 0.24 s to make
    and 0.24 s to log in, minutes of every run). The live site's cost is the
    constant in auth.py, which no setting reaches: this fixture changes the
    module's value in the suite's own process alone (the browser tests'
    server is a thread of it). A check costs what the hash says, so logging
    in a member made here is cheap too.
    test_a_password_is_hashed_at_full_cost_outside_the_suite holds the
    constant."""
    from qmt import auth

    auth.BCRYPT_ROUNDS = 4
    yield


@pytest.fixture(scope="session", autouse=True)
def _no_table_the_models_dropped():
    """The test database outlives a checkout, and a table a migration
    dropped stays in it with its foreign keys to tables the models keep,
    which stops every module's Base.metadata.drop_all. program_items went
    on 30.10.2026 (migration 7c3bf996c983, the programmes' days), and
    gym_training_parts on 27.11.2026 (migration 9b4e2d7f1c58, a gym
    training's blocks; its key points at gym_trainings): dropped once,
    before the first test, from the database the suite uses (every module
    points qmt at qmt_test before it imports it)."""
    from sqlalchemy import text

    from qmt import db

    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS program_items CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS gym_training_parts CASCADE"))
    yield
