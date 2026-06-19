#!/usr/bin/env python3
"""Provide Git HTTPS credentials from the child process environment.

Git invokes this executable once for the username prompt and once for the
password prompt. Keeping the token in the environment prevents it from
appearing in Git command-line arguments or repository configuration.
"""

import os
import sys

prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ""
variable = "QA_GIT_USERNAME" if "username" in prompt else "QA_GIT_TOKEN"
sys.stdout.write(os.environ.get(variable, ""))
