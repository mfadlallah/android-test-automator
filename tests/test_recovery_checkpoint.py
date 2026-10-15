import unittest
from src.planning import ensure_optional_recovery, compile_case
from tests.test_collections import step


class RecoveryCheckpointTests(unittest.TestCase):
    def test_insert_after_navigation_and_keep_original_ids(self):
        plan={'version':1,'name':'test','steps':[step('auto-recovery','tap','Catalog'),step(2,'assert_visible','Results')]}
        out=ensure_optional_recovery(plan)
        self.assertEqual([s['capability'] for s in out['steps']],['tap','recover_optional','assert_visible'])
        self.assertEqual(out['steps'][1]['id'],'auto-recovery-2')
        self.assertTrue(out['steps'][1]['optional'])
        self.assertEqual(len(plan['steps']),2)
        self.assertEqual(ensure_optional_recovery(out),out)

    def test_existing_checkpoint_not_duplicated(self):
        recovery=step(2,'recover_optional','');recovery.update(role='recovery',optional=True)
        plan={'steps':[step(1,'tap','Catalog'),recovery]}
        self.assertEqual(ensure_optional_recovery(plan),plan)

    def test_fallback_without_explicit_recovery_includes_checkpoint(self):
        def invalid(*args):
            return {'done':True,'done_reason':'stop','message':{'content':'{}'}}
        plan=compile_case(invalid,'local','Title: Test\nSteps:\n1. Tap Catalog.\n2. Verify Results is visible.\nExpected result: Results visible')
        self.assertEqual([s['capability'] for s in plan['steps']],['tap','recover_optional','assert_visible'])
