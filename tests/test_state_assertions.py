import json
import unittest
from src.state_assertions import modal_assertion, selected_assertion
from src.main import assertion_evidence_error


class StateAssertionTests(unittest.TestCase):
    def test_same_name_button_does_not_keep_modal_open(self):
        identities = {}
        step = {'capability': 'assert_visible', 'target': 'Settings sheet'}
        opened = {'nodes': [{'node': 1, 'resource_id': 'app:id/design_bottom_sheet'},
            {'node': 2, 'parent': 1, 'text': 'Settings', 'resource_id': 'app:id/heading'}]}
        self.assertEqual(modal_assertion(step, opened, identities)['status'], 'passed')
        step['capability'] = 'assert_hidden'
        closed = {'nodes': [{'node': n, 'resource_id': 'app:id/view'+str(n)} for n in range(10)]}
        closed['nodes'][3]['text'] = 'Settings'
        self.assertEqual(modal_assertion(step, closed, identities)['status'], 'passed')
        self.assertEqual(modal_assertion(step, opened, identities)['status'], 'failed')

    def test_missing_hierarchy_is_not_absence(self):
        self.assertIsNone(modal_assertion({'capability': 'assert_hidden', 'target': 'Settings sheet'},
            {'nodes': []}, {'settings sheet': {'container_id': 'modal', 'heading_id': 'title'}}))

    def test_different_modal_is_ambiguous(self):
        self.assertIsNone(modal_assertion({'capability': 'assert_hidden', 'target': 'Settings sheet'},
            {'nodes': [{'node': 1, 'resource_id': 'app:id/dialog'}]},
            {'settings sheet': {'container_id': 'old', 'heading_id': 'old_title'}}))

    def test_selection_requires_state_in_option_row(self):
        step = {'capability': 'assert_selected', 'target': 'Newest'}
        obs = {'nodes': [{'node': 1, 'parent': 9, 'text': 'Newest'},
            {'node': 2, 'parent': 9, 'class_name': 'android.widget.RadioButton', 'checked': True}]}
        self.assertEqual(selected_assertion(step, obs)['status'], 'passed')
        obs['nodes'][1]['checked'] = False
        self.assertEqual(selected_assertion(step, obs)['status'], 'failed')
        obs['nodes'][1]['parent'] = 99
        self.assertIsNone(selected_assertion(step, obs))

    def test_visibility_does_not_prove_selected(self):
        self.assertIsNotNone(assertion_evidence_error({'capability': 'assert_selected', 'target': 'Newest'},
            {'status': 'passed', 'reason': 'Newest text is present.', 'evidence': 'Newest is visible.'}))
