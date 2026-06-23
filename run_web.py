import sys
import os

# Ensure the project root is on sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import uvicorn
from web.server import app
from oracle.utils.config import OracleConfig

if __name__ == "__main__":
    cfg = OracleConfig()
    host = os.environ.get("ORACLE_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ORACLE_WEB_PORT", "8081"))
    uvicorn.run(app, host=host, port=port)

