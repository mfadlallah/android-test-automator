import io
import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from src.model_evidence import compact_chat_request, compact_nodes, context_overflow, node_table, intern_node_table
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
        table=evidence['nodes']
        node={k:v for k,v in zip(table['columns'],table['rows'][0]) if v is not None}
        self.assertEqual(node, {'node': 19, 'parent': 8,
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

    def test_nested_context_error(self):
        nested=json.dumps({'error':json.dumps({'error':{'type':'exceed_context_size_error'}})})
        self.assertTrue(context_overflow(400,nested))
        self.assertFalse(context_overflow(500,nested))

    def test_columnar_nodes_preserve_labels_and_states(self):
        nodes=[{'node':n,'parent':n-1,'text':'Ad' if n==9 else 'Name',
                'enabled':False,'checked':False,'bounds':[0,n,100,n+1]} for n in range(200)]
        table=node_table(nodes)
        restored=[{k:v for k,v in zip(table['columns'],row) if v is not None} for row in table['rows']]
        self.assertEqual(restored,nodes)
        self.assertLess(len(json.dumps(table)),len(json.dumps(nodes)))

    def test_retry_table_references_are_lossless(self):
        nodes=[{'node':n,'resource_id':'app.package.debug:id/shared_label',
                'text':'Visible label','enabled':False} for n in range(100)]
        table=node_table(nodes);compressed=intern_node_table(table)
        restored=[[compressed['strings'][cell['ref']] if isinstance(cell,dict) and 'ref' in cell else cell
                   for cell in row] for row in compressed['rows']]
        self.assertEqual(restored,table['rows'])
        payload={'messages':[{'role':'user','content':json.dumps({'nodes':table}), 'images':['keep-image']}]}
        retry=compact_chat_request(payload)
        self.assertIsNotNone(retry)
        self.assertEqual(retry['messages'][0]['images'],['keep-image'])


class PrefixedAssertionEvidenceTests(unittest.TestCase):
    def test_retry_compacts_both_comparison_sides_and_keeps_images(self):
        from src.model_evidence import compact_chat_request
        nodes=[{'node':i,'text':'Visible label','resource_id':'example:id/repeated_name','checked':False} for i in range(80)]
        payload={'messages':[{'role':'user','content':label+' scoped screen evidence: '+json.dumps({'nodes':nodes}), 'images':['original-image']} for label in ['BEFORE','CURRENT']]}
        retry=compact_chat_request(payload)
        self.assertIsNotNone(retry)
        for message,label in zip(retry['messages'],['BEFORE','CURRENT']):
            prefix,body=message['content'].split(': ',1)
            self.assertEqual(prefix,label+' scoped screen evidence')
            table=json.loads(body)['nodes']
            self.assertEqual(len(table['rows']),80)
            self.assertIn('checked',table['columns'])
            self.assertEqual(message['images'],['original-image'])
        self.assertLess(len(json.dumps(retry)),len(json.dumps(payload)))
