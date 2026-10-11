import struct
import unittest
from unittest.mock import patch
from src.main import unexpected_modal_back_gate


class ModalBackGroundingTests(unittest.TestCase):
    def test_contrast_without_foreground_candidate_cannot_authorize_back(self):
        png = b'0' * 16 + struct.pack('>II', 1080, 2340)
        for nodes in ([], [{'node': 1, 'bounds': [0, 0, 1080, 2340]}]):
            with patch('src.main.planned_modal_is_active', return_value=False), \
                 patch('src.main.candidate_ids', return_value=[]), \
                 patch('src.main.decode_png_luminance', return_value=None), \
                 patch('src.main.modal_dimming_evidence', return_value={'confirmed': True}) as dimming:
                self.assertIsNone(unexpected_modal_back_gate({'png': png, 'nodes': nodes}, []))
                dimming.assert_not_called()
