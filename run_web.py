import sys
import os

# Ensure the project root is on sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import uvicorn
from web.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8081)

