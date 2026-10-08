import json
import struct
import unittest
from unittest.mock import patch

from src.main import (
    assess_plan_assertion,
    assertion_crop_bounds,
    parse_nodes,
    scoped_exact_value_result,
)


class HierarchyParsingTests(unittest.TestCase):
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
