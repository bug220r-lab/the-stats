import os
import shutil
import pytest
from stats_app.native_paths import native_path
from stats_app.tiktok_repository import TikTokRepository
from stats_app.linktree_repository import LinktreeRepository
from tiktok_studio_fixtures import studio_package
from linktree_fixtures import synthetic_package

@pytest.mark.skipif(os.name!='nt',reason='Windows native long-path regression')
@pytest.mark.parametrize('factory,repository',[(studio_package,TikTokRepository),(synthetic_package,LinktreeRepository)])
def test_deep_collection_evidence_remains_readable(tmp_path,factory,repository):
    source=factory(tmp_path)
    logical=tmp_path/('a'*65)/('b'*65)/('c'*65)/'package'
    assert len(str(logical))>260
    shutil.copytree(source,native_path(logical))
    repo=repository(logical)
    assert repo.package_dir==logical.absolute()
    name=repo.sources().path.iloc[0]
    assert repo.original_bytes(name)==native_path(source/name).read_bytes()

def test_native_path_is_idempotent(tmp_path):
    assert native_path(native_path(tmp_path))==native_path(tmp_path)
