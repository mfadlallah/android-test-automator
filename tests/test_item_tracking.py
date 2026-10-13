import unittest
from src.item_tracking import ItemTracker, resolve_tracked
from src.collections import CollectionError


def scene(names=('A','B'), positions=(0,600), widths=(600,480),vertical=False):
    box=[0,0,1080,1800] if vertical else [0,0,1080,700]
    rows=[dict(node=1,parent=None,bounds=box,resource_id='p:id/cards',scrollable=True,enabled=True)]
    for i,(name,pos,width) in enumerate(zip(names,positions,widths)):
        bounds=[0,pos,1080,pos+width] if vertical else [pos,0,pos+width,700]
        rows.append(dict(node=10+i,parent=1,bounds=bounds,clickable=True,enabled=True))
        field=[10,pos+10,200,pos+50] if vertical else [pos+10,10,pos+min(200,width),50]
        rows.append(dict(node=20+i,parent=10+i,bounds=field,resource_id='p:id/title',text=name))
    return {'nodes':rows}


class ItemTrackingTests(unittest.TestCase):
    def tracker(self,vertical=False):
        return ItemTracker('cards',3,['cards','title'],'down' if vertical else 'left')

    def anchor(self,tracker,obs):
        self.assertIsNotNone(tracker.observe(obs))
        self.assertIsNotNone(tracker.observe(obs))
        self.assertIsNotNone(tracker.observe(obs))
        self.assertEqual(tracker.phase,'seek')

    def test_third_across_two_card_windows_and_clipping(self):
        t=self.tracker();self.anchor(t,scene())
        self.assertIsNotNone(t.observe(scene(('B','C'),(0,900),(600,180))))
        current=scene(('B','C'),(0,480),(480,600))
        self.assertIsNone(t.observe(current))
        self.assertEqual(t.selected['identity'],['p:id/title','C'])
        self.assertEqual(t.sequence,[('p:id/title','A'),('p:id/title','B'),('p:id/title','C')])
        self.assertEqual(resolve_tracked(t.selected,current)[1]['node'],11)
        with self.assertRaises(CollectionError):resolve_tracked(t.selected,scene(('B','D'),(0,480),(480,600)))

    def test_vertical_uses_same_tracking(self):
        t=self.tracker(True);initial=scene(widths=(900,900),positions=(0,900),vertical=True)
        self.anchor(t,initial)
        self.assertIsNone(t.observe(scene(('B','C'),(0,900),(900,900),True)))

    def test_lost_overlap_and_duplicates_block(self):
        t=self.tracker();self.anchor(t,scene())
        with self.assertRaises(CollectionError):t.observe(scene(('C','D')))
        with self.assertRaises(CollectionError):self.tracker().observe(scene(('A','A')))

    def test_reset_moves_to_observed_start_and_bounded_budget(self):
        t=self.tracker();self.assertEqual(t.observe(scene(('B','C')))['direction'],'right')
        t.observe(scene());t.observe(scene());t.observe(scene())
        self.assertEqual(t.sequence,[('p:id/title','A'),('p:id/title','B')])
        t=ItemTracker('cards',3,['cards','title'],'left',max_swipes=1)
        t.observe(scene())
        with self.assertRaises(CollectionError):t.observe(scene())

    def test_reorder_blocks_and_selection_revalidated(self):
        t=self.tracker();self.anchor(t,scene())
        with self.assertRaises(CollectionError):t.observe(scene(('B','A')))

class TrackedExecutionTests(unittest.TestCase):
    def test_seek_capture_tap_and_compare_destination(self):
        import tempfile,json
        from pathlib import Path
        from unittest.mock import patch
        from src.main import run_sequential_plan
        from tests.test_collections import step
        seek=step(1,'seek_item','cards','left');seek.update(value='3',hints=['cards','title'])
        capture=step(2,'capture_text','tracked item of cards');capture.update(value='selected_title',hints=['cards','title'])
        tap=step(3,'tap','tracked item of cards')
        compare=step(4,'assert_contains','menu_title');compare['value']='$selected_title'
        plan={'steps':[seek,capture,tap,compare]}
        class Device:
            def __init__(self):self.calls=[]
            def observe(self,folder,index,*args):
                obs=scene() if index<3 else scene(('B','C'),(0,480),(480,600))
                if index>=6:
                    obs={'nodes':[dict(node=99,parent=None,bounds=[0,0,900,100],resource_id='p:id/menu_title',text='C')]}
                obs.update(observation=index,png=b'')
                return obs
            def execute(self,decision,obs):self.calls.append((decision['action'],decision.get('node')))
        device=Device()
        with tempfile.TemporaryDirectory() as folder, patch('src.main.read_screen_ocr',return_value=[]),patch('src.main.in_app_message_gate',return_value=None),patch('src.main.unexpected_modal_back_gate',return_value=None),patch('src.main.current_home_screen',return_value=False):
            status,reason,history,_=run_sequential_plan(device,Path(folder),plan,None,None)
            self.assertEqual(status,'PASSED',reason)
            self.assertEqual(json.loads((Path(folder)/'captured-values.json').read_text())['selected_title']['text'],'C')
            self.assertTrue((Path(folder)/'item-tracking.json').exists())
        self.assertIn(('tap',11),device.calls)
        self.assertEqual(sum(r['step_completed'] for r in history),4)
