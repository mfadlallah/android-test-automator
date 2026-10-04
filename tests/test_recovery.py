import json
import struct
import unittest

from src.recovery import Recovery, assess, normalize_visual_point


def png(width=1080, height=2340):
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * 8 + struct.pack('>II', width, height)


def node(number, parent, bounds, text='', resource_id='', class_name='android.view.View', enabled=True):
    return {'node': number, 'parent': parent, 'bounds': bounds, 'text': text,
            'description': '', 'resource_id': resource_id, 'class_name': class_name,
            'enabled': enabled, 'clickable': False, 'scrollable': False}


def sheet_observation(target='Cancel'):
    return {'observation': 0, 'png': png(), 'ocr': [], 'nodes': [
        node(0, None, [0, 1200, 1080, 2250], resource_id='app:id/bottom_sheet',
             class_name='android.widget.FrameLayout'),
        node(1, 0, [80, 1250, 1000, 1370], text='Special offer'),
        node(2, 0, [100, 2000, 980, 2150], text=target),
    ]}


def home_observation():
    return {'observation':0,'png':png(),'ocr':[],'nodes':[
        node(0,None,[0,0,1080,2200],resource_id='app:id/root',
             class_name='android.widget.FrameLayout'),
        node(1,0,[20,700,1060,1700],resource_id='app:id/content_card',
             class_name='android.widget.FrameLayout'),
        node(2,1,[40,740,1040,850],text='Challenges'),
        node(3,0,[40,500,1040,620],text='Welcome',
             resource_id='app:id/welcome_message_headline'),
    ]}


class RecoveryTests(unittest.TestCase):
    def test_clear_screen_continues(self):
        obs={'observation': 0, 'png': png(), 'ocr': [],
             'nodes': [node(0, None, [0, 0, 1080, 2200], text='Home')]}
        result=Recovery().handle({'kind':'clear','container':None,'anchor':None,
                                  'target_source':'none','target':None,'reason':'No overlay'},obs)
        self.assertIsNone(result)

    def test_optional_sheet_uses_explicit_cancel(self):
        decision,usage=Recovery().handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'node',
             'target':2,'reason':'Optional offer'},sheet_observation())
        self.assertEqual('tap',decision['action'])
        self.assertEqual(2,decision['node'])
        self.assertEqual('recovery',usage['source'])

    def test_generic_ok_is_not_allowed(self):
        decision,_=Recovery().handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'node',
             'target':2,'reason':'Unknown prompt'},sheet_observation('OK'))
        self.assertEqual('blocked',decision['action'])

    def test_target_outside_sheet_is_rejected(self):
        obs=sheet_observation()
        obs['nodes'].append(node(3, None, [10, 100, 400, 220], text='Cancel'))
        decision,_=Recovery().handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'node',
             'target':3,'reason':'Bad grounding'},obs)
        self.assertEqual('blocked',decision['action'])

    def test_address_work_preserves_navigation_reset_marker(self):
        obs=sheet_observation('Work')
        obs['nodes'][1]['text']='Choose your delivery address'
        decision,usage=Recovery().handle(
            {'kind':'address','container':0,'anchor':1,'target_source':'node',
             'target':2,'reason':'Address required'},obs)
        self.assertEqual('tap',decision['action'])
        self.assertEqual('delivery_address_gate',usage['source'])

    def test_recovery_must_be_verified_before_resume(self):
        recovery=Recovery()
        recovery.handle({'kind':'optional','container':0,'anchor':1,'target_source':'node',
                         'target':2,'reason':'Offer'},sheet_observation())
        clear={'observation':1,'png':png(),'ocr':[],
               'nodes':[node(0,None,[0,0,1080,2200],text='Restaurants')]}
        result=recovery.handle({'kind':'clear','container':None,'anchor':None,
                                'target_source':'none','target':None,'reason':'Clear'},clear)
        self.assertIsNone(result)
        self.assertEqual('recovery_verified',recovery.events[-1]['event'])

    def test_second_sheet_is_handled_after_first_disappears(self):
        recovery=Recovery()
        recovery.handle({'kind':'optional','container':0,'anchor':1,'target_source':'node',
                         'target':2,'reason':'First'},sheet_observation())
        second=sheet_observation('Not now')
        second['observation']=1
        second['nodes'][1]['text']='Enable recommendations'
        decision,_=recovery.handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'node',
             'target':2,'reason':'Second'},second)
        self.assertEqual('tap',decision['action'])
        self.assertEqual(2,len([e for e in recovery.events if e['event']=='recovery_attempt']))

    def test_home_card_false_positive_is_ignored(self):
        recovery=Recovery()
        result=recovery.handle(
            {'kind':'optional','container':1,'anchor':2,'target_source':'node',
             'target':2,'reason':'optional'},home_observation())
        self.assertIsNone(result)
        self.assertEqual('false_positive_ignored',recovery.events[-1]['event'])

    def test_visual_close_icon_in_sheet_top_corner(self):
        obs=sheet_observation()
        decision,_=Recovery().handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'vision',
             'target':None,'target_point':[880,556],'reason':'Visible X icon'},obs)
        self.assertEqual('tap',decision['action'])
        self.assertIn('vision_point',decision)

    def test_visual_target_in_sheet_content_is_rejected(self):
        obs=sheet_observation()
        decision,_=Recovery().handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'vision',
             'target':None,'target_point':[500,750],'reason':'Offer CTA'},obs)
        self.assertEqual('tap',decision['action'])
        self.assertGreater(decision['vision_point'][0],900)
        self.assertLess(decision['vision_point'][1],1400)

    def test_fractional_visual_coordinates_are_normalized(self):
        response={
            'done':True,
            'message':{'content':json.dumps({
                'kind':'optional','container':0,'anchor':1,
                'target_source':'vision','target':None,
                'target_point':[0.91,0.48],'reason':'Visible X icon'
            })}
        }
        request=lambda *args,**kwargs: response
        result=assess(request,'local-model','case',sheet_observation(),[],vision=False)
        self.assertEqual([910,480],result['target_point'])

    def test_visual_bbox_is_converted_to_center(self):
        self.assertEqual([910,480],normalize_visual_point([880,450,940,510]))

    def test_visual_point_object_is_normalized(self):
        self.assertEqual([910,480],normalize_visual_point({'x':.91,'y':.48}))

    def test_visual_bbox_string_is_normalized(self):
        self.assertEqual([910,480],normalize_visual_point('[880, 450, 940, 510]'))

    def test_pixel_point_is_normalized_using_screenshot_size(self):
        self.assertEqual([500,504],normalize_visual_point([540,1180],(1080,2340)))

    def test_visual_point_far_from_sheet_is_rejected(self):
        decision,_=Recovery().handle(
            {'kind':'optional','container':0,'anchor':1,'target_source':'vision',
             'target':None,'target_point':[500,100],'reason':'Bad point'},
            sheet_observation())
        self.assertEqual('blocked',decision['action'])

    def test_centered_visual_promotion_without_hierarchy_uses_close_x(self):
        obs={'observation':0,'png':png(945,2048),'ocr':[],'nodes':[]}
        decision,_=Recovery().handle({
            'kind':'optional','container':None,'anchor':None,
            'target_source':'vision','target':None,
            'target_point':[916,308],
            'reason':'Centered promotional overlay with visible X',
        },obs)
        self.assertEqual('tap',decision['action'])
        self.assertGreater(decision['vision_point'][0],800)
        self.assertLess(decision['vision_point'][1],800)

    def test_vision_only_promotion_cannot_tap_bottom_cta(self):
        obs={'observation':0,'png':png(945,2048),'ocr':[],'nodes':[]}
        decision,_=Recovery().handle({
            'kind':'optional','container':None,'anchor':None,
            'target_source':'vision','target':None,
            'target_point':[850,760],
            'reason':'Promotional CTA',
        },obs)
        self.assertEqual('blocked',decision['action'])


if __name__ == '__main__':
    unittest.main()
