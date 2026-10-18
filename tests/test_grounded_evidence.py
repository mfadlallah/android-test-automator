import io,json,tempfile,unittest
from pathlib import Path
from PIL import Image
from src.grounded_evidence import save_grounded_evidence
from src.main import structured_step_results


class GroundedEvidenceTests(unittest.TestCase):
    def observation(self):
        image=Image.new('RGB',(1080,2340),'white');buf=io.BytesIO();image.save(buf,format='PNG')
        return {'png':buf.getvalue(),'observation':15}

    def test_title_crop_is_zoomed_and_context_has_red_bounds(self):
        obs=self.observation()
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            record=save_grounded_evidence(folder,'15-captured-comparison',obs,[261,370,818,421],{'result':{'match_type':'truncated_prefix','observed_text':'Example title...'}})
            self.assertTrue((folder/record['crop_image']).exists())
            with Image.open(folder/record['crop_image']) as crop:self.assertGreater(crop.width,557)
            with Image.open(folder/record['context_image']) as full:self.assertEqual(full.getpixel((261,370)),(255,0,0))
            self.assertEqual(record['grounded_bounds'],[261,370,818,421])
            step={'id':'9','capability':'assert_contains','role':'assertion','target':'Details screen','value':'Example title'}
            history=[{'step_completed':True,'plan_step':step,'decision':{'action':'step_pass'},'observation':15}]
            results=structured_step_results({'steps':[step]},history,folder)
            self.assertEqual(results[0]['crop_artifact'],record['crop_image'])

    def test_tap_uses_same_helper_and_missing_bounds_never_guess(self):
        obs=self.observation()
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            record=save_grounded_evidence(folder,'15-tap-grounded',obs,[0,100,400,500],{'action':'tap'})
            self.assertIn('crop_image',record)
            for bounds in (None,[-1,0,400,500],[0,0,2000,500]):
                record=save_grounded_evidence(folder,'invalid',obs,bounds,{})
                self.assertIn('crop_error',record);self.assertNotIn('crop_image',record)
