import unittest
from pathlib import Path
from src.planning import compile_case,validate_source_actions,PlanError


class SuitePlanningTests(unittest.TestCase):
    def test_all_repository_cases_have_valid_complete_fallbacks(self):
        for case in sorted(Path('cases').glob('*.txt')):
            with self.subTest(case=case.name):
                requests=[]
                def invalid(path,payload,timeout):
                    requests.append(payload)
                    return {'done':True,'message':{'content':'{}'}}
                plan=compile_case(invalid,'local',case.read_text())
                self.assertEqual(plan['plan_source'],'controlled_fallback')
                caps=[s['capability'] for s in plan['steps']]
                allowed=requests[0]['format']['properties']['steps']['items']['properties']['capability']['enum']
                if 'swimlanes' in case.name:
                    self.assertIn('seek_item',allowed);self.assertIn('seek_item',caps)
                else:
                    self.assertNotIn('seek_item',allowed);self.assertNotIn('seek_item',caps)
                if 'card-to-row' in case.name or 'row-to-card' in case.name:
                    self.assertEqual(caps.count('set_control'),2)
                    action=next(s for s in plan['steps'] if s['capability']=='set_control' and s['role']=='action')
                    self.assertEqual(action['value'],'row' if 'card-to-row' in case.name else 'card')
                if 'sort-restaurants' in case.name:
                    self.assertEqual(caps.count('tap'),4)
                    self.assertEqual([s['value'] for s in plan['steps'] if s['capability']=='assert_not_contains'],['Ad'])
                    self.assertEqual([s['target'] for s in plan['steps'] if s['capability']=='wait_changed'],['restaurant items'])

    def test_control_action_cannot_cover_unrelated_missing_tap(self):
        source='Steps:\n1. Tap Catalog.\n2. Tap Details.\nExpected result:'
        plan={'steps':[{'capability':'tap','target':'Catalog','value':''},
                       {'capability':'set_control','role':'action','value':'row','position':'right'}]}
        with self.assertRaises(PlanError):validate_source_actions(source,plan)
