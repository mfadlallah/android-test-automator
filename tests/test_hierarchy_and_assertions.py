import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.main import (
    Blocked,
    Device,
    assess_plan_assertion,
    assertion_crop_bounds,
    canonicalize_scoped_contains_result,
    parse_nodes,
    scoped_exact_value_result,
)
from src.adapters.generic_adapter import GenericAdapter


class HierarchyParsingTests(unittest.TestCase):
    @patch('src.main.subprocess.run')
    def test_dump_diagnostics_keep_stderr_on_success_and_failure(self,run):
        device=Device('serial','com.example.app')
        with tempfile.TemporaryDirectory() as temporary:
            log=Path(temporary)/'commands.jsonl'
            run.return_value=subprocess.CompletedProcess([],0,b'',b'ERROR: idle state unavailable')
            self.assertEqual('',device.adb('shell','uiautomator','dump','file.xml',
                diagnostic_path=log,diagnostic_attempt=1))
            run.return_value=subprocess.CompletedProcess([],1,b'partial output',b'dump failed')
            with self.assertRaises(Blocked):
                device.adb('shell','uiautomator','dump','file.xml',
                    diagnostic_path=log,diagnostic_attempt=2)
            records=[json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual('ERROR: idle state unavailable',records[0]['stderr'])
            self.assertEqual(0,records[0]['exit_code'])
            self.assertEqual('partial output',records[1]['stdout'])
            self.assertEqual(1,records[1]['exit_code'])
            self.assertEqual(2,records[1]['attempt'])
            self.assertGreaterEqual(records[1]['duration_seconds'],0)

    @patch('src.main.subprocess.run')
    def test_dump_timeout_keeps_partial_streams_and_is_still_raised(self,run):
        run.side_effect=subprocess.TimeoutExpired(['adb'],35,
            output=b'waiting for root',stderr=b'accessibility timeout')
        with tempfile.TemporaryDirectory() as temporary:
            log=Path(temporary)/'commands.jsonl'
            with self.assertRaises(subprocess.TimeoutExpired):
                Device('serial','com.example.app').adb('shell','uiautomator','dump',
                    diagnostic_path=log)
            record=json.loads(log.read_text())
            self.assertTrue(record['timed_out'])
            self.assertIsNone(record['exit_code'])
            self.assertEqual('waiting for root',record['stdout'])
            self.assertEqual('accessibility timeout',record['stderr'])

    @patch('src.main.time.sleep')
    def test_failed_dump_uses_one_observation_fallback_and_retries_later(
            self,_sleep):
        device=Device('serial','com.example.app')
        calls=[]
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))

        def adb(*args,**kwargs):
            calls.append(args)
            if args[:2]==('exec-out','screencap'):
                return png
            if args[:3]==('shell','ls','-l'):
                raise Blocked('dump file is absent')
            return ''

        device.adb=adb
        with tempfile.TemporaryDirectory() as temporary:
            observation=device.observe(Path(temporary),4)
            self.assertEqual([],observation['nodes'])
            self.assertTrue(observation['hierarchy_unavailable'])
            self.assertTrue((Path(temporary)/'04.png').exists())
            log=(Path(temporary)/'04-dump-log.txt').read_text()
            self.assertIn('bounded retries',log)
        self.assertEqual(3,sum(
            args[:3]==('shell','uiautomator','dump') for args in calls))
        # Cleanup is recovery-only; it must never precede the first dump.
        first_dump=next(index for index,args in enumerate(calls)
                        if args[:3]==('shell','uiautomator','dump'))
        self.assertFalse(any(
            args[:3]==('shell','pkill','-f')
            for args in calls[:first_dump]))

    def test_non_launcher_foreground_package_is_retained(self):
        xml='''<?xml version="1.0" encoding="UTF-8"?>
        <hierarchy>
          <node package="com.external.flow" class="android.widget.FrameLayout"
                bounds="[0,0][1080,2200]">
            <node package="com.external.flow" class="android.widget.TextView"
                  text="Continue" resource-id="com.external.flow:id/continue"
                  clickable="true" enabled="true" bounds="[40,100][500,220]" />
          </node>
        </hierarchy>'''
        nodes=parse_nodes(
            xml,'com.example.launcher',foreground_package='com.external.flow')
        self.assertEqual(2,len(nodes))
        self.assertEqual('com.external.flow',nodes[0]['package'])
        self.assertEqual(0,nodes[1]['parent'])
        self.assertEqual('Continue',nodes[1]['text'])

    def test_unexpected_package_falls_back_to_valid_current_hierarchy(self):
        xml='''<hierarchy>
          <node package="com.partner.activity" class="android.view.View"
                bounds="[0,0][1080,2200]">
            <node package="com.partner.activity" class="android.view.View"
                  text="Partner screen" bounds="[20,50][800,160]" />
          </node>
        </hierarchy>'''
        nodes=parse_nodes(xml,'com.example.launcher')
        self.assertEqual(['com.partner.activity']*2,
                         [node['package'] for node in nodes])
        self.assertEqual(0,nodes[1]['parent'])

    def test_launch_package_wins_over_unrelated_system_nodes(self):
        xml='''<hierarchy>
          <node package="com.example.app" class="android.view.View"
                bounds="[0,0][1080,2200]">
            <node package="com.example.app" text="App content"
                  class="android.widget.TextView" bounds="[20,50][800,160]" />
          </node>
          <node package="com.android.systemui" text="12:00"
                class="android.widget.TextView" bounds="[0,0][100,40]" />
        </hierarchy>'''
        nodes=parse_nodes(xml,'com.example.app')
        self.assertEqual({'com.example.app'},
                         {node['package'] for node in nodes})


class ScopedLabelAssertionTests(unittest.TestCase):
    def test_collection_target_does_not_ground_to_search_label(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'nodes':[],'ocr':[
            {'text':'Search for a Restaurant or Meal','confidence':.99,
             'bounds':[140,330,900,410]},
            {'text':'Filters','confidence':.99,'bounds':[40,850,220,930]},
            {'text':'Cuisines','confidence':.99,'bounds':[250,850,470,930]},
            {'text':'Vendor One','confidence':.99,
             'bounds':[40,1050,400,1130]},
        ]}
        bounds=assertion_crop_bounds(obs,{
            'capability':'assert_visible',
            'target':'refreshed restaurant items','value':'',
        })
        self.assertGreater(bounds[1],930)
        self.assertNotEqual([140,330,900,410],bounds)

    def test_scoped_negative_observation_gets_deterministic_polarity(self):
        step={
            'capability':'assert_not_contains',
            'target':'first product item','value':'Sponsored',
        }
        result=canonicalize_scoped_contains_result(step,{
            'status':'failed',
            'reason':'Sponsored is not present in the image.',
            'evidence':'The text Sponsored is not visible in the image.',
        },[0,900,1080,1450])
        self.assertEqual('passed',result['status'])
        self.assertIn('first product item',result['evidence'])
        self.assertIn('Sponsored',result['evidence'])

    def test_structural_target_does_not_match_single_character_ocr(self):
        adapter=GenericAdapter()
        obs={'ocr':[
            {'text':'M','confidence':.99,'bounds':[220,47,271,78]},
        ],'nodes':[]}
        self.assertIsNone(adapter.ground_target(
            'first restaurant item',obs))

    def test_hierarchy_free_first_item_starts_below_dense_controls(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'nodes':[],'ocr':[
            {'text':'Restaurants','confidence':.99,
             'bounds':[40,650,320,730]},
            {'text':'Filters','confidence':.99,'bounds':[40,850,220,930]},
            {'text':'Cuisines','confidence':.99,'bounds':[250,850,470,930]},
            {'text':'Offers','confidence':.99,'bounds':[500,850,650,930]},
            {'text':'Vendor One','confidence':.99,
             'bounds':[40,1050,400,1130]},
        ]}
        bounds=assertion_crop_bounds(obs,{
            'capability':'assert_contains','target':'first restaurant item',
            'value':'Ad',
        })
        self.assertGreater(bounds[1],930)
        self.assertEqual([0,1080],[bounds[0],bounds[2]])
        self.assertGreater(bounds[3]-bounds[1],500)

    def test_generic_first_item_label_is_scoped_and_resolved(self):
        png=(b'\x89PNG\r\n\x1a\n'+b'\x00'*8+
             struct.pack('>II',1080,2340))
        obs={'png':png,'ocr':[
            {'text':'Ad','confidence':.98,'bounds':[850,940,900,980]},
        ],'nodes':[
            {'node':0,'parent':None,'text':'','description':'',
             'resource_id':'sample:id/content_list',
             'bounds':[0,850,1080,2200],'scrollable':True,
             'enabled':True,'class_name':'androidx.recyclerview.widget.RecyclerView'},
            {'node':1,'parent':0,'text':'','description':'',
             'resource_id':'sample:id/item','bounds':[0,850,1080,1350],
             'scrollable':False,'enabled':True,
             'class_name':'android.view.ViewGroup'},
            {'node':2,'parent':1,'text':'Ad','description':'',
             'resource_id':'sample:id/badge','bounds':[850,940,900,980],
             'scrollable':False,'enabled':True,
             'class_name':'android.widget.TextView'},
        ]}
        positive={
            'capability':'assert_contains','target':'first product item',
            'value':'Ad',
        }
        bounds=assertion_crop_bounds(obs,positive)
        self.assertLessEqual(bounds[0],850)
        self.assertLessEqual(bounds[1],940)
        self.assertGreaterEqual(bounds[2],900)
        self.assertGreaterEqual(bounds[3],980)
        self.assertGreaterEqual(bounds[2]-bounds[0],220)
        self.assertGreaterEqual(bounds[3]-bounds[1],140)
        self.assertEqual(
            'passed',scoped_exact_value_result(obs,positive,bounds)['status'])

        negative=dict(positive,capability='assert_not_contains')
        self.assertEqual(
            'failed',scoped_exact_value_result(obs,negative,bounds)['status'])

    @patch('src.main.read_screen_ocr',return_value=[])
    @patch('src.main.scoped_assertion_image',return_value=(
        b'\x89PNG\r\n\x1a\n'+b'0'*32,[0,100,500,500]))
    @patch('src.main.local_request')
    def test_negative_ocr_miss_requires_visual_verdict(
            self,request,_crop,_ocr):
        request.return_value={
            'done':True,
            'message':{'content':json.dumps({
                'status':'passed',
                'reason':'The first item does not contain Ad.',
                'evidence':'Ad is absent from the visible grounded first item.',
            })},
        }
        step={
            'id':'negative','capability':'assert_not_contains',
            'target':'first item','value':'Ad',
        }
        result=assess_plan_assertion(
            'model',step,{'nodes':[],'ocr':[],'png':b''},vision=True)
        self.assertEqual('passed',result['status'])
        request.assert_called_once()


if __name__ == '__main__':
    unittest.main()
