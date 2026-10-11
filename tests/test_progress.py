import unittest
from src.progress import PlanProgress


class ProgressTests(unittest.TestCase):
    def test_layout_events_follow_plan_not_observations(self):
        steps = [
            ('tap', 'action'), ('recover_optional', 'recovery'),
            ('set_control', 'setup'), ('set_control', 'action'),
            ('assert_changed', 'assertion'), ('scroll', 'action'),
            ('assert_scrolled', 'assertion')]
        output = []
        progress = PlanProgress({'steps': [
            {'capability': cap, 'role': role, 'target': 'Example'}
            for cap, role in steps]}, output.append)
        for source, action in [
                ('navigation_gate', 'tap'), ('unexpected_modal_back_gate', 'back'),
                ('layout_precondition_setup', 'tap'),
                ('layout_precondition_settle', 'wait'),
                ('layout_toggle_gate', 'tap'),
                ('layout_toggle_verified', 'screen_scroll'),
                ('screenshot_scroll_fallback', 'passed')]:
            progress.legacy({'action': action, 'reason': 'detail', 'evidence': 'change'},
                            {'source': source, 'layout_evidence': 'change'})
        headers = [line for line in output if line.startswith('[')]
        self.assertEqual([line.split(']')[0] for line in headers],
                         [f'[{i}/7' for i in range(1, 8)])
        self.assertIn('  ↳ Recovery: detail', output)
        self.assertIn('  ↳ Wait: detail', output)

    def test_repeated_observations_do_not_repeat_step_header(self):
        output = []
        progress = PlanProgress({'steps': [{'capability': 'tap', 'target': 'Label'}]}, output.append)
        progress.show(0)
        progress.show(0)
        self.assertEqual(output, ['[1/1] tap: Label'])
