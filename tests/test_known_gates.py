import base64
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from src.planning import validate_plan

from src.main import (
    assess_plan_assertion,
    assertion_crop_bounds,
    assertion_evidence_error,
    compact_assertion_observation,
    current_home_screen,
    delivery_address_gate,
    fast_offer_probe_after_navigation,
    hour_offer_gate,
    in_app_message_gate,
    ignore_ungrounded_optional_after_back,
    layout_toggle_and_scroll_gate,
    locate_layout_toggle_visual,
    modal_dimming_evidence,
    navigation_gate,
    navigation_retry_from_home,
    needs_sequential_executor,
    observed_scroll_change,
    optional_grounding_back_fallback,
    planned_modal_is_active,
    prior_recovery_dismissal,
    parse_layout_transition,
    plan_completion_error,
    restaurants_modal_back_gate,
    restaurants_ready_for_layout,
    semantic_tap_decision,
    semantic_visible_evidence,
    screenshot_scroll_gate,
    screenshot_only_after_recovery,
    scoped_exact_value_result,
    semantic_target_bounds,
    stabilize_assertion_result,
    step_result_summary,
    unexpected_modal_back_gate,
)


def solid_regions_png(width,height,split,top_rgb,bottom_rgb):
    """Build a small non-interlaced RGB PNG for luminance tests."""
    raw=bytearray()
    for y in range(height):
        raw.append(0)
        color=top_rgb if y<split else bottom_rgb
        raw.extend(bytes(color)*width)
    def chunk(kind,data):
        return (struct.pack('>I',len(data))+kind+data+
                struct.pack('>I',zlib.crc32(kind+data)&0xffffffff))
    ihdr=struct.pack('>IIBBBBB',width,height,8,2,0,0,0)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',ihdr)+
            chunk(b'IDAT',zlib.compress(bytes(raw)))+chunk(b'IEND',b''))


def node(number, text='', resource_id='', parent=None):
    return {'node':number,'parent':parent,'text':text,'description':'',
            'resource_id':resource_id,'bounds':[0,100+number*20,900,180+number*20],
            'clickable':False,'scrollable':False,'enabled':True,
            'class_name':'android.view.View'}


def layout_plan(initial, initial_side, target, target_side):
    return validate_plan({
        'version':1,
        'name':initial+' to '+target,
        'steps':[
            {'id':'open','capability':'tap','role':'action',
             'target':'Restaurants','value':'','position':'none',
             'direction':'none','optional':False,'success':'listing visible'},
            {'id':'recover','capability':'recover_optional','role':'recovery',
             'target':'','value':'','position':'none','direction':'none',
             'optional':True,'success':'foreground clear'},
            {'id':'initial','capability':'set_control','role':'setup',
             'target':'listing layout','value':initial,'position':initial_side,
             'direction':'none','optional':False,'success':'initial state'},
            {'id':'target','capability':'set_control','role':'action',
             'target':'listing layout','value':target,'position':target_side,
             'direction':'none','optional':False,'success':'target state'},
            {'id':'changed','capability':'assert_changed','role':'assertion',
             'target':'restaurant items','value':'','position':'none',
             'direction':'none','optional':False,'success':'layout changed'},
            {'id':'scroll','capability':'scroll','role':'action',
             'target':'restaurant list','value':'','position':'none',
             'direction':'down','optional':False,'success':'list moved'},
            {'id':'scrolled','capability':'assert_scrolled','role':'assertion',
             'target':'restaurant list','value':'','position':'none',
             'direction':'none','optional':False,'success':'content moved'},
        ],
    })


class KnownGateTests(unittest.TestCase):
    def test_address_gate_runs_without_modal_container_grounding(self):
        obs={'nodes':[
            node(0,'Choose your delivery address'),
            node(1,'Work','app:id/address_title'),
        ]}
        decision,usage=delivery_address_gate(obs,[])
        self.assertEqual('tap',decision['action'])
        self.assertEqual(1,decision['node'])
        self.assertEqual('delivery_address_gate',usage['source'])

    def test_listing_open_at_launch_returns_home_once(self):
        obs={'nodes':[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
        ]}
        decision,usage=navigation_gate(lambda *args:None,obs,None,[])
        self.assertEqual('back',decision['action'])
        self.assertEqual('navigation_gate',usage['source'])

    def test_navigation_prefers_visible_label_before_resource_id(self):
        obs={'nodes':[
            node(3,'Restaurants','app:id/unrelated_label'),
            node(8,'','app:id/restaurantsVertical'),
        ]}
        decision,usage=navigation_gate(
            lambda *args:None,obs,None,[],
            target='Restaurants',resource_hints=('restaurantsVertical',))
        self.assertEqual('tap',decision['action'])
        self.assertEqual(3,decision['node'])
        self.assertNotEqual('resource_id_keywords',usage.get('localization'))

    def test_navigation_uses_resource_id_keywords_when_label_is_absent(self):
        obs={'nodes':[
            node(3,'','app:id/address_header'),
            node(8,'','app:id/homeRestaurantsVertical'),
        ]}
        decision,usage=navigation_gate(
            lambda *args:None,obs,None,[],
            target='Restaurants',resource_hints=('restaurantsVertical',))
        self.assertEqual('tap',decision['action'])
        self.assertEqual(8,decision['node'])
        self.assertEqual('resource_id_keywords',usage['localization'])

    def test_listing_after_navigation_scrolls_exact_vendors_recycler(self):
        obs={'nodes':[
            {**node(7,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(19,'','app:id/vendorsRecycler'),'scrollable':True},
            {**node(23,'','app:id/horizontalCarousel'),'scrollable':True},
        ]}
        history=[{
            'decision':{'action':'tap'},
            'usage':{'source':'navigation_gate'},
        }]
        planner=lambda *args: self.fail('planner must not choose the list node')
        decision,usage=navigation_gate(planner,obs,None,history)
        self.assertEqual('scroll',decision['action'])
        self.assertEqual(19,decision['node'])
        self.assertEqual('down',decision['direction'])
        self.assertEqual('navigation_gate',usage['source'])

    def test_listing_passes_after_recycler_content_moves(self):
        before={'nodes':[
            {**node(7,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(19,'Vendor One','app:id/vendorsRecycler'),'scrollable':True},
        ]}
        after={'nodes':[
            {**node(7,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(19,'Vendor Two','app:id/vendorsRecycler'),'scrollable':True},
        ]}
        history=[
            {'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}},
            {'decision':{'action':'scroll'},'usage':{'source':'navigation_gate'}},
        ]
        decision,_=navigation_gate(lambda *args:None,after,before,history)
        self.assertEqual('passed',decision['action'])

    def test_hour_offer_uses_expiry_ocr_and_sheet_geometry(self):
        nodes=[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
            {**node(2,'','app:id/bottom_sheet'),'bounds':[0,1000,1080,2250],
             'class_name':'android.widget.FrameLayout'},
        ]
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        obs={'nodes':nodes,'png':png,'ocr':[
            {'ocr_id':0,'text':'Expires in','confidence':.99,
             'bounds':[380,1230,650,1300]}
        ]}
        decision,usage=hour_offer_gate(obs,[])
        self.assertEqual('tap',decision['action'])
        self.assertEqual('hour_offer_gate',usage['source'])
        self.assertGreater(decision['vision_point'][0],900)
        self.assertLess(decision['vision_point'][1],1200)

    def test_hour_offer_fast_path_works_without_hierarchy(self):
        fake_png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
                  struct.pack('>II',1080,2340))
        obs={'nodes':[],'png':fake_png,'ocr':[
            {'text':'Restaurants','confidence':.99,
             'bounds':[40,600,340,690]},
            {'text':'Filters','confidence':.99,
             'bounds':[40,780,220,850]},
            {'text':'Expires in 31:12','confidence':.99,
             'bounds':[390,1080,690,1160]},
        ]}
        decision,usage=hour_offer_gate(obs,[])
        self.assertEqual('tap',decision['action'])
        self.assertIn('vision_point',decision)
        self.assertEqual('hour_offer_gate',usage['source'])

    def test_fast_offer_probe_only_follows_restaurants_navigation(self):
        next_step={'capability':'recover_optional'}
        navigation=[{
            'decision':{'action':'tap'},
            'usage':{'source':'navigation_gate'},
        }]
        apply_tap=[{
            'decision':{'action':'tap'},
            'usage':{'source':'sequential_executor'},
        }]
        self.assertTrue(fast_offer_probe_after_navigation(
            navigation,next_step))
        self.assertFalse(fast_offer_probe_after_navigation(
            apply_tap,next_step))

    def test_hour_carousel_without_expiry_is_not_a_sheet(self):
        nodes=[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
        ]
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        obs={'nodes':nodes,'png':png,'ocr':[
            {'ocr_id':0,'text':'Offer HOUR','confidence':.99,
             'bounds':[40,300,300,430]}
        ]}
        self.assertIsNone(hour_offer_gate(obs,[]))

    def test_sdk_in_app_message_uses_explicit_close_node(self):
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        nodes=[
            {**node(0,'','app:id/com_braze_inappmessage_modal'),
             'bounds':[40,550,1040,1900],
             'class_name':'android.widget.FrameLayout'},
            {**node(1,'','app:id/com_braze_inappmessage_close_button',0),
             'bounds':[920,580,1010,670]},
        ]
        decision,usage=in_app_message_gate(
            {'nodes':nodes,'png':png,'ocr':[]},[])
        self.assertEqual('tap',decision['action'])
        self.assertEqual(1,decision['node'])
        self.assertEqual('in_app_message_gate',usage['source'])

    def test_sdk_image_modal_uses_safe_top_corner_geometry(self):
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',945,2048)
        nodes=[{
            **node(0,'','app:id/com_braze_inappmessage_modal'),
            'bounds':[19,570,928,1478],
            'class_name':'android.widget.FrameLayout',
        }]
        decision,usage=in_app_message_gate(
            {'nodes':nodes,'png':png,'ocr':[]},[])
        self.assertEqual('tap',decision['action'])
        self.assertGreater(decision['vision_point'][0],800)
        self.assertLess(decision['vision_point'][1],700)
        self.assertEqual('in_app_message_gate',usage['source'])

    def test_normal_centered_card_without_sdk_marker_is_ignored(self):
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',945,2048)
        nodes=[{
            **node(0,'Promotion','app:id/content_card'),
            'bounds':[19,570,928,1478],
            'class_name':'android.widget.FrameLayout',
        }]
        self.assertIsNone(in_app_message_gate(
            {'nodes':nodes,'png':png,'ocr':[]},[]))

    def test_restaurants_bottom_modal_uses_android_back(self):
        nodes=[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
            {**node(2,'','app:id/bottom_sheet'),'bounds':[0,1000,1080,2250],
             'class_name':'android.widget.FrameLayout'},
        ]
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        decision,usage=restaurants_modal_back_gate(
            {'nodes':nodes,'png':png,'ocr':[]},history)
        self.assertEqual('back',decision['action'])
        self.assertEqual('unexpected_modal_back_gate',usage['source'])

    def test_normal_restaurants_content_does_not_trigger_back(self):
        nodes=[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
            {**node(2,'','app:id/content'),'bounds':[0,500,1080,2250],
             'class_name':'android.widget.FrameLayout'},
            {**node(3,'Vendor one','',parent=2),'bounds':[20,700,900,800]},
            {**node(4,'Vendor two','',parent=2),'bounds':[20,900,900,1000]},
        ]
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        self.assertIsNone(restaurants_modal_back_gate(
            {'nodes':nodes,'png':png,'ocr':[]},history))

    def test_dimming_detector_confirms_bright_modal_over_dark_background(self):
        png=solid_regions_png(100,200,100,(90,90,90),(240,240,240))
        evidence=modal_dimming_evidence(png,[0,100,100,200])
        self.assertTrue(evidence['confirmed'])
        self.assertGreater(evidence['foreground_median'],
                           evidence['background_median'])

    def test_dimming_detector_rejects_uniform_screen(self):
        png=solid_regions_png(100,200,100,(230,230,230),(230,230,230))
        evidence=modal_dimming_evidence(png,[0,100,100,200])
        self.assertFalse(evidence['confirmed'])

    def test_weak_bottom_container_requires_confirmed_dimming(self):
        nodes=[
            {**node(0,'Restaurants','app:id/vendors_title'),
             'bounds':[0,10,100,30]},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True,
             'bounds':[0,30,100,190]},
            {**node(2,'','app:id/content',parent=None),
             'bounds':[0,90,100,200],
             'class_name':'android.view.ViewGroup'},
            {**node(3,'Offer',parent=2),'bounds':[5,110,90,130]},
            {**node(4,'Dismiss',parent=2),'bounds':[5,150,90,175]},
        ]
        history=[{
            'decision':{'action':'tap'},
            'usage':{'source':'navigation_gate'},
        }]
        dimmed=solid_regions_png(100,200,90,(90,90,90),(240,240,240))
        clear=solid_regions_png(100,200,90,(230,230,230),(230,230,230))
        decision,usage=restaurants_modal_back_gate(
            {'nodes':nodes,'png':dimmed,'ocr':[]},history)
        self.assertEqual('back',decision['action'])
        self.assertTrue(usage['dimming_evidence']['confirmed'])
        self.assertIsNone(restaurants_modal_back_gate(
            {'nodes':nodes,'png':clear,'ocr':[]},history))

    def test_unplanned_dimmed_sheet_on_home_uses_one_back(self):
        nodes=[
            {**node(0,'Welcome','app:id/welcome_message_headline'),
             'bounds':[0,10,100,30]},
            {**node(1,'','app:id/rating_order_content'),
             'bounds':[0,90,100,200],
             # Real Compose semantics can expose the sheet as a plain View.
             'class_name':'android.view.View'},
            {**node(2,'Rate your order',parent=1),
             'bounds':[5,110,90,135]},
            {**node(3,'Not now',parent=1),'bounds':[5,150,90,175]},
        ]
        png=solid_regions_png(100,200,90,(90,90,90),(240,240,240))
        decision,usage=unexpected_modal_back_gate(
            {'nodes':nodes,'png':png,'ocr':[]},[],{'steps':[]},-1)
        self.assertEqual('back',decision['action'])
        self.assertEqual('unexpected_modal_back_gate',usage['source'])
        self.assertTrue(usage['dimming_evidence']['confirmed'])

        history=[{'decision':decision,'usage':usage}]
        waiting,_=unexpected_modal_back_gate(
            {'nodes':nodes,'png':png,'ocr':[]},history,{'steps':[]},-1)
        self.assertEqual('wait',waiting['action'])
        history.append({
            'decision':waiting,
            'usage':{'source':'unexpected_modal_back_gate'},
        })
        blocked,_=unexpected_modal_back_gate(
            {'nodes':nodes,'png':png,'ocr':[]},history,{'steps':[]},-1)
        self.assertEqual('blocked',blocked['action'])

    def test_explicit_plan_sheet_is_not_dismissed(self):
        nodes=[
            {**node(0,'','app:id/filter_content'),
             'bounds':[0,90,100,200],
             'class_name':'android.view.ViewGroup'},
            {**node(1,'Filters',parent=0),'bounds':[5,110,90,135]},
            {**node(2,'Apply',parent=0),'bounds':[5,150,90,175]},
        ]
        png=solid_regions_png(100,200,90,(90,90,90),(240,240,240))
        plan={'steps':[{
            'id':'filters-visible','capability':'assert_visible',
            'target':'Filters sheet','success':'Filters sheet is visible',
        }]}
        self.assertTrue(planned_modal_is_active(plan,0,[]))
        self.assertIsNone(unexpected_modal_back_gate(
            {'nodes':nodes,'png':png,'ocr':[]},[],plan,0))

    def test_verified_planned_sheet_remains_protected_during_interaction(self):
        visible={
            'id':'visible','capability':'assert_visible','role':'assertion',
            'target':'Filters sheet','success':'Filters sheet is visible',
        }
        plan={'steps':[visible,{
            'id':'rating','capability':'tap','role':'action',
            'target':'Ratings (High To Low)','success':'Rating selected',
        }]}
        history=[{
            'plan_step':visible,
            'decision':{'action':'step_pass'},
            'usage':{'source':'sequential_assertion'},
        }]
        self.assertTrue(planned_modal_is_active(plan,1,history))

    def test_optional_grounding_failure_never_uses_blind_back(self):
        nodes=[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
        ]
        obs={'nodes':nodes}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        result=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history)
        self.assertIsNone(result)
        self.assertTrue(ignore_ungrounded_optional_after_back(
            {'kind':'optional'},blocked,obs,history))

    def test_clear_assessment_never_uses_back_fallback(self):
        obs={'nodes':[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        self.assertIsNone(optional_grounding_back_fallback(
            {'kind':'clear'},None,obs,history))

    def test_ocr_listing_does_not_authorize_blind_back(self):
        obs={
            'nodes':[node(0,'Offer')],
            'ocr':[{'text':'Restaurants','confidence':.99,'bounds':[20,20,300,90]}],
        }
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        result=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history)
        self.assertIsNone(result)

    def test_modal_geometry_alone_does_not_authorize_generic_back(self):
        png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        nodes=[
            {**node(0,'','app:id/bottom_sheet'),'bounds':[0,900,1080,2340],
             'class_name':'android.widget.FrameLayout'},
            {**node(1,'Offer',parent=0),'bounds':[50,1050,600,1150]},
            {**node(2,'Expires in',parent=0),'bounds':[50,1200,600,1300]},
        ]
        obs={'nodes':nodes,'png':png,'ocr':[]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        result=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history)
        self.assertIsNone(result)

    def test_multiple_ungrounded_optional_claims_never_use_back(self):
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        for index,title in enumerate(('Offer One','Not now','Rate your order')):
            obs={'nodes':[],'ocr':[
                {'text':title,'confidence':.99,'bounds':[20,900,800,1000]},
            ]}
            if index==0:
                obs['ocr'].append({
                    'text':'Restaurants','confidence':.99,
                    'bounds':[20,400,500,500],
                })
            result=optional_grounding_back_fallback(
                {'kind':'optional'},blocked,obs,history)
            self.assertIsNone(result)

    def test_same_ungrounded_optional_sheet_is_never_backed(self):
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        obs={'nodes':[],'ocr':[
            {'text':'Expires in 31:12','confidence':.99,'bounds':[20,900,800,1000]},
            {'text':'Restaurants','confidence':.99,'bounds':[20,400,500,500]},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        first=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history)
        obs['ocr'][0]['text']='Expires in 31:11'
        repeated=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history)
        self.assertIsNone(first)
        self.assertIsNone(repeated)

    def test_no_second_back_on_clear_listing_after_sheet_closed(self):
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        first_obs={'nodes':[],'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[20,400,500,500]},
            {'text':'Expires in 31:12','confidence':.99,'bounds':[20,900,800,1000]},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        history.append({
            'plan_step':{'capability':'recover_optional'},
            'decision':{'action':'tap'},
            'usage':{'source':'hour_offer_gate'},
        })
        clear_listing={'nodes':[],'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[20,400,500,500]},
            {'text':'Filters','confidence':.99,'bounds':[20,700,300,800]},
            {'text':'Vendor One','confidence':.99,'bounds':[20,1000,600,1100]},
        ]}
        result=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,clear_listing,history)
        self.assertIsNone(result)
        self.assertTrue(ignore_ungrounded_optional_after_back(
            {'kind':'optional'},blocked,clear_listing,history))

    def test_unknown_screen_after_recovery_blocks_instead_of_back(self):
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        obs={'nodes':[],'ocr':[
            {'text':'Destination content','confidence':.99,
             'bounds':[20,400,500,500]},
        ]}
        history=[{
            'plan_step':{'capability':'recover_optional'},
            'decision':{'action':'tap'},
            'usage':{'source':'recovery'},
        }]
        self.assertTrue(prior_recovery_dismissal(history))
        self.assertIsNone(optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history))
        self.assertFalse(ignore_ungrounded_optional_after_back(
            {'kind':'optional'},blocked,obs,history))

    def test_grounded_second_recovery_action_is_not_suppressed(self):
        grounded=({
            'action':'tap','node':12,'direction':'none',
            'reason':'Tap explicit close target','evidence':'Close',
        },{'source':'recovery'})
        history=[{
            'plan_step':{'capability':'recover_optional'},
            'decision':{'action':'tap'},
            'usage':{'source':'recovery'},
        }]
        self.assertIsNone(optional_grounding_back_fallback(
            {'kind':'optional'},grounded,{'nodes':[]},history))
        self.assertFalse(ignore_ungrounded_optional_after_back(
            {'kind':'optional'},grounded,{'nodes':[]},history))

    def test_intercepted_layout_tap_never_authorizes_ungrounded_second_back(self):
        blocked=({
            'action':'blocked','node':None,'direction':'none',
            'reason':'Cannot ground the interruption container and heading',
            'evidence':'Cannot ground the interruption container and heading',
        },{'source':'recovery'})
        obs={'nodes':[],'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[20,400,500,500]},
            {'text':'Filters','confidence':.99,'bounds':[20,700,300,800]},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        history.append({
            'decision':{'action':'tap'},
            'usage':{'source':'layout_precondition_setup'},
        })
        followup=optional_grounding_back_fallback(
            {'kind':'optional'},blocked,obs,history)
        self.assertIsNone(followup)

    def test_history_context_cannot_authorize_layout_tap_on_home(self):
        obs={'nodes':[],'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[20,1000,500,1100]},
            {'text':'What would you like to order?','confidence':.99,
             'bounds':[20,700,900,800]},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        self.assertFalse(restaurants_ready_for_layout(
            obs,history,screenshot_context=True))

    def test_listing_ocr_can_authorize_layout_without_hierarchy(self):
        obs={'nodes':[],'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[20,500,500,600]},
            {'text':'Filters','confidence':.99,'bounds':[20,700,300,800]},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        self.assertTrue(restaurants_ready_for_layout(
            obs,history,screenshot_context=True))

    def test_screenshot_fallback_scrolls_then_verifies_ocr_movement(self):
        before={'ocr':[
            {'text':'Vendor One','confidence':.99,'bounds':[20,800,300,870]},
            {'text':'Vendor Two','confidence':.99,'bounds':[20,1100,300,1170]},
        ]}
        first,_=screenshot_scroll_gate(before,None,[])
        self.assertEqual('screen_scroll',first['action'])
        history=[{'decision':first,'usage':{'source':'screenshot_scroll_fallback'}}]
        after={'ocr':[
            {'text':'Vendor One','confidence':.99,'bounds':[20,500,300,570]},
            {'text':'Vendor Two','confidence':.99,'bounds':[20,800,300,870]},
        ]}
        verified,_=screenshot_scroll_gate(after,before,history)
        self.assertEqual('passed',verified['action'])

    def test_observed_scroll_change_uses_ocr_movement(self):
        before={'ocr':[{'text':'Vendor One','confidence':.99,
                        'bounds':[20,900,300,980]}]}
        after={'ocr':[{'text':'Vendor One','confidence':.99,
                       'bounds':[20,500,300,580]}]}
        changed,evidence=observed_scroll_change(before,after)
        self.assertTrue(changed)
        self.assertIn('Vendor One'.casefold(),evidence.casefold())

    def test_extended_assertion_selects_sequential_executor(self):
        plan=layout_plan('card','left','row','right')
        plan['steps'].append({
            'id':'ad','capability':'assert_not_contains','role':'assertion',
            'target':'first restaurant item','hints':[],'value':'Ad',
            'position':'none','direction':'none','optional':False,
            'success':'Ad absent',
        })
        self.assertTrue(needs_sequential_executor(plan))

    def test_close_tap_reprobes_full_hierarchy(self):
        history=[{
            'plan_step':{'capability':'recover_optional'},
            'decision':{'action':'tap'},
        }]
        self.assertFalse(screenshot_only_after_recovery(history,None))

    def test_hierarchy_miss_is_reprobed_on_next_observation(self):
        previous={'hierarchy_unavailable':True}
        history=[{
            'plan_step':{'capability':'assert_visible'},
            'decision':{'action':'wait'},
        }]
        self.assertFalse(screenshot_only_after_recovery(history,previous))

    def test_normal_tap_does_not_enable_screenshot_only_observation(self):
        history=[{
            'plan_step':{'capability':'tap'},
            'decision':{'action':'tap'},
        }]
        self.assertFalse(screenshot_only_after_recovery(history,None))

    def test_content_tap_reprobes_hierarchy_before_assertion(self):
        history=[{
            'plan_step':{'capability':'tap','target':'Apply'},
            'decision':{'action':'tap'},
            'usage':{'source':'sequential_executor'},
        }]
        next_step={
            'capability':'assert_contains','target':'Filters pill','value':'1',
        }
        self.assertFalse(screenshot_only_after_recovery(
            history,None,next_step))

    def test_next_semantic_tap_still_reprobes_hierarchy(self):
        history=[{
            'plan_step':{'capability':'tap','target':'Filters'},
            'decision':{'action':'tap'},
            'usage':{'source':'sequential_executor'},
        }]
        next_step={'capability':'tap','target':'Ratings (High To Low)'}
        self.assertFalse(screenshot_only_after_recovery(
            history,None,next_step))

    def test_semantic_tap_uses_exact_ocr_when_hierarchy_is_missing(self):
        fake_png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
                  struct.pack('>II',1080,2340))
        obs={'nodes':[],'png':fake_png,'ocr':[
            {'text':'Filters','confidence':.99,
             'bounds':[40,800,230,880]},
        ]}
        decision,usage=semantic_tap_decision(obs,'Filters')
        self.assertEqual('tap',decision['action'])
        self.assertEqual('apple_vision_ocr',usage['localization'])

    def test_semantic_tap_refuses_ambiguous_ocr(self):
        fake_png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
                  struct.pack('>II',1080,2340))
        obs={'nodes':[],'png':fake_png,'ocr':[
            {'text':'Filters','confidence':.99,
             'bounds':[40,800,230,880]},
            {'text':'Filters','confidence':.98,
             'bounds':[300,800,500,880]},
        ]}
        with self.assertRaisesRegex(Exception,'found 2'):
            semantic_tap_decision(obs,'Filters')

    def test_assertion_rejects_unrelated_home_screen_evidence(self):
        step={'capability':'assert_visible','target':'Filters pill','value':''}
        result={
            'status':'passed',
            'reason':'User can place an order.',
            'evidence':'The Home welcome message is visible.',
        }
        self.assertIsNotNone(assertion_evidence_error(step,result))

    def test_assertion_accepts_target_aligned_evidence(self):
        step={'capability':'assert_visible','target':'Filters pill','value':''}
        result={
            'status':'passed',
            'reason':'Filters is visible.',
            'evidence':'The Filters pill appears above the restaurant list.',
        }
        self.assertIsNone(assertion_evidence_error(step,result))

    def test_visible_assertion_uses_ocr_without_ai(self):
        obs={'nodes':[],'ocr':[
            {'text':'Filters','confidence':.99,'bounds':[20,400,200,470]},
        ]}
        self.assertIn('OCR',semantic_visible_evidence(obs,'Filters pill'))

    @patch('src.main.local_request')
    def test_assertion_sends_only_current_image(self,request):
        request.return_value={
            'done':True,
            'message':{'content':json.dumps({
                'status':'passed','reason':'Filters is visible.',
                'evidence':'Filters pill is visible.',
            })},
        }
        png=b'current-image'
        before={'nodes':[],'ocr':[{'text':'Before'}],'png':b'before-image'}
        current={'nodes':[],'ocr':[{'text':'Filters'}],'png':png}
        step={'capability':'assert_visible','target':'Filters pill','value':''}
        assess_plan_assertion('model',step,current,before,True,30)
        messages=request.call_args.args[1]['messages']
        image_messages=[message for message in messages if 'images' in message]
        self.assertEqual(1,len(image_messages))
        self.assertEqual(
            [base64.b64encode(png).decode()],image_messages[0]['images'])
        self.assertFalse(any(
            message.get('content','').startswith('BEFORE')
            for message in messages))

    @patch('src.main.local_request')
    def test_assertion_repairs_unrelated_pass_evidence_once(self,request):
        request.side_effect=[
            {
                'done':True,
                'message':{'content':json.dumps({
                    'status':'passed','reason':'First card is visible.',
                    'evidence':'A restaurant card is displayed.',
                })},
            },
            {
                'done':True,
                'message':{'content':json.dumps({
                    'status':'passed','reason':'Ad is visible.',
                    'evidence':'The exact Ad badge appears inside the first '
                               'restaurant item.',
                })},
            },
        ]
        current={'nodes':[],'ocr':[],'png':b'current-image'}
        step={
            'capability':'assert_contains','target':'first restaurant item',
            'value':'Ad',
        }
        result=assess_plan_assertion('model',step,current,None,True,30)
        self.assertEqual('passed',result['status'])
        self.assertEqual(2,request.call_count)
        retry_messages=request.call_args.args[1]['messages']
        self.assertIn('low-contrast',retry_messages[-1]['content'])

    @patch('src.main.scoped_assertion_image')
    @patch('src.main.local_request')
    def test_scoped_assertion_persists_crop_and_retry_metadata(
            self,request,crop):
        crop.return_value=(b'cropped-png',[10,20,300,500])
        request.side_effect=[
            {
                'done':True,
                'message':{'content':json.dumps({
                    'status':'passed','reason':'Item is visible.',
                    'evidence':'A restaurant item is displayed.',
                })},
            },
            {
                'done':True,
                'message':{'content':json.dumps({
                    'status':'passed','reason':'Ad is visible.',
                    'evidence':'The exact Ad label is inside the first '
                               'restaurant item.',
                })},
            },
        ]
        current={
            'observation':4,'nodes':[],'ocr':[],'png':b'full-screen',
        }
        step={
            'id':'4','capability':'assert_contains',
            'target':'first restaurant item','value':'Ad',
        }
        with tempfile.TemporaryDirectory() as temp:
            result=assess_plan_assertion(
                'model',step,current,None,True,30,Path(temp))
            image=Path(temp)/'04-assertion-step-4-crop.png'
            metadata=Path(temp)/'04-assertion-step-4-crop.json'
            self.assertEqual(b'cropped-png',image.read_bytes())
            record=json.loads(metadata.read_text(encoding='utf-8'))
        self.assertEqual('passed',result['status'])
        self.assertEqual([10,20,300,500],record['crop_bounds'])
        self.assertEqual(2,record['attempts'])
        self.assertTrue(record['retried'])
        self.assertEqual('Ad',record['expected_value'])
        self.assertEqual('passed',record['final_status'])
        self.assertEqual(1,len(record['validation_errors']))

    def test_contains_assertion_requires_expected_value_in_evidence(self):
        step={
            'capability':'assert_contains','target':'first restaurant item',
            'value':'Ad',
        }
        unrelated={
            'status':'passed','reason':'First item is visible.',
            'evidence':'A restaurant card is displayed.',
        }
        aligned={
            'status':'passed','reason':'First item contains Ad.',
            'evidence':'The exact Ad label is inside the first restaurant card.',
        }
        self.assertIsNotNone(assertion_evidence_error(step,unrelated))
        self.assertIsNone(assertion_evidence_error(step,aligned))

    def test_positive_contains_rejects_negative_pass_wording(self):
        step={
            'capability':'assert_contains','target':'first restaurant item',
            'value':'Ad',
        }
        negative={
            'status':'passed',
            'reason':'The ad is not present in the first restaurant item.',
            'evidence':'The first restaurant item does not contain Ad.',
        }
        error=assertion_evidence_error(step,negative)
        self.assertIn('negative evidence',error)

    def test_negative_contains_requires_explicit_absence(self):
        step={
            'capability':'assert_not_contains',
            'target':'first restaurant item','value':'Ad',
        }
        positive={
            'status':'passed','reason':'First restaurant item inspected.',
            'evidence':'Ad is visible in the first restaurant item.',
        }
        negative={
            'status':'passed','reason':'First restaurant item inspected.',
            'evidence':'Ad is not present in the first restaurant item.',
        }
        self.assertIsNotNone(assertion_evidence_error(step,positive))
        self.assertIsNone(assertion_evidence_error(step,negative))

    def test_negative_contains_rejects_failed_absence_polarity(self):
        step={
            'capability':'assert_not_contains',
            'target':'first restaurant item','value':'Ad',
        }
        inverted={
            'status':'failed',
            'reason':"The expected value 'Ad' is not present.",
            'evidence':'Ad is not visible in the first restaurant item.',
        }
        error=assertion_evidence_error(step,inverted)
        self.assertIn('treated proven absence as failure',error)

    def test_negative_contains_accepts_failed_observed_presence(self):
        step={
            'capability':'assert_not_contains',
            'target':'first restaurant item','value':'Ad',
        }
        contradiction={
            'status':'failed',
            'reason':'The first restaurant item contains Ad.',
            'evidence':'The exact Ad badge is visible in the first item.',
        }
        self.assertIsNone(assertion_evidence_error(step,contradiction))

    def test_hidden_assertion_rejects_visible_not_hidden_pass(self):
        step={
            'capability':'assert_hidden','target':'Filters sheet','value':'',
        }
        contradiction={
            'status':'passed',
            'reason':'The Filters sheet is visible and not hidden.',
            'evidence':'Filters sheet remains open.',
        }
        valid={
            'status':'passed',
            'reason':'The Filters sheet is closed.',
            'evidence':'Filters sheet is no longer visible.',
        }
        self.assertIsNotNone(assertion_evidence_error(step,contradiction))
        self.assertIsNone(assertion_evidence_error(step,valid))

    def test_wait_changed_requires_before_current_change_evidence(self):
        step={
            'capability':'wait_changed','target':'product items','value':'',
        }
        visible_only={
            'status':'passed','reason':'Product items are visible.',
            'evidence':'The first product item is displayed.',
        }
        changed={
            'status':'passed','reason':'Product items refreshed.',
            'evidence':'CURRENT contains new items compared with BEFORE.',
        }
        self.assertIsNotNone(assertion_evidence_error(step,visible_only))
        self.assertIsNone(assertion_evidence_error(step,changed))

    def test_step_report_records_assertions_and_rejects_missing_steps(self):
        plan={'steps':[
            {'id':'open','capability':'tap','role':'action','target':'Catalog',
             'value':'','optional':False},
            {'id':'present','capability':'assert_contains','role':'assertion',
             'target':'first product item','value':'Sponsored',
             'optional':False},
            {'id':'absent','capability':'assert_not_contains',
             'role':'assertion','target':'first product item',
             'value':'Sponsored','optional':False},
        ]}
        history=[
            {'observation':0,'plan_step':plan['steps'][0],
             'step_completed':True,
             'decision':{'action':'tap','reason':'Open Catalog.',
                         'evidence':'Catalog label grounded.'},
             'usage':{'source':'navigation'}},
            {'observation':1,'plan_step':plan['steps'][1],
             'step_completed':True,
             'decision':{'action':'step_pass',
                         'reason':'first product item contains Sponsored.',
                         'evidence':'Sponsored is visible in the first product item.'},
             'usage':{'source':'assertion'}},
        ]
        summary=step_result_summary(plan,history)
        self.assertEqual(2,summary['steps_passed'])
        self.assertEqual(1,summary['assertions_passed'])
        self.assertIn('contains Sponsored',summary['key_assertions'][0])
        self.assertIn('absent',plan_completion_error(plan,history))

        history.append({
            'observation':2,'plan_step':plan['steps'][2],
            'step_completed':True,
            'decision':{'action':'step_pass',
                        'reason':'first product item does not contain Sponsored.',
                        'evidence':'Sponsored is absent from the first product item.'},
            'usage':{'source':'assertion'},
        })
        self.assertIsNone(plan_completion_error(plan,history))

    def test_exact_scoped_ocr_passes_positive_contains_without_ai(self):
        step={
            'capability':'assert_contains','target':'first restaurant item',
            'value':'Ad',
        }
        obs={'nodes':[],'ocr':[
            {'text':'Ad','confidence':.99,'bounds':[30,120,70,150]},
        ]}
        result=scoped_exact_value_result(obs,step,[0,100,500,500])
        self.assertEqual('passed',result['status'])
        self.assertIsNone(assertion_evidence_error(step,result))

    def test_first_item_crop_prefers_direct_recycler_child(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'ocr':[],'nodes':[
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True,
             'bounds':[0,900,1080,2205]},
            {**node(2,'',parent=1),'bounds':[0,900,1080,1500],
             'class_name':'android.widget.RelativeLayout'},
            {**node(3,'',parent=1),'bounds':[0,1500,1080,2100],
             'class_name':'android.widget.RelativeLayout'},
        ]}
        self.assertEqual(
            [0,900,1080,1500],
            assertion_crop_bounds(obs,{
                'target':'first restaurant item',
                'capability':'assert_contains',
            }))

    def test_labelled_target_crop_includes_adjacent_indicator(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'ocr':[],'nodes':[
            {**node(1,'Filters','app:id/filters'),
             'bounds':[40,700,210,780]},
            {**node(2,'1','app:id/filter_count'),
             'bounds':[215,710,250,750]},
        ]}
        bounds=semantic_target_bounds(obs,'Filters pill')
        self.assertLessEqual(bounds[0],40)
        self.assertGreaterEqual(bounds[2],250)
        result=scoped_exact_value_result(
            obs,{
                'capability':'assert_contains','target':'Filters pill',
                'value':'1',
            },bounds)
        self.assertEqual('passed',result['status'])

    def test_combined_ocr_label_and_badge_ground_target_crop(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'nodes':[],'ocr':[
            {'text':'Filters 1','confidence':.99,
             'bounds':[45,760,310,840]},
        ]}
        bounds=semantic_target_bounds(obs,'Filters pill')
        self.assertIsNotNone(bounds)
        result=scoped_exact_value_result(
            obs,{
                'capability':'assert_contains','target':'Filters pill',
                'value':'1',
            },bounds)
        self.assertEqual('passed',result['status'])

    def test_failed_assertion_is_reobserved_three_times(self):
        step={'id':'count','capability':'assert_contains',
              'target':'Filters pill','value':'1'}
        failed={'status':'failed','reason':'Not visible',
                'evidence':'Filters was temporarily absent.'}
        first=stabilize_assertion_result(step,failed,0,3)
        second=stabilize_assertion_result(step,failed,1,3)
        third=stabilize_assertion_result(step,failed,2,3)
        self.assertEqual('wait',first['status'])
        self.assertEqual('wait',second['status'])
        self.assertEqual('failed',third['status'])

    def test_first_item_assertion_gets_scoped_list_crop(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'ocr':[
            {'text':'Filters','confidence':.99,'bounds':[40,700,250,790]},
        ],'nodes':[]}
        bounds=assertion_crop_bounds(obs,{
            'target':'first restaurant item','capability':'assert_contains',
        })
        self.assertEqual(0,bounds[0])
        self.assertEqual(800,bounds[1])
        self.assertEqual(1080,bounds[2])
        self.assertGreater(bounds[3],1700)

    def test_visible_label_assertion_gets_target_crop(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        bounds=assertion_crop_bounds(
            {'png':png,'ocr':[], 'nodes':[
                {**node(1,'Filters','app:id/filters'),
                 'bounds':[40,700,210,780]},
            ]},
            {'target':'Filters pill','capability':'assert_visible'})
        self.assertIsNotNone(bounds)
        self.assertLessEqual(bounds[0],40)
        self.assertGreaterEqual(bounds[2],210)

    def test_unmatched_label_assertion_keeps_full_image(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        self.assertIsNone(assertion_crop_bounds(
            {'png':png,'ocr':[],'nodes':[]},
            {'target':'Filters pill','capability':'assert_visible'}))

    def test_assertion_context_is_scoped_and_bounded(self):
        nodes=[]
        ocr=[]
        for index in range(150):
            inside=index<100
            top=900+index if inside else 100
            nodes.append({
                'node':index,'parent':None,'text':('Ad' if index==3 else ''),
                'description':'','resource_id':f'app:id/vendor_{index}',
                'bounds':[10,top,1000,top+40],
                'clickable':False,'scrollable':False,'enabled':True,
                'selected':False,'checked':False,
            })
            ocr.append({
                'text':f'row {index}','confidence':.9,
                'bounds':[10,top,300,top+30],
            })
        compact=compact_assertion_observation(
            {'nodes':nodes,'ocr':ocr},
            {'target':'first restaurant item','value':'Ad'},
            [0,800,1080,1500])
        self.assertLessEqual(len(compact['nodes']),80)
        self.assertLessEqual(len(compact['ocr']),60)
        self.assertTrue(any(row.get('text')=='Ad'
                            for row in compact['nodes']))
        self.assertGreater(compact['omitted_counts']['nodes'],0)

    @patch('src.main.local_request')
    def test_assertion_uses_safe_local_context_size(self,request):
        request.return_value={
            'done':True,
            'message':{'content':json.dumps({
                'status':'passed','reason':'Filters is visible.',
                'evidence':'Filters pill is visible.',
            })},
        }
        assess_plan_assertion(
            'model',{'capability':'assert_visible','target':'Filters pill'},
            {'nodes':[],'ocr':[],'png':b'image'},None,True,30)
        payload=request.call_args.args[1]
        self.assertEqual(16384,payload['options']['num_ctx'])

    def test_semantic_tap_strips_view_type_suffix(self):
        obs={'nodes':[node(4,'Filters','app:id/filters')], 'ocr':[]}
        decision,usage=semantic_tap_decision(obs,'Filters pill')
        self.assertEqual('tap',decision['action'])
        self.assertEqual(4,decision['node'])
        self.assertEqual('hierarchy_text',usage['localization'])

    def test_restaurants_path_is_ready_for_layout_after_navigation(self):
        obs={'nodes':[
            {**node(0,'Restaurants','app:id/vendors_title'),'scrollable':False},
            {**node(1,'','app:id/vendorsRecycler'),'scrollable':True},
        ]}
        history=[{'decision':{'action':'tap'},'usage':{'source':'navigation_gate'}}]
        self.assertTrue(restaurants_ready_for_layout(obs,history))

    def test_home_screen_is_grounded_from_current_hierarchy(self):
        obs={'nodes':[
            node(1,'Welcome','app:id/welcome_message_headline'),
        ],'ocr':[]}
        self.assertTrue(current_home_screen(obs))

    def test_recovery_retries_restaurants_once_after_back_returns_home(self):
        obs={'nodes':[
            node(1,'Welcome','app:id/welcome_message_headline'),
        ],'ocr':[]}
        one_tap=[{
            'decision':{'action':'tap'},
            'usage':{'source':'navigation_gate'},
        }]
        two_taps=one_tap+[{
            'decision':{'action':'tap'},
            'usage':{'source':'navigation_gate'},
        }]
        self.assertTrue(navigation_retry_from_home(obs,one_tap))
        self.assertFalse(navigation_retry_from_home(obs,two_taps))

    def test_restaurants_screen_is_not_misclassified_as_home(self):
        obs={'nodes':[
            node(1,'Restaurants','app:id/vendors_title'),
            {**node(2,'','app:id/vendorsRecycler'),'scrollable':True},
        ],'ocr':[]}
        self.assertFalse(current_home_screen(obs))
        self.assertFalse(navigation_retry_from_home(obs,[]))

    def test_verified_layout_change_triggers_scroll(self):
        baseline={'image_size':[1080,2340],'rows':[
            {'text':'vendor one','x':200,'y':1200},
            {'text':'vendor two','x':200,'y':1600},
        ]}
        history=[{
            'decision':{'action':'tap'},
            'usage':{'source':'layout_toggle_gate','baseline':baseline},
        }]
        fake_png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        obs={'png':fake_png,'ocr':[
            {'text':'Vendor One','confidence':.99,'bounds':[500,900,700,1000]},
            {'text':'Vendor Two','confidence':.99,'bounds':[500,1300,700,1400]},
        ]}
        decision,usage=layout_toggle_and_scroll_gate(
            obs,history,layout_plan('card','left','row','right'))
        self.assertEqual('screen_scroll',decision['action'])
        self.assertEqual('layout_toggle_verified',usage['source'])

    def test_layout_target_uses_heading_without_selected_state_inference(self):
        fake_png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        obs={'png':fake_png,'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[40,700,320,780]},
            {'text':'Filters','confidence':.99,'bounds':[40,850,240,920]},
            {'text':'Vendor One','confidence':.99,'bounds':[80,1100,500,1200]},
        ]}
        decision,_=locate_layout_toggle_visual(
            obs,layout_plan('card','left','row','right'))
        self.assertEqual('tap',decision['action'])
        self.assertEqual([983,740],decision['vision_point'])

    def test_two_layout_cases_have_opposite_transitions(self):
        card_to_row=parse_layout_transition(
            layout_plan('card','left','row','right'))
        row_to_card=parse_layout_transition(
            layout_plan('row','right','card','left'))
        self.assertEqual(('left','right'),(
            card_to_row['initial_side'],card_to_row['target_side']))
        self.assertEqual(('right','left'),(
            row_to_card['initial_side'],row_to_card['target_side']))

    def test_initial_layout_is_established_idempotently(self):
        fake_png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        obs={'png':fake_png,'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[40,700,320,780]},
            {'text':'Filters','confidence':.99,'bounds':[40,850,240,920]},
        ]}
        decision,usage=locate_layout_toggle_visual(
            obs,layout_plan('card','left','row','right'),setup=True)
        self.assertEqual('tap',decision['action'])
        self.assertEqual([896,740],decision['vision_point'])
        self.assertEqual('layout_precondition_setup',usage['source'])

    def test_setup_settles_before_target_transition(self):
        fake_png=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+struct.pack('>II',1080,2340)
        obs={'png':fake_png,'ocr':[
            {'text':'Restaurants','confidence':.99,'bounds':[40,700,320,780]},
            {'text':'Filters','confidence':.99,'bounds':[40,850,240,920]},
        ]}
        plan=layout_plan('card','left','row','right')
        setup,setup_usage=layout_toggle_and_scroll_gate(obs,[],plan)
        self.assertEqual('tap',setup['action'])
        self.assertEqual([896,740],setup['vision_point'])
        history=[{'decision':setup,'usage':setup_usage}]
        waiting,wait_usage=layout_toggle_and_scroll_gate(obs,history,plan)
        self.assertEqual('wait',waiting['action'])
        history.append({'decision':waiting,'usage':wait_usage})
        target,target_usage=layout_toggle_and_scroll_gate(obs,history,plan)
        self.assertEqual('tap',target['action'])
        self.assertEqual([983,740],target['vision_point'])
        self.assertEqual('layout_toggle_gate',target_usage['source'])


if __name__ == '__main__':
    unittest.main()
