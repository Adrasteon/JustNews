#!/usr/bin/env python3
"""
Print the database config to help debugging Chroma & MariaDB settings
"""
import os
import json
from database.utils.migrated_database_utils import get_db_config


def main():
    cfg = get_db_config()
    cfg['_env'] = {
        'CHROMADB_REQUIRE_CANONICAL': os.environ.get('CHROMADB_REQUIRE_CANONICAL', None),
        'CHROMADB_CANONICAL_HOST': os.environ.get('CHROMADB_CANONICAL_HOST', None),
        'CHROMADB_CANONICAL_PORT': os.environ.get('CHROMADB_CANONICAL_PORT', None),
    }
    print(json.dumps(cfg, indent=2))


if __name__ == '__main__':
    main()
