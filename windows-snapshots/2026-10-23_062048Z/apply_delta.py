#!/usr/bin/env python3
"""Apply the separately verified post-capture delta to a restored Windows snapshot."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,zipfile,re

def safe_relative(text):
    p=PurePosixPath(text)
    reserved={'CON','PRN','AUX','NUL'}|{'COM'+str(i) for i in range(1,10)}|{'LPT'+str(i) for i in range(1,10)}
    if p.is_absolute() or not p.parts or any(x in {'..','.'} or x.rstrip(' .')!=x or x.split('.')[0].upper() in reserved or any(ord(c)<32 or c in '<>:"|?*' for c in x) for x in p.parts) or '\\' in text:raise ValueError('Unsafe relative path: '+text)
    return Path(*p.parts)

def sha_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(4*1024*1024):h.update(b)
    return h.hexdigest()

def verify(z):
    names=z.namelist()
    if len(names)!=len(set(names)):raise ValueError('Duplicate archive entry')
    checks={}
    for line in z.read('CHECKSUMS.sha256').decode().splitlines():
        digest,name=line.split('  ',1)
        if name in checks or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid checksum list')
        checks[name]=digest
        if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('Checksum mismatch: '+name)
    if set(checks)!=set(names)-{'CHECKSUMS.sha256'}:raise ValueError('Incomplete checksum coverage')
    manifest=json.loads(z.read('DELTA_MANIFEST.json'))
    seen=set()
    for r in manifest['files']:
        safe_relative(r['path'])
        if not r['path'].startswith('workspace/'):raise ValueError('Delta contains an unexpected source root')
        key=r['path'].casefold()
        if key in seen:raise ValueError('Case-colliding delta path')
        seen.add(key)
        if checks.get(r['path'])!=r['sha256'] or len(z.read(r['path']))!=r['bytes']:raise ValueError('Delta manifest mismatch: '+r['path'])
    return manifest

def apply(package,destination):
    dest=Path(destination).resolve()
    if not dest.is_dir() or not (dest/'workspace').is_dir() or not (dest/'active-library').is_dir():raise ValueError('Destination must be the root of an existing restored Windows snapshot')
    with zipfile.ZipFile(package) as z:
        manifest=verify(z);writes=[];already=[]
        for r in manifest['files']:
            target=dest/safe_relative(r['path'])
            if not target.resolve().is_relative_to(dest):raise ValueError('Delta path escapes restore destination')
            current=sha_file(target) if target.exists() else None
            if current==r['sha256']:already.append(r['path']);continue
            if current!=r['base_sha256']:raise ValueError('Restored file differs from expected base; refusing overwrite: '+r['path'])
            tmp=target.with_name(target.name+'.delta-tmp')
            if tmp.exists():raise ValueError('Temporary delta output already exists: '+str(tmp))
            writes.append((r,target,tmp))
        for r,target,tmp in writes:
            target.parent.mkdir(parents=True,exist_ok=True)
            with tmp.open('xb') as f:f.write(z.read(r['path']))
            if sha_file(tmp)!=r['sha256']:raise ValueError('Delta write verification failed')
            os.replace(tmp,target)
        return {'applied_files':len(writes),'already_applied_files':len(already),'capture_finished_utc':manifest['capture_finished_utc']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('delta_zip');p.add_argument('restored_root',nargs='?');p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    if a.verify_only:
        with zipfile.ZipFile(a.delta_zip) as z:m=verify(z)
        result={'verified_delta_files':len(m['files']),'capture_finished_utc':m['capture_finished_utc']}
    elif a.restored_root:result=apply(a.delta_zip,a.restored_root)
    else:p.error('Provide restored_root or --verify-only')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
