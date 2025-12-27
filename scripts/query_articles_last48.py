import os
import sys

sys.path.insert(0, os.getcwd())
from database.utils.migrated_database_utils import create_database_service


def main():
    s = create_database_service()
    try:
        cur = s.mb_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM articles WHERE collection_timestamp >= NOW() - INTERVAL 48 HOUR"
        )
        print(cur.fetchone())
        cur.close()
    finally:
        s.close()


if __name__ == "__main__":
    main()
