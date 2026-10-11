import unittest
from src.change_evidence import ModalBaseline,collection_change


class ChangeEvidenceTests(unittest.TestCase):
    def test_baseline_precedes_modal_not_apply(self):
        tracker=ModalBaseline()
        listing={'nodes':[{'resource_id':'app:id/list'}]}
        sheet={'nodes':[{'resource_id':'app:id/design_bottom_sheet'}]}
        refreshed={'nodes':[{'resource_id':'app:id/list'}]}
        tracker.observe(listing);tracker.observe(sheet);tracker.observe(sheet);tracker.observe(refreshed)
        self.assertIs(tracker.before,listing)
        tracker.consume();self.assertIsNone(tracker.before)

    def test_unknown_hierarchy_does_not_replace_baseline(self):
        tracker=ModalBaseline();listing={'nodes':[{'resource_id':'app:id/list'}]}
        tracker.observe(listing);tracker.observe({'nodes':[]})
        tracker.observe({'nodes':[{'resource_id':'app:id/dialog'}]})
        self.assertIs(tracker.before,listing)

    def test_scoped_item_change_excludes_header_and_clock(self):
        def obs(names):
            return {'nodes':[{'resource_id':'app:id/item_name','text':name,
                'bounds':[10,100+i*100,150,180+i*100]} for i,name in enumerate(names)]}
        before=obs(['One','Two']);current=obs(['Three','Two'])
        result,_=collection_change(before,current,[0,90,200,400],[0,90,200,400])
        self.assertEqual(result['status'],'passed')
        result,_=collection_change(before,before,[0,90,200,400],[0,90,200,400])
        self.assertIsNone(result)
        result,_=collection_change(before,current,[0,500,200,900],[0,500,200,900])
        self.assertIsNone(result)

    def test_single_visible_named_item_can_prove_identity_change(self):
        def obs(name):
            return {'nodes':[{'resource_id':'app:id/product_name','text':name,'bounds':[10,100,150,180]}]}
        result,_=collection_change(obs('One'),obs('Two'),[0,90,200,400],[0,90,200,400])
        self.assertEqual(result['status'],'passed')
