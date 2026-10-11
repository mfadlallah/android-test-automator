import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.hierarchy_backend import capture, resolve_backend, snapshot
from src.main import Blocked, Device


XML='<hierarchy><node package="example.app" resource-id="example.app:id/item" bounds="[0,0][100,100]"/></hierarchy>'


class SnapshotBackendTests(unittest.TestCase):
    def test_worker_disables_idle_wait_and_preserves_resource_ids(self):
        device=Mock()
        device.dump_hierarchy.return_value=XML
        module=SimpleNamespace(connect=Mock(return_value=device))
        with tempfile.TemporaryDirectory() as tmp,patch.dict('sys.modules',{'uiautomator2':module}):
            path=Path(tmp)/'dump.xml'
            snapshot('chosen-device',path)
            module.connect.assert_called_once_with('chosen-device')
            device.jsonrpc.setConfigurator.assert_called_once_with(
                {'waitForIdleTimeout':0,'waitForSelectorTimeout':0})
            self.assertIn('example.app:id/item',path.read_text())

    @patch('src.hierarchy_backend.subprocess.run')
    def test_timeout_is_bounded_and_retains_partial_diagnostics(self,run):
        run.side_effect=subprocess.TimeoutExpired([],25,output=b'connecting',stderr=b'busy')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'dump.xml';path.write_text(XML)
            log=Path(tmp)/'log.jsonl'
            with self.assertRaisesRegex(RuntimeError,'exceeded'):
                capture('serial',path,log)
            self.assertFalse(path.exists())  # no stale snapshot may survive
            record=json.loads(log.read_text())
            self.assertTrue(record['timed_out'])
            self.assertEqual('busy',record['stderr'])

    @patch('src.hierarchy_backend.subprocess.run')
    def test_empty_tree_is_rejected(self,run):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'dump.xml';log=Path(tmp)/'log.jsonl'
            def complete(*args,**kwargs):
                path.write_text('<hierarchy/>')
                return subprocess.CompletedProcess([],0,b'',b'')
            run.side_effect=complete
            with self.assertRaisesRegex(RuntimeError,'no nodes'):
                capture('serial',path,log)

    @patch('src.main.capture_hierarchy',return_value=XML)
    def test_service_snapshot_keeps_ids_without_shell_dump(self,capture_mock):
        device=Device('serial','example.app')
        device.hierarchy_backend='uiautomator2'
        device.foreground_package=Mock(return_value='example.app')
        device.adb=Mock(return_value=b'\x89PNG\r\n\x1a\n')
        with tempfile.TemporaryDirectory() as tmp:
            obs=device.observe(Path(tmp),1,allow_screenshot_only=True)
            self.assertEqual('example.app:id/item',obs['nodes'][0]['resource_id'])
            capture_mock.assert_called_once()
        self.assertFalse(any(c.args[:3]==('shell','uiautomator','dump')
                             for c in device.adb.call_args_list))

    @patch('src.main.time.sleep')
    def test_idle_failure_does_not_repeat_same_dump(self,_sleep):
        device=Device('serial','example.app')
        def adb(*args,**kwargs):
            if args[:3]==('shell','uiautomator','dump'):
                raise Blocked('UIAutomator could not get idle state')
            return b'\x89PNG\r\n\x1a\n' if args[0]=='exec-out' else ''
        device.adb=Mock(side_effect=adb)
        with tempfile.TemporaryDirectory() as tmp:
            obs=device.observe(Path(tmp),1)
            self.assertTrue(obs['hierarchy_unavailable'])
        self.assertEqual(1,sum(c.args[:3]==('shell','uiautomator','dump')
                              for c in device.adb.call_args_list))

    @patch('src.main.subprocess.run')
    def test_zero_exit_idle_error_is_classified_before_file_check(self,run):
        run.return_value=subprocess.CompletedProcess([],0,b'',
            b'ERROR: could not get idle state.\n')
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'log.jsonl'
            with self.assertRaisesRegex(Blocked,'could not get idle state'):
                Device('serial','example.app').adb('shell','uiautomator','dump',
                    'file.xml',diagnostic_path=log)
            self.assertEqual(0,json.loads(log.read_text())['exit_code'])

    @patch('src.hierarchy_backend.importlib.util.find_spec',return_value=None)
    def test_explicit_backend_has_actionable_missing_dependency_error(self,_spec):
        self.assertEqual('adb',resolve_backend('auto'))
        with self.assertRaisesRegex(RuntimeError,'pip install'):
            resolve_backend('uiautomator2')
