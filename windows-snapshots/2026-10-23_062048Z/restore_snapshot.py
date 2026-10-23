#!/usr/bin/env python3
"""Verify, join, or restore The Stats Windows snapshot with Python 3 standard library."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, shutil, sys, zipfile, re

def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(4*1024*1024):h.update(chunk)
    return h.hexdigest()

def safe_relative(text):
    p=PurePosixPath(text)
    reserved={'CON','PRN','AUX','NUL'}|{'COM'+str(i) for i in range(1,10)}|{'LPT'+str(i) for i in range(1,10)}
    if p.is_absolute() or not p.parts or any(x in {'..','.'} or x.rstrip(' .')!=x or x.split('.')[0].upper() in reserved or any(ord(c)<32 or c in '<>:"|?*' for c in x) for x in p.parts) or '\\' in text:
        raise ValueError('Unsafe archive path: '+text)
    return Path(*p.parts)

def verify(package):
    with zipfile.ZipFile(package) as z:
        manifest=json.loads(z.read('MANIFEST.json'))
        objects={r['sha256']:r['bytes'] for r in manifest['files']}
        actual={n for n in z.namelist() if n.startswith('objects/')}
        expected={'objects/'+h for h in objects}
        if actual!=expected:raise ValueError('Object inventory differs from manifest')
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate ZIP member names')
        checksum_names=set()
        for n,line in enumerate(z.read('CHECKSUMS.sha256').decode().splitlines()):
            expected_hash,name=line.split('  ',1)
            if name in checksum_names:raise ValueError('Duplicate checksum entry: '+name)
            checksum_names.add(name)
            if not re.fullmatch('[0-9a-f]{64}',expected_hash):raise ValueError('Invalid checksum encoding')
            if name.startswith('objects/') and name!='objects/'+expected_hash:raise ValueError('Object hash differs from object name: '+name)
            h=hashlib.sha256()
            with z.open(name) as f:
                while chunk:=f.read(4*1024*1024):h.update(chunk)
            if h.hexdigest()!=expected_hash:raise ValueError('Checksum mismatch: '+name)
        if checksum_names!=set(z.namelist())-{'CHECKSUMS.sha256'}:raise ValueError('Checksum inventory does not cover every archive member exactly once')
        for h,size in objects.items():
            if z.getinfo('objects/'+h).file_size!=size:raise ValueError('Object length mismatch: '+h)
        seen=set()
        for record in manifest['files']:
            safe_relative(record['path'])
            if record['path'].casefold() in seen:raise ValueError('Duplicate or case-colliding restore path: '+record['path'])
            seen.add(record['path'].casefold())
    return manifest

def restore(package, destination):
    dest=Path(destination).resolve()
    if dest.exists():raise ValueError('Restore destination must not already exist: '+str(dest))
    manifest=verify(package)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(package) as z:
        for record in manifest['files']:
            target=dest/safe_relative(record['path'])
            if not target.resolve().is_relative_to(dest):raise ValueError('Restore path escapes destination')
            target.parent.mkdir(parents=True,exist_ok=True)
            h=hashlib.sha256()
            with z.open('objects/'+record['sha256']) as src,target.open('xb') as out:
                while chunk:=src.read(4*1024*1024):
                    out.write(chunk);h.update(chunk)
            if h.hexdigest()!=record['sha256']:raise ValueError('Restored file checksum mismatch: '+record['path'])
    return {'restored_files':len(manifest['files']),'destination':str(dest)}

def join(parts_manifest,output):
    mf=Path(parts_manifest);data=json.loads(mf.read_text(encoding='utf-8'))
    out=Path(output)
    if out.exists():raise ValueError('Joined output already exists: '+str(out))
    with out.open('xb') as stream:
        for part in data['parts']:
            p=mf.parent/safe_relative(part['path'])
            if p.stat().st_size!=part['bytes'] or digest_file(p)!=part['sha256']:raise ValueError('Invalid part: '+part['path'])
            with p.open('rb') as source:shutil.copyfileobj(source,stream,4*1024*1024)
    if out.stat().st_size!=data['bytes'] or digest_file(out)!=data['sha256']:raise ValueError('Joined package checksum mismatch')
    return {'joined_file':str(out),'bytes':data['bytes'],'sha256':data['sha256']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    v=commands.add_parser('verify');v.add_argument('package')
    r=commands.add_parser('restore');r.add_argument('package');r.add_argument('destination')
    j=commands.add_parser('join');j.add_argument('parts_manifest');j.add_argument('output')
    args=parser.parse_args()
    if args.command=='verify':
        m=verify(args.package);result={'verified_files':len(m['files']),'unique_objects':len({x['sha256'] for x in m['files']}),'logical_bytes':sum(x['bytes'] for x in m['files'])}
    elif args.command=='restore':result=restore(args.package,args.destination)
    else:result=join(args.parts_manifest,args.output)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
