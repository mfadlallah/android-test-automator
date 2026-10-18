import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from src.collections import resolve_collection, capture_item_text, CollectionError
from src.runtime_values import validate_bindings, resolve_value, captured_destination_result
from src.planning import (compile_controlled_case, canonicalize_model_plan,
                          validate_plan, validate_executable_plan, validate_source_actions, compile_case, PlanError)
from tests.test_collections import scene, node
from src.main import run_sequential_plan, plan_completion_error


class RuntimeValuesTests(unittest.TestCase):
    def test_actual_fallback_path_normalizes_scroll_proof(self):
        text='Title: Test\nSteps:\n1. Tap Catalog.\n2. Scroll left within recommendations.\n3. Tap Details.\nExpected result: content moved'
        def invalid_planner(*args):
            return {'done':True,'done_reason':'stop','message':{'content':'{}'}}
        plan=compile_case(invalid_planner,'local',text)
        self.assertEqual(plan['plan_source'],'controlled_fallback')
        self.assertTrue(plan['normalization_applied'])
        caps=[s['capability'] for s in plan['steps']]
        index=caps.index('scroll')
        self.assertEqual(caps[index+1:index+3],['assert_scrolled','tap'])

    def test_late_scroll_assertion_is_rejected(self):
        text='Title: Test\nSteps:\n1. Tap Catalog.\n2. Scroll left within recommendations.\n3. Tap Details.\nExpected result: content moved'
        raw=validate_plan(compile_controlled_case(text))
        with self.assertRaises(PlanError): validate_executable_plan(raw)
    def test_bounded_search_executes_only_parent_swipes(self):
        from tests.test_collections import step
        search=step(1,'scroll_until_visible','horizontal_scroll','down')
        search['value']='results'
        plan={'steps':[search]}
        class Device:
            calls=[]
            def observe(self,folder,index,*args):
                obs=scene()
                if index<2:
                    obs['nodes']=[n for n in obs['nodes'] if n['node']<6]
                obs.update(observation=index,png=b'')
                return obs
            def execute(self,decision,obs):
                self.calls.append((decision['node'],decision['direction']))
        device=Device()
        with tempfile.TemporaryDirectory() as folder, patch('src.main.read_screen_ocr',return_value=[]), patch('src.main.in_app_message_gate',return_value=None), patch('src.main.unexpected_modal_back_gate',return_value=None):
            status,_,history,_=run_sequential_plan(device,Path(folder),plan,None,None)
        self.assertEqual(status,'PASSED')
        self.assertEqual(device.calls,[(1,'down'),(1,'down')])
        self.assertEqual(sum(r['step_completed'] for r in history),1)

    def test_recorded_resolved_reference_passes_completion_guard(self):
        from tests.test_collections import step
        s=step(1,'assert_contains','name');s['value']='$title'
        executed={**s,'value':'Gamma'}
        result=captured_destination_result(s,{'nodes':[node(99,None,[0,0,300,100],resource_id='p:id/name',text='Gamma')]},{'text':'Gamma','scope':{}})
        history=[{'step_completed':True,'plan_step':executed,'decision':{'action':'step_pass',**result},'observation':0}]
        self.assertIsNone(plan_completion_error({'steps':[s]},history))
    def test_exact_id_wins_over_other_horizontal_containers(self):
        obs=scene()
        obs['nodes'] += [node(20,None,[0,0,1000,200],scrollable=True,resource_id='p:id/horizontal_promotions'),
                         node(21,20,[0,0,300,200],clickable=True),node(22,20,[300,0,600,200],clickable=True)]
        self.assertEqual(resolve_collection('horizontal_scroll',obs,direction='left')['node'],6)
        with self.assertRaises(CollectionError): resolve_collection('horizontal collection',obs,direction='left')
        obs['nodes']=[n for n in obs['nodes'] if n['node'] not in range(6,13)]
        with self.assertRaises(CollectionError): resolve_collection('horizontal_scroll',obs,direction='left')

    def test_capture_scoped_field_and_destination(self):
        obs=scene()
        text,scope=capture_item_text('third visible item of horizontal_scroll',obs,['horizontal_scroll','name'])
        self.assertEqual(text,'Gamma')
        capture={'text':text,'scope':scope}
        step={'target':'name','hints':['name']}
        self.assertEqual(captured_destination_result(step,obs,capture)['status'],'blocked')
        destination={'nodes':[node(99,None,[0,100,900,200],resource_id='p:id/name',text='Gamma')]}
        self.assertEqual(captured_destination_result(step,destination,capture)['status'],'passed')
        destination['nodes'][0]['text']='Gamma Plus'
        self.assertEqual(captured_destination_result(step,destination,capture)['status'],'failed')

    def test_bindings_require_prior_capture(self):
        with self.assertRaises(ValueError): resolve_value('$title',{})
        with self.assertRaises(ValueError): validate_bindings([{'capability':'assert_contains','value':'$title'}])
        validate_bindings([{'capability':'capture_text','value':'title'}, {'capability':'assert_contains','value':'$title'}])

    def test_case_compiles_and_preserves_tap_capture_search(self):
        text=Path('cases/33618525-open-swimlanes-in-list.txt').read_text()
        plan=validate_executable_plan(validate_plan(canonicalize_model_plan(compile_controlled_case(text))))
        validate_source_actions(text,plan)
        self.assertEqual([s['capability'] for s in plan['steps']],['tap','recover_optional','scroll_until_visible','assert_visible','seek_item','capture_text','tap','assert_visible','assert_contains'])
        self.assertEqual(plan['steps'][4]['hints'],['horizontal_scroll','vendor_name'])
        plan['steps'][6]['capability']='assert_visible'
        with self.assertRaises(PlanError): validate_source_actions(text,plan)

    def test_old_placeholder_plan_is_rejected(self):
        plan={'steps':[{'capability':'tap','target':'Third visible item','value':''},
                       {'capability':'assert_contains','target':'menu','value':'third item title'}]}
        with self.assertRaises(PlanError): validate_source_actions('Steps:\n1. Tap Third visible item.\nExpected result:',plan)

class ScreenCapturedValueTests(unittest.TestCase):
    def setUp(self):
        self.capture={'text':'Selected Item','scope':{'collection_resource_id':'demo:id/cards'}}
        self.step={'capability':'assert_contains','target':'Details screen','value':'Selected Item','hints':[]}
        self.obs={'nodes':[node(1,None,[0,100,600,200],text='Selected Item',resource_id='')]}

    def test_without_destination_id_matches_visible_exact_text(self):
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'passed')

    def test_source_title_or_unconfirmed_destination_does_not_pass(self):
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture)['status'],'blocked')
        self.obs['nodes'].append(node(9,None,[0,300,600,800],resource_id='demo:id/cards'))
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'blocked')

    def test_ocr_fallback_requires_destination_evidence_and_exact_label(self):
        self.obs['nodes'][0]['text']='Details'
        self.obs['ocr']=[{'text':'Selected Item','bounds':[0,100,500,200],'confidence':.99}]
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'passed')
        self.obs['ocr'][0]['text']='Selected Item Plus'
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'blocked')
        self.obs['nodes']=[]
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'blocked')

class TruncatedTitleTests(unittest.TestCase):
    def setUp(self):
        self.capture={'text':'Medan al sham mashwiat','scope':{'collection_resource_id':'demo:id/cards'}}
        self.step={'capability':'assert_contains','target':'Menu screen','value':self.capture['text'],'hints':[]}
        self.obs={'nodes':[node(1,None,[0,100,900,200],text='Medan al sham ma...',resource_id='')]}

    def test_explicit_ellipsis_prefix_records_weaker_evidence_type(self):
        for ellipsis in ('...', '\u2026'):
            self.obs['nodes'][0]['text']='MEDAN  al sham ma'+ellipsis
            result=captured_destination_result(self.step,self.obs,self.capture,True)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['match_type'],'truncated_prefix')
            self.assertIn(self.capture['text'],result['evidence'])
            self.assertIn('truncated',result['reason'])

    def test_exact_hierarchy_and_ocr_take_priority(self):
        self.obs['ocr']=[{'text':self.capture['text'],'bounds':[0,100,900,200],'confidence':.99}]
        result=captured_destination_result(self.step,self.obs,self.capture,True)
        self.assertEqual((result['match_type'],result['source']),('exact','ocr'))
        self.obs['nodes'][0]['text']=self.capture['text']
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['source'],'hierarchy')

    def test_missing_ellipsis_wrong_suffix_short_and_ambiguous_block(self):
        for text in ('Medan al sham ma','Medan al sham za...', 'Medan al...', 'Medan...'):
            self.obs['nodes'][0]['text']=text
            self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'blocked',text)
        self.obs['nodes'][0]['text']='Medan al sham ma...'
        self.obs['nodes'].append(node(2,None,[0,300,900,400],text='Medan al sham macaroni'))
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'blocked')

    def test_source_collection_and_unconfirmed_screen_still_block(self):
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture)['status'],'blocked')
        self.obs['nodes'].append(node(9,None,[0,300,900,900],resource_id='demo:id/cards'))
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture,True)['status'],'blocked')

    def test_id_scoped_title_supports_same_ellipsis_rule(self):
        self.step['target']='title'
        self.obs['nodes'][0]['resource_id']='demo:id/title'
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture)['match_type'],'truncated_prefix')
        self.obs['nodes'][0]['text']='Medan...'
        self.assertEqual(captured_destination_result(self.step,self.obs,self.capture)['status'],'blocked')
