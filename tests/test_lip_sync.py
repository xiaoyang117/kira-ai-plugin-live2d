import math,tempfile,unittest,wave
from array import array
from pathlib import Path
from unittest.mock import patch
from kira_live2d_desktop.lip_sync import envelope,levels

class LipSyncTests(unittest.TestCase):
    def test_silence_is_closed_and_voice_has_bounded_levels(self):
        self.assertTrue(all(value==0 for value in levels([0]*8000,8000,1)['levels']))
        samples=[int(16000*math.sin(i*.2)) for i in range(4000)]+[0]*4000
        data=levels(samples,8000,1)
        self.assertEqual(data['step_ms'],40)
        self.assertTrue(all(0<=value<=1 for value in data['levels']))
        self.assertGreater(max(data['levels']),.8)
        self.assertEqual(data['levels'][-1],0)
    def test_pcm_wav_and_missing_decoder_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'voice.wav'
            with wave.open(str(path),'wb') as writer:
                writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(8000)
                writer.writeframes(array('h',[12000,-12000]*160).tobytes())
            self.assertGreater(envelope(path)['levels'][0],.8)
            with patch('kira_live2d_desktop.lip_sync.shutil.which',return_value=None):self.assertEqual(envelope(Path(folder)/'missing.mp3')['levels'],[])
