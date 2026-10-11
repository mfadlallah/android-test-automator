import io
import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from src.model_evidence import compact_chat_request, compact_nodes, context_overflow
from src.main import local_request, Blocked


class ModelEvidenceTests(unittest.TestCase):
    def payload(self):
        return {'messages': [{'role': 'system', 'content': 'Keep the exact assertion.'},
            {'role': 'user', 'images': ['original-image'], 'content': json.dumps({
                'step': {'capability': 'assert_not_contains', 'value': 'Ad'},
                'nodes': [{'node': 19, 'parent': 8, 'enabled': False,
                           'selected': False, 'text': 'Ad', 'package': 'repeated-package'}],
                'recent_actions': [{'action': 'tap', 'reason': 'Apply', 'usage': 'x' * 4000}]})}],
            'format': {'required': ['status']}}

    def test_compaction_preserves_assertion_and_image_and_identity(self):
        original = self.payload()
        reduced = compact_chat_request(original)
        evidence = json.loads(reduced['messages'][1]['content'])
        self.assertEqual(evidence['nodes'][0], {'node': 19, 'parent': 8,
            'enabled': False, 'selected': False, 'text': 'Ad'})
        self.assertEqual(evidence['step']['value'], 'Ad')
        self.assertEqual(reduced['messages'][1]['images'], ['original-image'])
        self.assertEqual(reduced['messages'][0], original['messages'][0])
        self.assertIn('package', json.loads(original['messages'][1]['content'])['nodes'][0])

    def test_all_nodes_retained(self):
        nodes = [{'node': n, 'parent': n-1, 'text': str(n)} for n in range(500)]
        self.assertEqual(compact_nodes(nodes), nodes)

    def test_only_context_error_retried(self):
        self.assertTrue(context_overflow(400, '{"error":{"type":"exceed_context_size_error"}}'))
        self.assertFalse(context_overflow(400, '{"error":"model missing"}'))

    def test_request_retries_once(self):
        error = urllib.error.HTTPError('local', 400, 'bad', {},
            io.BytesIO(b'{"error":{"type":"exceed_context_size_error"}}'))
        response = MagicMock()
        response.__enter__.return_value = io.StringIO('{"done":true}')
        opener = MagicMock()
        opener.open.side_effect = [error, response]
        with patch('src.main.urllib.request.build_opener', return_value=opener):
            self.assertEqual(local_request('/api/chat', self.payload()), {'done': True})
        self.assertEqual(opener.open.call_count, 2)

    def test_other_400_not_retried(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError('local', 400, 'bad', {}, io.BytesIO(b'{"error":"bad schema"}'))
        with patch('src.main.urllib.request.build_opener', return_value=opener), self.assertRaises(Blocked):
            local_request('/api/chat', self.payload())
        self.assertEqual(opener.open.call_count, 1)
