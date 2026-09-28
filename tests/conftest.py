"""Suite-wide environment, set before any test module imports the app."""
import os

# The suite opens accounts through /signup, the way invited members did before
# registration closed on 28.9.2026. Production runs with SIGNUP_MODE unset,
# which means closed; test_signup_is_closed_by_default_and_members_still_log_in
# covers that state.
os.environ.setdefault("SIGNUP_MODE", "invite")
