"""Local setup tests use no live service, credential discovery or trained inference."""
import copy,hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mye_c_automation.resources import resource_path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class RuntimeReadinessTests(unittest.TestCase):
    def test_shipped_v2_policy_authorizes_twin_but_execution_stays_disabled(self):
        from mye_c_automation.automation_policy import AutomationPolicy
        policy=AutomationPolicy.load(resource_path('config/automation.v2.example.json'))
        self.assertTrue(policy.permits('REPLACE_TWIN'))
        self.assertFalse(policy.config['enabled'])

    def test_shipped_policy_reaches_formal_fake_twin_save(self):
        import test_v2_workflow as workflow
        from test_visual_versions import FIXTURE,framed_observation
        config=json.loads(resource_path('config/automation.v2.example.json').read_text())
        config['enabled']=True
        with tempfile.TemporaryDirectory() as root,patch.object(workflow,'CONFIG',config):
            s=workflow.V2WorkflowTests.scenario(self,root,['REMOVE_TEXT','KEEP'],asset_images={0:FIXTURE/'framed.bin',1:FIXTURE/'clean.bin'},observation_transform=framed_observation)
            rows=json.loads((s['root']/'auto_decisions.json').read_text())['items']
            self.assertTrue(any(r['action']=='REPLACE_TWIN' and r['decision']=='AUTO_SAFE' for r in rows))
            self.assertEqual((s['writer'].saves,s['writer'].uploads),(1,0))

    def test_legacy_template_example_resolves_packaged_bytes_and_provenance(self):
        import numpy as np
        from mye_c_automation.template_applicability import snapshot,resolve
        with tempfile.TemporaryDirectory() as root:
            snapshot(resource_path('config/template.red-store.screening.example.json'),root)
            result=resolve(root,7,required=True)
            template=Path(result['templates'][0]['path'])
            self.assertTrue(template.is_file())
            self.assertTrue(template.is_relative_to(resource_path('assets')))
            provenance=json.loads(template.with_suffix('.json').read_text())
            self.assertEqual(sha(template),provenance['sha256'])
            self.assertGreater(np.load(template,allow_pickle=False).size,0)

    def test_init_preserves_existing_config_and_disables_execution(self):
        from mye_c_automation.configuration import initialize_config
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'config';directory.mkdir()
            target=directory/'site.local.json';target.write_text('{"user":"DO_NOT_REPLACE"}')
            result=initialize_config(directory)
            self.assertEqual(target.read_text(),'{"user":"DO_NOT_REPLACE"}')
            self.assertIn('site.local.json',result['preserved'])
            policy=json.loads((directory/'automation.local.json').read_text())
            self.assertFalse(policy['enabled']);self.assertTrue(policy['allow_actions']['REPLACE_TWIN'])
            self.assertEqual(json.loads((directory/'image-options.local.json').read_text())['rights'],'RIGHTS_UNKNOWN')
            before={p.name:sha(p) for p in directory.iterdir() if p.is_file()}
            initialize_config(directory)
            self.assertEqual(before,{p.name:sha(p) for p in directory.iterdir() if p.is_file()})

    def test_offline_check_reports_missing_values_without_network_or_secret_output(self):
        from mye_c_automation.configuration import initialize_config,check_configuration
        with tempfile.TemporaryDirectory() as root,patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            initialize_config(root)
            with patch.dict(os.environ,{},clear=True):result=check_configuration(root)
            self.assertFalse(result['ready_for_readonly'])
            self.assertEqual(result['network_calls'],0)
            self.assertIn('MODEL_API_KEY_MISSING',result['blockers'])
            self.assertIn('SITE_CONFIG_INCOMPLETE',result['blockers'])

    def test_valid_readonly_config_is_not_a_live_or_write_verification(self):
        from mye_c_automation.configuration import initialize_config,check_configuration
        with tempfile.TemporaryDirectory() as root:
            initialize_config(root)
            (Path(root)/'site.local.json').write_text(json.dumps(dict(base='https://example.invalid',user='private-account',pwd='private-password')))
            with patch.dict(os.environ,{'VLM_API_KEY':'private-api-key'}):result=check_configuration(root)
            self.assertTrue(result['ready_for_readonly'])
            self.assertFalse(result['ready_for_write'])
            self.assertEqual(result['live_verification'],'NOT_RUN')
            self.assertNotIn('private-',json.dumps(result))

    def test_options_paths_bind_to_config_location(self):
        from mye_c_automation.configuration import load_image_options
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'image-options.local.json'
            path.write_text(json.dumps(dict(rights='RIGHTS_UNKNOWN',max_mask_area=.25,lama_model_path='../models/lama.pt')))
            options=load_image_options(path)
            self.assertEqual(Path(options['lama_model_path']),(path.parent/'../models/lama.pt').resolve())

    def test_partial_image_options_keep_existing_job_defaults(self):
        from mye_c_automation.configuration import load_image_options
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'options.json';path.write_text(json.dumps({'rights':'OWNED_OR_LICENSED'}))
            self.assertEqual(load_image_options(path),dict(rights='OWNED_OR_LICENSED',max_mask_area=.25))

    def test_model_installer_is_checksum_pinned_and_never_overwrites(self):
        from mye_c_automation.model_resources import install_lama
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.pt';source.write_bytes(b'FAKE_WEIGHT_NO_INFERENCE')
            target=Path(root)/'models/lama.pt'
            with self.assertRaisesRegex(ValueError,'CHECKSUM'):install_lama(source,target,'0'*64)
            self.assertFalse(target.exists())
            result=install_lama(source,target,sha(source))
            self.assertEqual(sha(target),sha(source));self.assertEqual(result['status'],'INSTALLED')
            self.assertEqual(install_lama(source,target,sha(source))['status'],'ALREADY_INSTALLED')
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'EXISTS'):install_lama(source,target,sha(source))
            self.assertEqual(target.read_bytes(),b'FAKE_WEIGHT_NO_INFERENCE')

    def test_model_binding_uses_independent_copy_and_preserves_rights(self):
        from mye_c_automation.configuration import initialize_config,bind_lama,check_configuration
        with tempfile.TemporaryDirectory() as root:
            config=Path(root)/'config';initialize_config(config)
            model=Path(root)/'models/lama.pt';model.parent.mkdir();model.write_bytes(b'FAKE')
            bind_lama(config,model,sha(model))
            options=json.loads((config/'image-options.local.json').read_text())
            self.assertEqual(options['rights'],'RIGHTS_UNKNOWN')
            self.assertEqual(options['lama_model_path'],str(model.resolve()))
            self.assertEqual(options['lama_model_sha256'],sha(model))
            model.write_bytes(b'changed')
            result=check_configuration(config)
            self.assertIn('LAMA_CHECKSUM_MISMATCH',result['blockers'])

    def test_configure_cli_runs_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as root:
            config=Path(root)/'config'
            p=subprocess.run([sys.executable,'-m','mye_c_automation','configure','init','--directory',str(config)],cwd=root,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)['status'],'INITIALIZED')
            p=subprocess.run([sys.executable,'-m','mye_c_automation','configure','check','--directory',str(config)],cwd=root,capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertFalse(json.loads(p.stdout)['ready_for_readonly'])

    def test_deployment_review_is_packaged_and_has_no_activation_claim(self):
        from mye_c_automation.deployment_review import build_review
        with tempfile.TemporaryDirectory() as root:
            result=build_review(Path(root)/'install',Path(root)/'review')
            self.assertFalse(result['write_enabled'])
            self.assertEqual(result['live_verification'],'NOT_RUN')
            self.assertTrue(Path(result['windows_helper']).is_file())
            self.assertTrue(Path(result['review_file']).is_file())

    def test_full_audit_entry_resolves_relative_model_from_options_file(self):
        from mye_c_automation import workflow_runner
        from mye_c_automation.job_manager import atomic_json
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);config=root/'config';config.mkdir()
            atomic_json(config/'options.json',dict(rights='RIGHTS_UNKNOWN',max_mask_area=.25,lama_model_path='../models/local.pt'))
            atomic_json(config/'site.json',{})
            argv=['full-audit','--pid','1','--shop','7','--site-config',str(config/'site.json'),'--model-config',str(resource_path('config/model.gateway8788.example.json')),'--image-options',str(config/'options.json'),'--root',str(root/'jobs')]
            with patch('mye_c_automation.site_client.ReadOnlySiteClient'),patch('mye_c_automation.full_product_audit.run_full_audit',return_value={'job_id':'FAKE'}) as run:
                workflow_runner.main(argv)
            self.assertEqual(run.call_args.kwargs['image_options']['lama_model_path'],str((root/'models/local.pt').resolve()))

if __name__=='__main__':unittest.main()
