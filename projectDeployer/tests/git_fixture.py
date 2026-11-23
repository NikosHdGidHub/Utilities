import os
from unittest.mock import patch


def test_git_identity(case):
    # Subprocess-only identity. Never write the developer's Git configuration.
    env = patch.dict(os.environ, GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="user.name",
                     GIT_CONFIG_VALUE_0="Deployment Test", GIT_CONFIG_KEY_1="user.email",
                     GIT_CONFIG_VALUE_1="test@example.invalid")
    env.start()
    case.addCleanup(env.stop)
