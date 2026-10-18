import unittest
from pathlib import Path
from src.planning import compile_case,compile_controlled_case

class CheckboxPlanningTests(unittest.TestCase):
    def test_both_checkbox_transitions_preserve_actions_and_assertions(self):
        for name,source,dest in [('33271746-card-to-row','Card','Row'),('33271747-row-to-card','Row','Card')]:
            with self.subTest(case=name):
                def invalid(*args):
                    return {'done':True,'message':{'content':'{}'}}
                plan=compile_case(invalid,'local',(Path('cases')/(name+'.txt')).read_text())
                self.assertEqual([s['capability'] for s in plan['steps']],['tap','recover_optional','tap','assert_selected','tap','assert_selected','assert_changed','scroll','assert_scrolled'])
                self.assertEqual([s['target'] for s in plan['steps'] if s['capability']=='tap'],['Restaurants',source+' Checkbox',dest+' Checkbox'])
                self.assertEqual(plan['steps'][6]['target'],'Vendors RecyclerView')

    def test_generic_change_tenses_and_container_wording(self):
        for verb in ['change','changes','changed','has changed','have changed']:
            for target in ['Inventory list','items within Inventory list']:
                with self.subTest(verb=verb,target=target):
                    plan=compile_controlled_case('Title: Update\nSteps:\n1. Verify '+target+' '+verb+' from compact view to detailed view.\nExpected result:\n')
                    self.assertEqual(plan['steps'][0]['capability'],'assert_changed')
                    self.assertEqual(plan['steps'][0]['target'],'Inventory list')
