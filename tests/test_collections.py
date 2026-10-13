import unittest
from src.collections import (CollectionError, resolve_collection, resolve_item,
                             swipe_points, scroll_changed)
from src.planning import validate_plan, canonicalize_model_plan, PlanError


def node(i, parent, bounds, **kw):
    return dict(node=i,parent=parent,bounds=bounds,enabled=True,**kw)


def scene(offset=0):
    return {'nodes':[
        node(1,None,[0,0,1000,2000],scrollable=True,resource_id='p:id/results'),
        node(2,1,[0,0,1000,400]), node(3,1,[0,400,1000,800]),
        node(4,1,[0,800,1000,1500]),
        node(5,4,[0,800,1000,900],text='Recommended'),
        node(6,4,[0,900,1000,1400],scrollable=True,resource_id='p:id/horizontal_scroll'),
        node(7,6,[10,900,300,1400],clickable=True),
        node(8,6,[310,900,600,1400],clickable=True),
        node(9,6,[610,900,900,1400],clickable=True),
        node(10,7,[20+offset,950,200+offset,1000],text='Alpha',resource_id='p:id/name'),
        node(11,8,[320+offset,950,500+offset,1000],text='Beta',resource_id='p:id/name'),
        node(12,9,[620+offset,950,800+offset,1000],text='Gamma',resource_id='p:id/name')]}


def step(i, cap, target, direction='none'):
    return dict(id=str(i),capability=cap,role='assertion' if cap.startswith('assert') else 'action',
                target=target,hints=[],value='',position='none',direction=direction,optional=False,success='')


class CollectionTests(unittest.TestCase):
    def test_axis_selects_nested_container(self):
        self.assertEqual(resolve_collection('Recommended horizontal collection',scene(),direction='left')['node'],6)
        self.assertEqual(resolve_collection('vertical results list',scene(),direction='down')['node'],1)

    def test_third_item_is_structural_not_literal_label(self):
        container,item=resolve_item('Third visible item of Recommended horizontal collection',scene())
        self.assertEqual((container['node'],item['node']),(6,9))

    def test_missing_clipped_and_ambiguous_ordinals_block(self):
        for target in ['Fourth visible item of horizontal collection','Third item of horizontal collection']:
            with self.assertRaises(CollectionError): resolve_item(target,scene())
        obs=scene();obs['nodes'][8]['bounds'][2]=1100
        with self.assertRaises(CollectionError): resolve_item('Third visible item of horizontal collection',obs)

    def test_does_not_fall_back_to_vertical(self):
        obs=scene();obs['nodes']=[n for n in obs['nodes'] if n['node']<6]
        with self.assertRaises(CollectionError): resolve_collection('horizontal collection',obs,direction='left')

    def test_horizontal_points_and_scoped_motion(self):
        self.assertEqual(swipe_points([0,900,1000,1400],'left'),(850,1150,150,1150))
        moved,evidence=scroll_changed(scene(),scene(-60),'horizontal collection','left')
        self.assertTrue(moved);self.assertIn('Alpha',evidence)
        self.assertFalse(scroll_changed(scene(),scene(),'horizontal collection','left')[0])

    def test_planner_rejects_axis_conflict(self):
        p={'version':1,'name':'test','steps':[step(1,'scroll','horizontal collection','down')]}
        with self.assertRaises(PlanError): validate_plan(p)
        p['steps'][0]['direction']='left'
        self.assertEqual(validate_plan(p)['steps'][0]['direction'],'left')

    def test_proof_before_navigation(self):
        p={'version':1,'name':'test','steps':[step(1,'scroll','horizontal collection','left'),
            step(2,'tap','Item'),step(3,'assert_visible','Next screen'),
            step(4,'assert_scrolled','horizontal collection')]}
        out=canonicalize_model_plan(p)
        self.assertEqual([s['capability'] for s in out['steps']],
                         ['scroll','assert_scrolled','tap','assert_visible'])
