import json
from pathlib import Path
import tempfile
import unittest
from kira_live2d_desktop.outfits import outfit_expression_indices
from kira_live2d_desktop.model_profile import load_profile


class OutfitResourceTests(unittest.TestCase):
    def test_resolves_motion_expression_even_when_renamed_or_disabled_for_ai(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'physics.json').write_text(json.dumps({'PhysicsSettings': []}))
            (root/'dress.json').write_text(json.dumps({'Parameters':[{'Id':'Clothes','Value':1,'Blend':'Add'}]}))
            (root/'face.json').write_text(json.dumps({'Parameters':[{'Id':'Cheek','Value':1,'Blend':'Add'}]}))
            model = root/'model.json'
            data = {'FileReferences': {'Moc':'model.moc3','Expressions':[
                {'Name':'ignored','File':'physics.json'}, {'Name':'dress.exp3','File':'dress.json'},
                {'Name':'face.exp3','File':'face.json'}],
                'Motions':{'KiraAI_0_0':[{'Name':'action_1','Expression':'dress.exp3'}]}}}
            for adapted in (False,True):
                if adapted:
                    data['KiraAIAdaptation']={'motion_labels':{'dress':'KiraAI_0_0:action_1'}}
                model.write_text(json.dumps(data))
                override = json.dumps({'motions':{'renamed':{'type':0,'mtn':'KiraAI_0_0:action_1'}},
                    'expressions':{'renamed-face':1}})
                profile = load_profile(str(model),override)
                self.assertEqual(outfit_expression_indices(profile,{'motion':'renamed','expression':'默认'}),[0])
                self.assertEqual(outfit_expression_indices(profile,{'motion':'renamed','expression':'renamed-face'}),[0,1])
                self.assertEqual(outfit_expression_indices(profile,{'motion':'missing','expression':''}),[])
            self.assertIsNone(outfit_expression_indices({'format':'LPK','load_path':'x'},{}))
            self.assertIsNone(outfit_expression_indices({'format':'Cubism 2','load_path':'x'},{}))
