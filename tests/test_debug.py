import contextlib
import io
import os
import unittest
from unittest.mock import patch
from src.debug import debug_print


class DebugTests(unittest.TestCase):
    def test_individual_run_keeps_debug_by_default(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(output):
            debug_print('DEBUG details')
        self.assertEqual(output.getvalue(), 'DEBUG details\n')

    def test_suite_suppresses_debug_not_results(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'MOBILE_AGENT_DEBUG': '0'}), contextlib.redirect_stdout(output):
            debug_print('DEBUG multiline\ndetails')
            print('FAILED: expected label missing')
        self.assertEqual(output.getvalue(), 'FAILED: expected label missing\n')
