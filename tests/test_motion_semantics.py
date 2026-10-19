import json,tempfile,unittest
from pathlib import Path
from kira_live2d_desktop.motion_analysis import catalog,asset_analysis
from kira_live2d_desktop.model_profile import load_profile

class MotionSemanticsTests(unittest.TestCase):
    def test_hand_state_and_constant_arm_pose_precede_head_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'clip.json').write_text(json.dumps({'Meta':{'Duration':1,'Loop':True},'Curves':[
                {'Target':'Parameter','Id':ident,'Segments':[0,0,0,1,10]}
                for ident in ('ParamAngleX','ParamAngleY','ParamAngleZ','ParamEyeBallX','ParamBodyAngleX')]+[
                {'Target':'Parameter','Id':'ParamLeftArmFrontRotation','Segments':[0,30,2,1,30]},
                {'Target':'PartOpacity','Id':'PartLeftHand01','Segments':[0,0,2,1,0]},
                {'Target':'PartOpacity','Id':'PartLeftHand02','Segments':[0,1,2,1,1]}]}))
            model=root/'model.json';model.write_text(json.dumps({'FileReferences':{'Moc':'pet.moc3','Motions':{'Motion#3':[{'Name':'44','File':'clip.json'}]}}}))
            result=catalog(load_profile(str(model)))['motions']['Motion#3:44']
            self.assertTrue(result['summary'].startswith('手型切换'))
            self.assertIn('左手臂',result['summary'])
            self.assertEqual(result['duration'],1)
            self.assertTrue(result['loop'])
            self.assertIn('片段 1 秒',result['playback_hint'])
            self.assertIn('文件标记循环',result['playback_hint'])
            self.assertIn('状态保留',result['playback_hint'])
    def test_one_shot_and_expression_have_distinct_lifetimes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'motion.json').write_text(json.dumps({'Meta':{'Duration':2,'Loop':False},'Curves':[{'Target':'Parameter','Id':'ParamAngleX','Segments':[0,0,0,2,20]}]}))
            (root/'face.json').write_text(json.dumps({'Parameters':[{'Id':'ParamCheek','Value':1}]}))
            model=root/'model.json';model.write_text(json.dumps({'FileReferences':{'Moc':'pet.moc3','Expressions':[{'Name':'blush','File':'face.json'}],'Motions':{'Nod':[{'File':'motion.json'}]}}}))
            result=catalog(load_profile(str(model)))
            motion=next(iter(result['motions'].values()));face=next(iter(result['expressions'].values()))
            self.assertFalse(motion['loop']);self.assertIn('不代表姿态自动恢复',motion['playback_hint'])
            self.assertIn('持续至后续切换',face['playback_hint'])

    def test_mixed_numbered_expression_matches_known_outfit_but_not_neutral_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            resources={
                'zhifu.exp3':{'Param72':-1,'Param37':1,'ParamCheek':1},
                '0721.exp3':{'Param72':-1,'Param37':1,'ParamCheek':1,'Param7':1},
                'ordinary':{'Param72':0,'Param37':0,'ParamCheek':1},
                'other':{'Param7':1}}
            rows=[]
            for i,(name,values) in enumerate(resources.items()):
                file=f'face{i}.json';rows.append({'Name':name,'File':file})
                (root/file).write_text(json.dumps({'Parameters':[{'Id':k,'Value':v,'Blend':'Add'} for k,v in values.items()]}))
            model=root/'pet.json';model.write_text(json.dumps({'FileReferences':{'Moc':'pet.moc3','Expressions':rows}}))
            result=catalog(load_profile(str(model)))['expressions']
            self.assertTrue(result['0721.exp3']['appearance'])
            self.assertIn('Param72',result['0721.exp3']['appearance_evidence'])
            self.assertFalse(result['ordinary']['appearance'],'Neutral Add=0 clothing entries must not imply an outfit change')
            self.assertFalse(result['other']['appearance'],'Mixed expression face parameters must not propagate as outfit evidence')

    def test_clothes_ids_and_cdi_parts_support_numbered_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'face.json').write_text(json.dumps({'Parameters':[{'Id':'ParamClothes01','Value':1}]}))
            (root/'clip.json').write_text(json.dumps({'Meta':{'Duration':1},'Curves':[{'Target':'PartOpacity','Id':'Part17','Segments':[0,0,2,1,0]}]}))
            (root/'names.json').write_text(json.dumps({'Parts':[{'Id':'Part17','Name':'裙子'}]}))
            model=root/'pet.json';model.write_text(json.dumps({'FileReferences':{'Moc':'pet.moc3','DisplayInfo':'names.json','Expressions':[{'Name':'编号1','File':'face.json'}],'Motions':{'Unnamed':[{'File':'clip.json'}]}}}))
            result=catalog(load_profile(str(model)))
            self.assertTrue(result['expressions']['编号1']['appearance'])
            self.assertTrue(next(iter(result['motions'].values()))['appearance'])
