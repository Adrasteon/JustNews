import os
import sys

sys.path.insert(0, os.getcwd())

import chromadb


def main():
    host = os.environ.get('CHROMADB_HOST', 'localhost')
    port = int(os.environ.get('CHROMADB_PORT', '3307'))
    client = chromadb.HttpClient(host=host, port=port)
    col = client.get_collection('articles')
    res = col.get(include=['ids'])
    print('chroma_docs:', len(res.get('ids', [])))

if __name__ == '__main__':
    main()
