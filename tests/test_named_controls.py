import unittest
from src.main import semantic_tap_decision,retry_uncertain_interruption
from src.state_assertions import selected_assertion

class NativeControlTests(unittest.TestCase):
    def setUp(self):
        self.nodes=[{'node':58,'resource_id':'example:id/card_button','class_name':'android.widget.CheckBox','text':'','description':'','enabled':True,'checked':False}, {'node':59,'resource_id':'example:id/row_button','class_name':'android.widget.CheckBox','text':'','description':'','enabled':True,'checked':True}]

    def test_taps_named_checkbox_by_type_and_id(self):
        for target,node in [('Card Checkbox',58),('Row Checkbox',59)]:
            self.assertEqual(node,semantic_tap_decision({'nodes':self.nodes},target)[0]['node'])

    def test_checked_and_unchecked_are_deterministic(self):
        for target,status in [('Card Checkbox','failed'),('Row Checkbox','passed')]:
            self.assertEqual(status,selected_assertion({'capability':'assert_selected','target':target},{'nodes':self.nodes})['status'])

    def test_unrelated_name_and_duplicate_controls_are_not_guessed(self):
        from src.control_grounding import named_control
        self.assertIsNone(named_control(self.nodes,'Other Checkbox'))
        self.assertIsNone(named_control(self.nodes+[dict(self.nodes[0],node=60)],'Card Checkbox'))
        self.assertIsNone(named_control(self.nodes,'Card Switch'))

    def test_popup_hierarchy_mismatch_reobserves_but_does_not_back(self):
        action=({'action':'blocked','reason':'Cannot ground the interruption container and heading'}, {'source':'recovery'})
        assessment={'kind':'optional'}
        history=[]
        for _ in range(2):
            result=retry_uncertain_interruption(assessment,action,history,'2')
            self.assertEqual('wait',result[0]['action'])
            history.append({'usage':result[1]})
        self.assertEqual(action,retry_uncertain_interruption(assessment,action,history,'2'))
        self.assertEqual(action,retry_uncertain_interruption({'kind':'plan_step'},action,[],'2'))
