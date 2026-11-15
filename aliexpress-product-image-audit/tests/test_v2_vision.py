import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from ai_judge.client import JudgeClient
from budget_manager import BudgetManager


def observation(item, decision='KEEP', **changes):
    result=dict(schema_version='image-action-decision.v2',task_type='image_action_decision',
        item_id=item['id'],image_id=item['id'],image_sha256=item['sha256'],image_type=item['image_type'],
        evidence_ids=item['evidence_ids'],confidence=.95,abstain=False,decision=decision,
        visual_class='TOY_PRODUCT',retail_box_status='ABSENT',retail_box_confidence=.95,
        retail_box_bbox=None,box_relation='UNRELATED',toy_present=True,toy_confidence=.95,
        watermarks=[],product_identity=dict(same_product_as_context='YES',model_visible='UNKNOWN',structure_match='YES',color_match='YES'),
        sku_suitability=dict(is_toy_photo=True,is_retail_box_photo=False,recommended_group='WITHOUT_RETAIL_BOX'),
        subject_complete=True,clear=True,angle='FRONT',background_complexity='SMOOTH',
        preserve_regions=[],reason='visible product')
    result.update(changes)
    return result


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);p=self.root/'source.png';Image.new('RGB',(96,96),'white').save(p)
        self.item=dict(id='IMG_1',task_type='image_action_decision',local=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),image_type='MAIN',evidence_ids=['SOURCE'])
        self.budget=BudgetManager({'ai_requests':30,'full_resolution_images':20});self.addCleanup(self.budget.close)

    def client(self, callback):
        calls=[]
        def transport(model,item,context):
            calls.append((model,copy.deepcopy(context)))
            result=callback(model,item)
            return {'choices':[{'message':{'content':json.dumps(result)}}],'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}
        return JudgeClient(self.budget,self.root/'cache',transport=transport,retries=0),calls

    def decide(self,client):
        from ai_judge.image_action_decision import decide
        return decide(client,self.item,{'pid':1,'descriptionJson':'EXCLUDED'})

    def test_keep_uses_one_primary(self):
        client,calls=self.client(lambda m,i:observation(i))
        self.assertEqual(self.decide(client)['decision'],'KEEP')
        self.assertEqual(len(calls),1)
        self.assertNotIn('descriptionJson',calls[0][1])

    def test_delete_needs_independent_second_and_conflict_defers(self):
        client,calls=self.client(lambda m,i:observation(i,'DELETE' if m==client.models[0] else 'KEEP'))
        self.assertEqual(self.decide(client)['decision'],'REVIEW')
        self.assertEqual([c[0] for c in calls],list(client.models))
        self.assertNotIn('primary_result',calls[1][1])

    def test_bad_sha_and_coordinates_rejected(self):
        from ai_judge.image_action_decision import validate
        for changes in ({'image_sha256':'0'*64},{'retail_box_status':'PRESENT','retail_box_bbox':[-.1,0,.5,.5]}, {'confidence':float('nan')}):
            with self.assertRaises(ValueError):validate(observation(self.item,**changes),self.item)

    def test_invalid_primary_second_does_not_authorize_deletion(self):
        client,calls=self.client(lambda m,i: {} if m==client.models[0] else observation(i,'DELETE'))
        self.assertEqual(self.decide(client)['decision'],'REVIEW')
        self.assertEqual(len(calls),2)

    def test_uncertain_box_gets_one_second_but_conflict_stays_review(self):
        client,calls=self.client(lambda m,i:observation(i,retail_box_status='UNCERTAIN') if m==client.models[0] else observation(i))
        self.assertEqual(self.decide(client)['decision'],'REVIEW');self.assertEqual(len(calls),2)

    def test_factory_print_not_removable(self):
        from ai_judge.image_action_decision import validate
        mark=dict(kind='PRODUCT_PRINT',bbox=[0,.8,.2,.9],confidence=.99,preserve_overlap_risk='LOW')
        with self.assertRaises(ValueError):validate(observation(self.item,'REMOVE_TEXT',watermarks=[mark]),self.item)

    def test_cache_reused_and_context_invalidates_without_description(self):
        from ai_judge.image_action_decision import decide
        client,calls=self.client(lambda m,i:observation(i))
        self.decide(client);self.decide(client)
        self.assertEqual(len(calls),1)
        decide(client,self.item,{'pid':1,'identityJson':{'modelCode':'changed'}})
        self.assertEqual(len(calls),2)

    def test_transport_error_does_not_retry_same_model(self):
        from ai_judge.image_action_decision import decide
        calls=[]
        def broken(m,i,c):calls.append(m);raise OSError('offline failure')
        client=JudgeClient(self.budget,self.root/'cache',transport=broken,retries=2)
        self.assertEqual(decide(client,self.item,{})['decision'],'REVIEW')
        self.assertEqual(calls,list(client.models))

    def test_threshold_point_eight_and_unknown_never_keep(self):
        client,calls=self.client(lambda m,i:observation(i,confidence=.8))
        self.assertEqual(self.decide(client)['decision'],'KEEP');self.assertEqual(len(calls),1)
        client.result_cache.root=self.root/'other'
        self.item['id']='UNKNOWN';self.item['purpose']='unknown-class'
        client.transport=lambda m,i,c:{'choices':[{'message':{'content':json.dumps(observation(i,visual_class='UNKNOWN'))}}]}
        self.assertEqual(self.decide(client)['decision'],'REVIEW')

    def test_outgoing_schema_uses_one_decision_confidence(self):
        import jsonschema
        from ai_judge.image_action_decision import PROMPT
        schema=json.loads(PROMPT.split('OUTPUT_JSON_SCHEMA:\n',1)[1])
        canonical=observation(self.item)
        jsonschema.validate(canonical,schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(dict(canonical,decision_confidence=canonical['confidence']),schema)

    def test_legacy_confidence_alias_is_only_accepted_when_identical(self):
        from ai_judge.image_action_decision import validate
        row=observation(self.item,confidence=.86,decision_confidence=.86)
        original=copy.deepcopy(row)
        self.assertEqual(validate(row,self.item)['confidence'],.86)
        self.assertEqual(row,original)
        row['decision_confidence']=.8
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_CONFIDENCE'):
            validate(row,self.item)
        self.assertEqual(row['decision_confidence'],.8)

    def test_conflicting_confidences_cannot_be_rescued_by_second_model(self):
        client,calls=self.client(lambda model,item: observation(item,confidence=.86,decision_confidence=.8) if model==client.models[0] else observation(item))
        decision=self.decide(client)
        self.assertEqual(decision['decision'],'REVIEW')
        self.assertEqual(calls[0][0],client.models[0])
        self.assertEqual(len(calls),2)

    def test_model_prompt_contains_complete_authoritative_output_schema(self):
        from ai_judge.image_action_decision import PROMPT
        marker='OUTPUT_JSON_SCHEMA:\n'
        self.assertIn(marker,PROMPT)
        sent_schema=json.loads(PROMPT.split(marker,1)[1])
        authoritative=json.loads((Path(__file__).resolve().parents[1]/'scripts/config/schemas/image-action-decision.v2.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(sent_schema,authoritative)
        self.assertIn('schema_version',sent_schema['required'])
        self.assertFalse(sent_schema['additionalProperties'])
        from ai_judge.image_action_decision import validate
        invalid=observation(self.item);del invalid['schema_version']
        with self.assertRaises(ValueError):validate(invalid,self.item)
        invalid=observation(self.item);invalid['ownership_visual_guess']='UNKNOWN'
        with self.assertRaises(ValueError):validate(invalid,self.item)

    def test_prompt_does_not_receive_legacy_contract(self):
        import os
        from unittest.mock import patch
        client,calls=self.client(lambda m,i:observation(i))
        from ai_judge.image_action_decision import PROMPT
        client.budget._load_model_budget=lambda:None
        captured=[]
        def model_call(model,endpoint,pid,images,limit,metadata,send):
            # Inspect prompt construction without dispatching any connection.
            captured.append(metadata);return {}
        with patch.dict(os.environ,{'VLM_API_KEY':'FAKE'}),patch.object(client.budget,'model_call',side_effect=model_call):
            client._request(client.models[0],self.item,{'descriptionJson':'EXCLUDED'})
        expected=PROMPT+'\n'+json.dumps(__import__('ai_judge.client',fromlist=['safe_payload']).safe_payload(self.item,{'descriptionJson':'EXCLUDED'}),ensure_ascii=False)
        self.assertEqual(captured[0]['prompt_sha256'],hashlib.sha256(expected.encode()).hexdigest())


if __name__=='__main__':unittest.main()
