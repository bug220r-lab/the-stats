from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parent
failed = []
count = 0
for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
    expected, relative = line.split('  ', 1)
    path = root / relative
    count += 1
    if not path.is_file():
        failed.append(relative + ': missing')
        continue
    h = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            h.update(chunk)
    if h.hexdigest() != expected:
        failed.append(relative + ': checksum mismatch')
if failed:
    print('FAILED: ' + str(len(failed)) + ' of ' + str(count) + ' files')
    print('\n'.join(failed))
    sys.exit(1)
print('PASS: ' + str(count) + ' files match SHA-256 checksums.')
