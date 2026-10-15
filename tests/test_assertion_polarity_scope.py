import unittest
from src.main import contains_statement_is_negative, assertion_evidence_error, plan_completion_error
from src.runtime_values import captured_destination_result


class AssertionPolarityScopeTests(unittest.TestCase):
    def test_navigation_absence_does_not_negate_title_match(self):
        value='Maydan Alshaam for Grills'
        for text in [f"visible title is a prefix of {value}; source collection absent",f"source collection absent; exact title {value}",f"No dialog is visible. Title {value} is present."]:
            self.assertFalse(contains_statement_is_negative(value,text),text)

    def test_real_value_absence_still_rejected_for_positive_assertions(self):
        for text in ['Ad is absent.','Ad is not visible.','The target does not contain Ad.','No Ad label is present.']:
            self.assertTrue(contains_statement_is_negative('Ad',text),text)
            self.assertIsNotNone(assertion_evidence_error({'capability':'assert_contains','target':'label','value':'Ad'},{'status':'passed','reason':text,'evidence':''}))

    def test_label_punctuation_or_no_word_does_not_change_polarity(self):
        self.assertFalse(contains_statement_is_negative('No. 1 Kitchen','No. 1 Kitchen is visible.'))
        self.assertTrue(contains_statement_is_negative('No. 1 Kitchen','No. 1 Kitchen is absent.'))

    def test_truncated_title_result_survives_real_completion_guard(self):
        value='Maydan Alshaam for Grills'
        plan_step={'id':'9','capability':'assert_contains','target':'Menu screen','value':'$vendor_title','optional':False}
        executed={**plan_step,'value':value}
        obs={'nodes':[{'node':1,'text':'Maydan Alshaam for Gr...','bounds':[0,100,900,200]}]}
        result=captured_destination_result(executed,obs,{'text':value,'scope':{'collection_resource_id':'demo:id/cards'}},True)
        self.assertEqual(result['status'],'passed')
        self.assertIsNone(assertion_evidence_error(executed,result))
        history=[{'observation':15,'step_completed':True,'plan_step':executed,'decision':{'action':'step_pass',**result}}]
        self.assertIsNone(plan_completion_error({'steps':[plan_step]},history))
