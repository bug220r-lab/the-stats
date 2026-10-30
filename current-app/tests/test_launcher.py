"""Launcher refusal paths must never start a process or open a browser."""

import importlib.util
from pathlib import Path
import socket

import pytest


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parents[1] / "scripts" / "launch.py"
    spec = importlib.util.spec_from_file_location("stats_test_launcher", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    project = tmp_path / "project"
    project.mkdir()
    (project / ".venv").mkdir()
    (project / "app.py").write_text("# Isolated launcher test placeholder\n", encoding="utf-8")
    monkeypatch.setattr(module, "PROJECT_ROOT", project)
    monkeypatch.setattr(module.sys, "prefix", str(project / ".venv"))
    monkeypatch.setattr(module.sys, "argv", [str(source)])
    monkeypatch.setenv("STATS_MODE", "local")
    monkeypatch.setenv("STATS_PORT", "8501")

    def forbidden_child(*args, **kwargs):
        pytest.fail("A refused launch must not start a child process.")

    def forbidden_browser(*args, **kwargs):
        pytest.fail("A refused launch must not open a browser.")

    monkeypatch.setattr(module.subprocess, "Popen", forbidden_child)
    monkeypatch.setattr(module.webbrowser, "open", forbidden_browser)
    return module


@pytest.mark.parametrize("value", ["not-a-number", "0", "1023", "65536", "8501.5"])
def test_invalid_port_argument_rejected_before_launch(launcher, monkeypatch, capsys, value):
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py", "--port", value])
    with pytest.raises(SystemExit) as exc:
        launcher.main()
    assert exc.value.code == 2
    assert "1024" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["", "invalid", "1023", "65536"])
def test_invalid_environment_port_rejected_before_launch(launcher, monkeypatch, capsys, value):
    monkeypatch.setenv("STATS_PORT", value)
    with pytest.raises(SystemExit) as exc:
        launcher.main()
    assert exc.value.code == 2
    assert "1024" in capsys.readouterr().err


def test_occupied_loopback_port_refused_without_child_or_browser(launcher, monkeypatch, capsys):
    # An ephemeral loopback socket avoids the user's running dashboard and uses
    # the real OS bind behavior instead of mocking the safety check itself.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]
        monkeypatch.setattr(launcher.sys, "argv", ["launch.py", "--port", str(port)])
        assert launcher.main() == 1
    error = capsys.readouterr().err
    assert str(port) in error
    assert "already in use or unavailable" in error
    assert "No browser has been opened" in error


def test_wrong_virtual_environment_refused(launcher, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(launcher.sys, "prefix", str(tmp_path / "another-environment"))
    assert launcher.main() == 1
    assert "Use the project environment" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["hosted", "unexpected"])
def test_nonlocal_mode_refused_without_child_or_browser(launcher, monkeypatch, capsys, mode):
    monkeypatch.setenv("STATS_MODE", mode)
    assert launcher.main() == 1
    assert "local mode only" in capsys.readouterr().err
