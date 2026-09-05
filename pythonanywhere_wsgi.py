# PythonAnywhere WSGI configuration.
#
# On PythonAnywhere, open the "Web" tab, click the WSGI configuration file link,
# DELETE everything in it, and paste this file's contents. Then change:
#   1. USERNAME below to your PythonAnywhere username.
#   2. The teacher password.
# Finally click the green "Reload" button on the Web tab.

import os
import sys

# ---- 1. Point Python at the project folder --------------------------------
# If you uploaded/cloned the project to /home/USERNAME/fernando, this is right.
USERNAME = "USERNAME"  # <-- change to your PythonAnywhere username
project_home = f"/home/{USERNAME}/fernando"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# ---- 2. Set the teacher console password ----------------------------------
os.environ["TEACHER_PASSWORD"] = "change-this-password"  # <-- pick a password

# ---- 3. Expose the Flask app to the WSGI server ---------------------------
from app import app as application  # noqa: E402
