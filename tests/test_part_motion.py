import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from kira_live2d_desktop.native_shell.part_motion import PartMotion,curve_value

class PartMotionTests(unittest.TestCase):
    def test_segment_types_and_boundaries(self):
        self.assertEqual(curve_value([0,0,0,2,1],1),.5)
        self.assertEqual(curve_value([0,0,2,2,1],1),0)
        self.assertEqual(curve_value([0,0,2,2,1],2),1)
        self.assertEqual(curve_value([0,0,3,2,1],1),1)
        self.assertAlmostEqual(curve_value([0,0,1,.1,.2,.8,.9,1,1],.5),.5695,delta=.04)
        self.assertEqual(curve_value([0,.3],5),.3)
    def test_switch_preserves_other_parts_and_loops_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);motion=root/'motion.json';idle=root/'idle.json'
            motion.write_text(json.dumps({'Meta':{'Duration':1,'Loop':True},'Curves':[
                {'Target':'PartOpacity','Id':'A','Segments':[0,0,2,.5,1,2,1,1]},
                {'Target':'PartOpacity','Id':'B','Segments':[0,1,2,.5,0,2,1,0]},
                {'Target':'Parameter','Id':'C','Segments':[0,0]}]}))
            idle.write_text(json.dumps({'Meta':{'Duration':1},'Curves':[]}))
            player=PartMotion(['A','B','C'],{'A':1,'B':0,'C':.8});player.start(motion)
            self.assertEqual(player.values,{'A':0,'B':1,'C':.8})
            player.advance(.6);self.assertEqual((player.values['A'],player.values['B']),(1,0))
            player.advance(.5);self.assertEqual((player.values['A'],player.values['B']),(0,1))
            player.advance(.5);player.start(idle);player.advance(2)
            self.assertEqual((player.values['A'],player.values['B']),(1,0))
            actual={};player.apply(SimpleNamespace(SetPartOpacity=lambda i,v:actual.update({i:v})))
            self.assertEqual(actual,{0:1,1:0,2:.8})
