import json
import unittest

from src.planning import (
    PlanError,
    compile_case,
    compile_controlled_case,
    control_transition,
    extract_control_options,
    extract_control_transition,
    navigation_target,
    validate_plan,
    validate_executable_plan,
)


def sample_plan(initial='row',initial_side='right',target='card',target_side='left'):
    return {
        'version':1,
        'name':initial+' to '+target,
        'steps':[
            {'id':'open','capability':'tap','role':'action',
             'target':'Restaurants','hints':['restaurantsVertical'],
             'value':'','position':'none',
             'direction':'none','optional':False,'success':'listing visible'},
            {'id':'recover','capability':'recover_optional','role':'recovery',
             'target':'','value':'','position':'none','direction':'none',
             'optional':True,'success':'foreground clear'},
            {'id':'setup','capability':'set_control','role':'setup',
             'target':'listing layout','value':initial,'position':initial_side,
             'direction':'none','optional':False,'success':'initial layout'},
            {'id':'toggle','capability':'set_control','role':'action',
             'target':'listing layout','value':target,'position':target_side,
             'direction':'none','optional':False,'success':'target layout'},
            {'id':'verify','capability':'assert_changed','role':'assertion',
             'target':'restaurant items','value':'','position':'none',
             'direction':'none','optional':False,'success':'items changed'},
            {'id':'scroll','capability':'scroll','role':'action',
             'target':'restaurant list','value':'','position':'none',
             'direction':'down','optional':False,'success':'list moved'},
            {'id':'verify-scroll','capability':'assert_scrolled','role':'assertion',
             'target':'restaurant list','value':'','position':'none',
             'direction':'none','optional':False,'success':'content moved'},
        ],
    }


class PlanningTests(unittest.TestCase):
    def test_valid_plan_exposes_semantic_target_and_transition(self):
        plan=validate_plan(sample_plan())
        self.assertEqual('Restaurants',navigation_target(plan))
        self.assertEqual({
            'control':'listing layout',
            'initial_name':'row','initial_side':'right',
            'target_name':'card','target_side':'left',
        },control_transition(plan))
        self.assertEqual(['restaurantsVertical'],plan['steps'][0]['hints'])

    def test_compiler_uses_model_json_then_validates(self):
        raw=sample_plan('card','left','row','right')
        def request(path,payload,timeout):
            self.assertEqual('/api/chat',path)
            self.assertIn('human-written Android test case',
                          payload['messages'][0]['content'])
            return {'done':True,'message':{'content':json.dumps(raw)}}
        plan=compile_case(request,'local-model','plain text',30)
        self.assertEqual('card',control_transition(plan)['initial_name'])
        self.assertEqual('ai',plan['plan_source'])

    def test_compiler_repairs_unambiguous_model_role_drift(self):
        raw=sample_plan()
        raw['steps'][1]['role']='action'
        raw['steps'][4]['role']='action'
        def request(_path,_payload,_timeout):
            return {'done':True,'message':{'content':json.dumps(raw)}}
        plan=compile_case(request,'local-model','plain text',30)
        self.assertEqual('recovery',plan['steps'][1]['role'])
        self.assertEqual('assertion',plan['steps'][4]['role'])

    def test_compiler_retries_with_validation_feedback_for_missing_value(self):
        invalid=sample_plan()
        invalid['steps'][2]['value']=''
        corrected=sample_plan()
        calls=[]
        def request(_path,payload,_timeout):
            calls.append(payload)
            raw=invalid if len(calls)==1 else corrected
            return {'done':True,'message':{'content':json.dumps(raw)}}
        plan=compile_case(request,'local-model','plain text',30)
        self.assertEqual('row',plan['steps'][2]['value'])
        self.assertEqual(2,len(calls))
        self.assertIn('set_control requires a value',
                      calls[1]['messages'][-1]['content'])

    def test_explicit_control_vocabulary_fills_missing_model_values(self):
        raw=sample_plan()
        raw['steps'][2]['value']=''
        raw['steps'][3]['value']=''
        calls=[]
        def request(_path,_payload,_timeout):
            calls.append(1)
            return {'done':True,'message':{'content':json.dumps(raw)}}
        case=(
            'Verify row view (right toggle option) is selected.\n'
            'Tap card view (left toggle option).'
        )
        plan=compile_case(request,'local-model',case,30)
        self.assertEqual('row',plan['steps'][2]['value'])
        self.assertEqual('card',plan['steps'][3]['value'])
        self.assertEqual(1,len(calls))

    def test_explicit_transition_overrides_conflicting_model_fields(self):
        raw=sample_plan()
        raw['steps'][0]['position']='left'
        raw['steps'][2].update(
            target='row',value='card',position='left')
        raw['steps'][3].update(
            target='card',value='card',position='left')
        raw['steps'].pop()
        def request(_path,_payload,_timeout):
            return {'done':True,'message':{'content':json.dumps(raw)}}
        case=(
            'Verify toggling from row view to card view.\n'
            'Row view uses the right toggle option.\n'
            'Card view uses the left toggle option.'
        )
        plan=compile_case(request,'local-model',case,30)
        transition=control_transition(plan)
        self.assertEqual(('row','right'),(
            transition['initial_name'],transition['initial_side']))
        self.assertEqual(('card','left'),(
            transition['target_name'],transition['target_side']))
        self.assertEqual('none',plan['steps'][0]['position'])
        self.assertTrue(any(
            step['capability']=='assert_scrolled' for step in plan['steps']))

    def test_extracts_only_one_explicit_transition(self):
        options={'right':'row','left':'card'}
        self.assertEqual(('row','card'),extract_control_transition(
            'Toggle from row view to card view.',options))

    def test_scroll_action_is_restored_before_orphan_assertion(self):
        raw=sample_plan('card','left','row','right')
        raw['steps']=[step for step in raw['steps']
                      if step['capability']!='scroll']
        def request(_path,_payload,_timeout):
            return {'done':True,'message':{'content':json.dumps(raw)}}
        case=(
            'Toggle from card view to row view.\n'
            'Card view uses the left toggle option.\n'
            'Row view uses the right toggle option.\n'
            'Scroll down within the vertical restaurant list.'
        )
        plan=compile_case(request,'local-model',case,30)
        names=[step['capability'] for step in plan['steps']]
        self.assertLess(names.index('scroll'),names.index('assert_scrolled'))
        scroll=next(step for step in plan['steps']
                    if step['capability']=='scroll')
        self.assertEqual('down',scroll['direction'])

    def test_control_vocabulary_never_guesses_without_explicit_side(self):
        self.assertEqual({},extract_control_options(
            'Switch from row view to card view.'))

    def test_single_option_set_control_is_normalized_to_tap(self):
        raw=sample_plan()
        raw['steps']=[raw['steps'][0],{
            'id':'rating','capability':'set_control','role':'action',
            'target':'Sorting options','hints':['rating'],'value':'Ratings low to high',
            'position':'none','direction':'none','optional':False,
            'success':'Rating option selected',
        },{
            'id':'selected','capability':'assert_selected','role':'assertion',
            'target':'Ratings low to high','hints':['rating'],'value':'',
            'position':'none','direction':'none','optional':False,
            'success':'Rating option is selected',
        }]
        def request(_path,_payload,_timeout):
            return {'done':True,'message':{'content':json.dumps(raw)}}
        plan=compile_case(
            request,'local-model','Tap Ratings low to high and verify selected.',30)
        self.assertEqual('tap',plan['steps'][1]['capability'])
        self.assertEqual('Ratings low to high',plan['steps'][1]['target'])

    def test_option_selection_never_becomes_layout_transition(self):
        raw=sample_plan()
        raw['steps']=[raw['steps'][0],{
            'id':'rating-setup','capability':'set_control','role':'setup',
            'target':'Ratings low to high','hints':['rating'],'value':'',
            'position':'none','direction':'none','optional':False,
            'success':'Prepare rating option',
        },{
            'id':'rating-action','capability':'set_control','role':'action',
            'target':'Sorting options','hints':['rating'],
            'value':'Ratings low to high','position':'none','direction':'none',
            'optional':False,'success':'Select rating option',
        },{
            'id':'selected','capability':'assert_selected','role':'assertion',
            'target':'Ratings low to high','hints':['rating'],'value':'',
            'position':'none','direction':'none','optional':False,
            'success':'Rating option is selected',
        }]
        def request(_path,_payload,_timeout):
            return {'done':True,'message':{'content':json.dumps(raw)}}
        plan=compile_case(
            request,'local-model',
            'Tap Ratings low to high and verify it is selected.',30)
        capabilities=[step['capability'] for step in plan['steps']]
        self.assertNotIn('set_control',capabilities)
        self.assertIn('tap',capabilities)
        self.assertIn('assert_selected',capabilities)
        self.assertEqual('ai',plan['plan_source'])

    def test_filter_assertion_capabilities_validate(self):
        plan=sample_plan()
        plan['steps'].extend([
            {'id':'visible','capability':'assert_visible','role':'assertion',
             'target':'Filters pill','hints':['filters'],'value':'',
             'position':'none','direction':'none','optional':False,
             'success':'Filters pill visible'},
            {'id':'contains','capability':'assert_contains','role':'assertion',
             'target':'first restaurant item','hints':['vendor'],'value':'Ad',
             'position':'none','direction':'none','optional':False,
             'success':'Ad visible'},
            {'id':'not-ad','capability':'assert_not_contains','role':'assertion',
             'target':'first restaurant item','hints':['vendor'],'value':'Ad',
             'position':'none','direction':'none','optional':False,
             'success':'Ad absent'},
            {'id':'selected','capability':'assert_selected','role':'assertion',
             'target':'Ratings low to high','hints':['rating'],'value':'',
             'position':'none','direction':'none','optional':False,
             'success':'Selected'},
            {'id':'closed','capability':'assert_hidden','role':'assertion',
             'target':'Filters sheet','hints':['filter'],'value':'',
             'position':'none','direction':'none','optional':False,
             'success':'Sheet closed'},
            {'id':'loaded','capability':'wait_changed','role':'assertion',
             'target':'restaurant items','hints':['vendor'],'value':'',
             'position':'none','direction':'none','optional':False,
             'success':'Items refreshed'},
        ])
        self.assertEqual(13,len(validate_plan(plan)['steps']))

    def test_selected_assertion_rejects_opposite_tapped_option(self):
        plan={
            'version':1,'name':'sort direction','steps':[
                {'id':'open','capability':'tap','role':'action',
                 'target':'Restaurants','hints':[],'value':'',
                 'position':'none','direction':'none','optional':False,
                 'success':'listing open'},
                {'id':'choose','capability':'tap','role':'action',
                 'target':'Ratings (low to high)','hints':[],'value':'',
                 'position':'none','direction':'none','optional':False,
                 'success':'rating selected'},
                {'id':'selected','capability':'assert_selected',
                 'role':'assertion','target':'Ratings (High To Low)',
                 'hints':[],'value':'','position':'none','direction':'none',
                 'optional':False,'success':'rating selected'},
            ],
        }
        with self.assertRaisesRegex(
                PlanError,'must match the immediately preceding'):
            validate_executable_plan(validate_plan(plan))

    def test_compiler_preserves_scoped_assertion_value(self):
        raw=sample_plan()
        raw['steps'].append({
            'id':'not-ad','capability':'assert_not_contains','role':'assertion',
            'target':'first restaurant item','hints':['vendor'],'value':'Ad',
            'position':'none','direction':'none','optional':False,
            'success':'Ad absent',
        })
        def request(_path,_payload,_timeout):
            return {'done':True,'message':{'content':json.dumps(raw)}}
        plan=compile_case(request,'local-model',
                          'Verify first restaurant item does not contain "Ad".',30)
        self.assertEqual('Ad',plan['steps'][-1]['value'])

    def test_controlled_compiler_builds_sorting_case(self):
        case='''Title: Sort by rating
Steps:
1. Tap the Restaurants label on Home.
2. Recover safely from any optional foreground sheet.
3. Verify Filters pill is shown.
4. Verify that first restaurant item contains "Ad" label.
5. Tap Filters.
6. Verify that Filters sheet is open.
7. Tap on the Ratings(low to high) option in the Sorting options.
8. Verify Ratings(low to high) option is selected.
9. Tap on Apply button.
10. Verify that Filters pill shows indicator view label "1"
11. Verify Filters sheet is closed and wait until restaurant items load.
12. Verify new restaurant items screen loaded.
13. Verify that first restaurant item does not contain Ad label.
Expected result:
- The list scrolls and reveals more content.
'''
        plan=validate_executable_plan(validate_plan(
            compile_controlled_case(case)))
        names=[step['capability'] for step in plan['steps']]
        self.assertIn('assert_contains',names)
        self.assertIn('assert_not_contains',names)
        self.assertIn('assert_selected',names)
        self.assertIn('assert_hidden',names)
        self.assertIn('wait_changed',names)
        self.assertLess(names.index('scroll'),names.index('assert_scrolled'))
        negative=next(step for step in plan['steps']
                      if step['capability']=='assert_not_contains')
        self.assertEqual('Ad',negative['value'])

    def test_invalid_model_uses_controlled_language_fallback(self):
        invalid=sample_plan()
        invalid['steps'][2]['value']=''
        calls=[]
        def request(_path,payload,_timeout):
            calls.append(payload)
            return {'done':True,'message':{'content':json.dumps(invalid)}}
        case='''Title: Visible filter
Steps:
1. Tap Restaurants.
2. Verify Filters pill is visible.
'''
        plan=compile_case(request,'local-model',case,30)
        self.assertEqual(['tap','assert_visible'],
                         [step['capability'] for step in plan['steps']])
        self.assertEqual('controlled_fallback',plan['plan_source'])
        self.assertEqual(3,plan['planner_attempts'])
        self.assertEqual(3,len(plan['planner_errors']))
        self.assertEqual(3,len(calls))
        self.assertIn('Canonical capability catalog',
                      calls[0]['messages'][0]['content'])

    def test_compiler_stops_after_bounded_repair_attempts(self):
        invalid=sample_plan()
        invalid['steps'][2]['value']=''
        calls=[]
        def request(_path,_payload,_timeout):
            calls.append(1)
            return {'done':True,'message':{'content':json.dumps(invalid)}}
        with self.assertRaisesRegex(PlanError,'after 3 attempts'):
            compile_case(request,'local-model','plain text',30)
        self.assertEqual(3,len(calls))

    def test_unknown_capability_is_rejected(self):
        plan=sample_plan()
        plan['steps'][0]['capability']='shell'
        with self.assertRaisesRegex(PlanError,'Unsupported capability'):
            validate_plan(plan)

    def test_capability_role_contract_is_enforced(self):
        plan=sample_plan()
        plan['steps'][0]['role']='assertion'
        with self.assertRaisesRegex(PlanError,'does not allow role'):
            validate_plan(plan)

    def test_transition_requires_explicit_positions_for_safe_execution(self):
        plan=validate_plan(sample_plan(initial_side='none'))
        with self.assertRaisesRegex(PlanError,'left/right'):
            control_transition(plan)

    def test_duplicate_step_ids_are_rejected(self):
        plan=sample_plan()
        plan['steps'][1]['id']=plan['steps'][0]['id']
        with self.assertRaisesRegex(PlanError,'unique'):
            validate_plan(plan)


if __name__=='__main__':
    unittest.main()
