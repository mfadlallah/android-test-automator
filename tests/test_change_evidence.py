import unittest
from src.change_evidence import ModalBaseline,collection_change,collection_visible


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

    def test_collection_visible_needs_container_and_content(self):
        bounds=[0,100,200,400]
        obs={'nodes':[{'node':1,'scrollable':True,'bounds':bounds},
            {'node':2,'parent':1,'resource_id':'app:id/product_name','text':'One','bounds':[10,120,100,150]}]}
        step={'capability':'assert_visible','target':'refreshed product items'}
        self.assertEqual(collection_visible(step,obs,bounds)['status'],'passed')
        obs['nodes'][0]['scrollable']=False
        self.assertIsNone(collection_visible(step,obs,bounds))
        obs['nodes'][0]['scrollable']=True
        obs['nodes'].append({'resource_id':'app:id/dialog'})
        self.assertIsNone(collection_visible(step,obs,bounds))


class ChangeReferenceTests(unittest.TestCase):
    def test_layout_action_does_not_reuse_stale_modal_baseline(self):
        from src.change_evidence import change_reference
        old={'screen':'old row view before interruption'}
        immediate={'screen':'card view before tapping row'}
        self.assertIs(change_reference('assert_changed',old,immediate),immediate)
        self.assertIs(change_reference('wait_changed',old,immediate),old)
        self.assertIsNone(change_reference('assert_changed',old,None))

    def test_layout_intent_is_not_a_content_refresh(self):
        from src.change_evidence import layout_change_requested
        self.assertTrue(layout_change_requested({'capability':'assert_changed','success':'Verify Inventory list changed from compact view to detailed view'}))
        self.assertFalse(layout_change_requested({'capability':'wait_changed','success':'Wait until products refresh'}))
