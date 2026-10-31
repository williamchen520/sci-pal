import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.paths import DB_PATH
from services.tenancy import bootstrap_default_workspace

print(bootstrap_default_workspace(db_path=str(DB_PATH)))
