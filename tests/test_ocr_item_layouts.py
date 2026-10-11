import io
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from src.adapters.generic_adapter import GenericAdapter
from src.main import Blocked, assess_plan_assertion, scoped_exact_value_result


class OcrItemLayoutTests(unittest.TestCase):
    def observation(self, scale=1, card=False, dark=False):
        width,height=int(600*scale),int(1200*scale)
        color='#202020' if dark else '#ffffff'
        fill='#505050' if dark else '#eeeeee'
        image=Image.new('RGB',(width,height),color)
        draw=ImageDraw.Draw(image)
        bottom=850 if card else 520
        for box in [(20,345,580,bottom),(20,bottom+30,580,1130)]:
            draw.rectangle(tuple(int(v*scale) for v in box),fill=fill)
        rows=[('Products',(30,240,220,280)),('Filters',(30,300,120,325)),
              ('Sort',(200,300,270,325)),
              ('Item Alpha',(30,640 if card else 370,220,680 if card else 400)),
              ('4.9 rating',(30,700 if card else 425,150,725 if card else 445)),
              ('Sponsored',(400,780 if card else 470,560,800 if card else 490)),
              ('Item Beta',(30,bottom+70,220,bottom+100)),
              ('Ad',(400,bottom+110,450,bottom+130))]
        data=io.BytesIO();image.save(data,format='PNG')
        return {'png':data.getvalue(),'nodes':[],
                'ocr':[{'text':text,'confidence':.99,
                        'bounds':[int(v*scale) for v in bounds]} for text,bounds in rows]}

    def test_variable_cards_rows_resolutions_and_background_colors(self):
        for card in (False,True):
            for scale in (.75,1,2):
                for dark in (False,True):
                    with self.subTest(card=card,scale=scale,dark=dark):
                        obs=self.observation(scale,card,dark)
                        bounds=GenericAdapter().get_assertion_crop(
                            'first product item',obs,{'capability':'assert_not_contains','value':'Missing'})
                        self.assertTrue(obs['ocr_item_scope']['boundary_confirmed'])
                        self.assertGreaterEqual(bounds.y2,(850 if card else 520)*scale)
                        self.assertLess(bounds.y2,(880 if card else 550)*scale)
                        self.assertIsNone(scoped_exact_value_result(obs,
                            {'capability':'assert_contains','target':'first product item','value':'Ad'},
                            [bounds.x1,bounds.y1,bounds.x2,bounds.y2]))

    def test_text_in_card_artwork_is_not_a_second_item_title(self):
        obs=self.observation(card=True)
        image=Image.open(io.BytesIO(obs['png']))
        draw=ImageDraw.Draw(image)
        # Textured artwork carrying OCR words above the actual item title.
        for x in range(20,580,4):
            draw.rectangle((x,345,x+3,610),fill=(x%256,(x*3)%256,(x*7)%256))
        buffer=io.BytesIO();image.save(buffer,format='PNG');obs['png']=buffer.getvalue()
        obs['ocr'] += [
            {'text':'Crafted by','confidence':.99,'bounds':[30,410,220,450]},
            {'text':'Nature','confidence':.99,'bounds':[30,510,220,550]},
        ]
        bounds=GenericAdapter().get_assertion_crop('first product item',obs,
            {'capability':'assert_contains','value':'Sponsored'})
        self.assertTrue(obs['ocr_item_scope']['boundary_confirmed'])
        self.assertGreaterEqual(bounds.y2,800)
        self.assertLessEqual(bounds.y2,851)

    def test_positive_label_gets_tight_crop_in_ocr_only_mode(self):
        obs=self.observation(card=True)
        bounds=GenericAdapter().get_assertion_crop('first product item',obs,
            {'capability':'assert_contains','value':'Sponsored'})
        self.assertLess(bounds.x2-bounds.x1,600)
        self.assertEqual('passed',scoped_exact_value_result(obs,
            {'capability':'assert_contains','target':'first product item','value':'Sponsored'},
            [bounds.x1,bounds.y1,bounds.x2,bounds.y2])['status'])

    def test_metadata_resembling_next_title_does_not_truncate_card(self):
        for scale in (.75,1,2):
            for dark in (False,True):
                with self.subTest(scale=scale,dark=dark):
                    obs=self.observation(scale,card=True,dark=dark)
                    obs['ocr'].append({'text':'Extra details','confidence':.99,
                        'bounds':[int(v*scale) for v in (30,790,220,830)]})
                    GenericAdapter().get_assertion_crop('first product item',obs,
                        {'capability':'assert_contains','value':'Sponsored'})
                    scope=obs['ocr_item_scope']
                    self.assertTrue(scope['boundary_confirmed'])
                    self.assertGreaterEqual(scope['bounds'][3],850*scale)
                    self.assertLess(scope['bounds'][3],880*scale)

    def test_plain_whitespace_without_next_surface_is_not_card_gap(self):
        image=Image.new('RGB',(600,1200),'white')
        buffer=io.BytesIO();image.save(buffer,format='PNG')
        self.assertIsNone(GenericAdapter()._visual_card_gap(
            {'png':buffer.getvalue()},400,1100))

    def test_no_content_anchor_does_not_guess_item_from_status_bar(self):
        obs=self.observation();obs['ocr']=[{'text':'M','confidence':1,'bounds':[20,10,50,30]}]
        self.assertIsNone(GenericAdapter().get_assertion_crop(
            'first product item',obs,{'capability':'assert_contains','value':'Ad'}))

    @patch('src.main.local_request')
    @patch('src.main.read_screen_ocr',return_value=[])
    @patch('src.main.scoped_assertion_image',return_value=(b'png',[0,100,600,600]))
    def test_unconfirmed_boundary_blocks_negative_without_model_call(self,_crop,_ocr,request):
        obs={'nodes':[],'ocr':[],'ocr_item_scope':{
            'target':'first product item','boundary_confirmed':False}}
        for capability in ('assert_contains','assert_not_contains'):
            with self.subTest(capability=capability):
                with self.assertRaisesRegex(Blocked,'boundary is uncertain'):
                    assess_plan_assertion('local',{'capability':capability,
                        'target':'first product item','value':'Ad'},obs)
        request.assert_not_called()
