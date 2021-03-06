import os.path
import sys
import unittest.mock

import py

import pytest
from _pytest.pathlib import ensure_deletable
from _pytest.pathlib import fnmatch_ex
from _pytest.pathlib import get_extended_length_path_str
from _pytest.pathlib import get_lock_path
from _pytest.pathlib import maybe_delete_a_numbered_dir
from _pytest.pathlib import Path


class TestPort:
    """Test that our port of py.common.FNMatcher (fnmatch_ex) produces the same results as the
    original py.path.local.fnmatch method.
    """

    @pytest.fixture(params=["pathlib", "py.path"])
    def match(self, request):
        if request.param == "py.path":

            def match_(pattern, path):
                return py.path.local(path).fnmatch(pattern)

        else:
            assert request.param == "pathlib"

            def match_(pattern, path):
                return fnmatch_ex(pattern, path)

        return match_

    if sys.platform == "win32":
        drv1 = "c:"
        drv2 = "d:"
    else:
        drv1 = "/c"
        drv2 = "/d"

    @pytest.mark.parametrize(
        "pattern, path",
        [
            ("*.py", "foo.py"),
            ("*.py", "bar/foo.py"),
            ("test_*.py", "foo/test_foo.py"),
            ("tests/*.py", "tests/foo.py"),
            (drv1 + "/*.py", drv1 + "/foo.py"),
            (drv1 + "/foo/*.py", drv1 + "/foo/foo.py"),
            ("tests/**/test*.py", "tests/foo/test_foo.py"),
            ("tests/**/doc/test*.py", "tests/foo/bar/doc/test_foo.py"),
            ("tests/**/doc/**/test*.py", "tests/foo/doc/bar/test_foo.py"),
        ],
    )
    def test_matching(self, match, pattern, path):
        assert match(pattern, path)

    def test_matching_abspath(self, match):
        abspath = os.path.abspath(os.path.join("tests/foo.py"))
        assert match("tests/foo.py", abspath)

    @pytest.mark.parametrize(
        "pattern, path",
        [
            ("*.py", "foo.pyc"),
            ("*.py", "foo/foo.pyc"),
            ("tests/*.py", "foo/foo.py"),
            (drv1 + "/*.py", drv2 + "/foo.py"),
            (drv1 + "/foo/*.py", drv2 + "/foo/foo.py"),
            ("tests/**/test*.py", "tests/foo.py"),
            ("tests/**/test*.py", "foo/test_foo.py"),
            ("tests/**/doc/test*.py", "tests/foo/bar/doc/foo.py"),
            ("tests/**/doc/test*.py", "tests/foo/bar/test_foo.py"),
        ],
    )
    def test_not_matching(self, match, pattern, path):
        assert not match(pattern, path)


def test_access_denied_during_cleanup(tmp_path, monkeypatch):
    """Ensure that deleting a numbered dir does not fail because of OSErrors (#4262)."""
    path = tmp_path / "temp-1"
    path.mkdir()

    def renamed_failed(*args):
        raise OSError("access denied")

    monkeypatch.setattr(Path, "rename", renamed_failed)

    lock_path = get_lock_path(path)
    maybe_delete_a_numbered_dir(path)
    assert not lock_path.is_file()


def test_long_path_during_cleanup(tmp_path):
    """Ensure that deleting long path works (particularly on Windows (#6775))."""
    path = (tmp_path / ("a" * 250)).resolve()
    if sys.platform == "win32":
        # make sure that the full path is > 260 characters without any
        # component being over 260 characters
        assert len(str(path)) > 260
        extended_path = "\\\\?\\" + str(path)
    else:
        extended_path = str(path)
    os.mkdir(extended_path)
    assert os.path.isdir(extended_path)
    maybe_delete_a_numbered_dir(path)
    assert not os.path.isdir(extended_path)


def test_get_extended_length_path_str():
    assert get_extended_length_path_str(r"c:\foo") == r"\\?\c:\foo"
    assert get_extended_length_path_str(r"\\share\foo") == r"\\?\UNC\share\foo"
    assert get_extended_length_path_str(r"\\?\UNC\share\foo") == r"\\?\UNC\share\foo"
    assert get_extended_length_path_str(r"\\?\c:\foo") == r"\\?\c:\foo"


def test_suppress_error_removing_lock(tmp_path):
    """ensure_deletable should not raise an exception if the lock file cannot be removed (#5456)"""
    path = tmp_path / "dir"
    path.mkdir()
    lock = get_lock_path(path)
    lock.touch()
    mtime = lock.stat().st_mtime

    with unittest.mock.patch.object(Path, "unlink", side_effect=OSError):
        assert not ensure_deletable(
            path, consider_lock_dead_if_created_before=mtime + 30
        )
    assert lock.is_file()

    # check now that we can remove the lock file in normal circumstances
    assert ensure_deletable(path, consider_lock_dead_if_created_before=mtime + 30)
    assert not lock.is_file()
