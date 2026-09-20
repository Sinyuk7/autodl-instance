"""Process ownership checks for ComfyUI lifecycle commands."""
import signal
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.utils import (
    _is_owned_comfy_process, _process_identity,
    ensure_port_available, stop_owned_comfy_listener,
)

COMFY = Path('/target/ComfyUI')
ENV = Path('/target/venv')


def test_start_refuses_occupied_port_without_killing():
    with patch('src.core.utils.listening_pids', return_value=[42]), patch(
        'src.core.utils.os.kill'
    ) as kill, pytest.raises(RuntimeError, match='不会自动终止'):
        ensure_port_available(6006)
    kill.assert_not_called()


@pytest.mark.parametrize('cwd,exe,argv,expected', [
    (COMFY, '/real/python', b'/target/venv/bin/python\0main.py\0', True),
    (COMFY, '/real/python', b'/target/venv/bin/python\0/target/ComfyUI/main.py\0', True),
    (Path('/other'), '/real/python', b'/target/venv/bin/python\0main.py\0', False),
    (COMFY, '/bin/sleep', b'/target/venv/bin/python\0main.py\0', False),
    (COMFY, '/real/python', b'/other/venv/bin/python\0main.py\0', False),
    (COMFY, '/real/python', b'/target/venv/bin/python\0/other/main.py\0', False),
    (COMFY, '/real/python', b'/target/venv/bin/python\0-c\0main.py\0', False),
])
def test_ownership_requires_environment_executable_cwd_and_entrypoint(cwd, exe, argv, expected):
    def resolve(path, strict=False):
        return {
            Path('/proc/42/cwd'): cwd,
            Path('/proc/42/exe'): Path(exe),
            ENV / 'bin/python': Path('/real/python'),
        }.get(path, path)
    with patch.object(Path, 'resolve', resolve), patch.object(Path, 'read_bytes', return_value=argv):
        assert _is_owned_comfy_process(42, COMFY, ENV) is expected


def test_ownership_fails_closed_when_proc_unreadable():
    with patch.object(Path, 'resolve', side_effect=PermissionError):
        assert not _is_owned_comfy_process(42, COMFY, ENV)


@pytest.mark.parametrize('state,expected', [('S', '1234'), ('Z', None), ('X', None)])
def test_process_identity_parses_comm_with_parentheses(state, expected):
    stat = '42 (python (worker)) ' + ' '.join([state] + ['0'] * 18 + ['1234'])
    with patch.object(Path, 'read_text', return_value=stat):
        assert _process_identity(42) == expected


def test_process_identity_missing():
    with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
        assert _process_identity(42) is None


@pytest.fixture
def process_mocks():
    with patch('src.core.utils.listening_pids', return_value=[42]), patch(
        'src.core.utils._is_owned_comfy_process', return_value=True
    ) as owned, patch('src.core.utils._process_identity', return_value='123') as identity, patch(
        'src.core.utils.os.kill'
    ) as kill, patch('src.core.utils.time.sleep') as sleep:
        yield owned, identity, kill, sleep


def test_stop_refuses_unowned_listener(process_mocks):
    owned, _, kill, _ = process_mocks
    owned.return_value = False
    with pytest.raises(RuntimeError, match='无法确认属于目标 ComfyUI'):
        stop_owned_comfy_listener(6006, COMFY, ENV)
    kill.assert_not_called()


def test_stop_validates_all_listeners_before_signalling(process_mocks):
    owned, _, kill, _ = process_mocks
    owned.side_effect = [True, False]
    with patch('src.core.utils.listening_pids', return_value=[42, 43]), pytest.raises(RuntimeError):
        stop_owned_comfy_listener(6006, COMFY, ENV)
    kill.assert_not_called()


def test_stop_waits_for_exit(process_mocks):
    _, identity, kill, sleep = process_mocks
    identity.side_effect = ['123', '123', '123', '123', None]
    assert stop_owned_comfy_listener(6006, COMFY, ENV) == [42]
    kill.assert_called_once_with(42, signal.SIGTERM)
    sleep.assert_called_once()


def test_stop_timeout_is_failure_without_sigkill(process_mocks):
    _, _, kill, _ = process_mocks
    with pytest.raises(RuntimeError, match='退出超时.*未发送 SIGKILL'):
        stop_owned_comfy_listener(6006, COMFY, ENV, timeout=0)
    kill.assert_called_once_with(42, signal.SIGTERM)


@pytest.mark.parametrize('identities', [['123', '456'], ['123', '123', '456']])
def test_stop_refuses_reused_pid_before_signal(process_mocks, identities):
    _, identity, kill, _ = process_mocks
    identity.side_effect = identities
    with pytest.raises(RuntimeError, match='进程身份'):
        stop_owned_comfy_listener(6006, COMFY, ENV)
    kill.assert_not_called()


def test_stop_rechecks_ownership_before_signal(process_mocks):
    owned, _, kill, _ = process_mocks
    owned.side_effect = [True, False]
    with pytest.raises(RuntimeError, match='归属已变化'):
        stop_owned_comfy_listener(6006, COMFY, ENV)
    kill.assert_not_called()


def test_stop_does_not_wait_for_reused_pid(process_mocks):
    _, identity, kill, sleep = process_mocks
    identity.side_effect = ['123', '123', '123', '456']
    assert stop_owned_comfy_listener(6006, COMFY, ENV) == [42]
    kill.assert_called_once_with(42, signal.SIGTERM)
    sleep.assert_not_called()


def test_stop_handles_exit_before_signal(process_mocks):
    _, identity, kill, _ = process_mocks
    identity.side_effect = ['123', '123', '123', None]
    kill.side_effect = ProcessLookupError
    assert stop_owned_comfy_listener(6006, COMFY, ENV) == []


def test_stop_handles_already_exited_listener(process_mocks):
    _, identity, kill, _ = process_mocks
    identity.return_value = None
    assert stop_owned_comfy_listener(6006, COMFY, ENV) == []
    kill.assert_not_called()
