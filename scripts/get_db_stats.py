import json
import os
import sys

sys.path.insert(0, os.getcwd())

from database.utils.migrated_database_utils import (
    create_database_service,
    get_database_stats,
)

s = create_database_service()
try:
    stats = get_database_stats(s)
    print(json.dumps(stats, indent=2))
    with open('db_stats.json','w') as fh:
        json.dump(stats, fh, indent=2)
finally:
    s.close()
