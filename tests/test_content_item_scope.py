import json
import unittest
from pathlib import Path
from src.adapters.generic_adapter import GenericAdapter

class ContentScopeTests(unittest.TestCase):
    def setUp(self):
        self.nodes=json.loads((Path(__file__).parent/'fixtures/header-content-collection.json').read_text())
        self.adapter=GenericAdapter()

    def test_headers_and_nested_collections_are_not_content_items(self):
        result=self.adapter._find_first_item_in_container({'nodes':self.nodes},(0,263,1080,2205))
        self.assertEqual((0,941,1080,1822),result)

    def test_node_ids_are_not_array_offsets(self):
        nodes=[dict(n,node=n['node']+1000,parent=n['parent']+1000 if n.get('parent') is not None else None) for n in self.nodes]
        self.assertEqual((0,941,1080,1822), self.adapter._find_first_item_in_container({'nodes':nodes},(0,263,1080,2205)))

    def test_missing_identity_does_not_guess_header_or_badge_scope(self):
        for n in self.nodes:
            n['text']=''
        self.assertIsNone(self.adapter._find_first_item_in_container({'nodes':self.nodes},(0,263,1080,2205)))
