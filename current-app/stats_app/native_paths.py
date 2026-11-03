"""Extended Windows paths for retained collection files, without OS changes."""
import os
from pathlib import Path

def native_path(value):
    path=Path(value).absolute()
    text=str(path)
    if os.name=='nt' and not text.startswith('\\\\?\\'):
        text='\\\\?\\UNC\\'+text[2:] if text.startswith('\\\\') else '\\\\?\\'+text
        return Path(text)
    return path
