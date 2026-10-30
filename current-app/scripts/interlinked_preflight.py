"""Read-only validation of the registered local library; no import or activation."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def validate_registered_library(data, *, verify_all=False):
    from stats_app.analysis_repository import list_registered_analyses,load_registered_analysis
    from stats_app.youtube_repository import list_registered_youtube,load_registered_youtube
    from stats_app.shopify_repository import list_registered_shopify,load_registered_shopify
    from stats_app.linktree_repository import list_registered_linktree,load_registered_linktree
    from stats_app.tiktok_repository import list_registered_tiktok,load_registered_tiktok
    root=Path(data).resolve()
    assert root.is_dir() and not str(root).startswith(('\\\\','//'))
    result={}
    routes=[('analyses',list_registered_analyses,load_registered_analysis),('youtube',list_registered_youtube,load_registered_youtube),
            ('shopify',list_registered_shopify,load_registered_shopify),('linktree',list_registered_linktree,load_registered_linktree),
            ('tiktok',list_registered_tiktok,load_registered_tiktok)]
    for name,listing,loading in routes:
        rows=listing(root)
        result[name]=[]
        for row in rows:
            repo=loading(root,row['key'],**({'verify_all':verify_all} if name=='tiktok' else {}))
            assert repo is not None,'Missing registered '+name
            result[name].append(row['key'])
            if verify_all and name=='analyses':
                assert hashlib.sha256(repo.original_zip()).hexdigest()==repo.metadata['zip_sha256']
    if verify_all:
        checked=[]
        for path in root.rglob('*.sqlite3'):
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok',str(path)
            checked.append(str(path.relative_to(root)))
        result['integrityCheckedDatabases']=checked
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);parser.add_argument('--verify-all',action='store_true')
    args=parser.parse_args()
    print(json.dumps(validate_registered_library(args.data,verify_all=args.verify_all)))
