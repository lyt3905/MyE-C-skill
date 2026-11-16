"""Desktop presentation delegates to the existing CLI; no live service access."""
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path

class DesktopInterfaceTests(unittest.TestCase):
    def test_fake_command_is_the_existing_cli_with_explicit_independent_data(self):
        from mye_c_automation.desktop_data import fake_command
        with tempfile.TemporaryDirectory() as root:
            argv=fake_command('repair',Path(root)/'data')
            self.assertEqual(argv[:4],[sys.executable,'-u','-m','mye_c_automation'])
            self.assertEqual(argv[4:7],['fake','--scenario','repair'])
            self.assertEqual(Path(argv[-1]),(Path(root)/'data').resolve())
            with self.assertRaises(ValueError):fake_command('auto_apply',root)

    def test_connection_form_save_preserves_policy_and_model_options(self):
        from mye_c_automation.configuration import initialize_config
        from mye_c_automation.desktop_data import load_connection_form,save_connection_form
        with tempfile.TemporaryDirectory() as root:
            initialize_config(root);root=Path(root)
            before=(root/'automation.local.json').read_bytes()
            form=load_connection_form(root)
            save_connection_form(root,dict(base='https://example.invalid',user='account',pwd='password',gateway='http://127.0.0.1:8788/v1'),form['revisions'])
            self.assertEqual((root/'automation.local.json').read_bytes(),before)
            self.assertEqual(json.loads((root/'model.local.json').read_text())['models'],['deepseek-v4.1-flash'])
            self.assertEqual(json.loads((root/'site.local.json').read_text())['pwd'],'password')

    def test_connection_form_conflict_never_overwrites_newer_user_edit(self):
        from mye_c_automation.configuration import initialize_config
        from mye_c_automation.desktop_data import load_connection_form,save_connection_form
        with tempfile.TemporaryDirectory() as root:
            initialize_config(root);root=Path(root);form=load_connection_form(root)
            path=root/'site.local.json';path.write_text(json.dumps(dict(base='https://changed.invalid',user='new',pwd='new')))
            current=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'CONFIG_CHANGED'):
                save_connection_form(root,dict(base='https://example.invalid',user='old',pwd='old',gateway='http://127.0.0.1:8788/v1'),form['revisions'])
            self.assertEqual(path.read_bytes(),current)

    def test_gui_environment_key_is_process_only_and_not_saved_in_form(self):
        from mye_c_automation.desktop_data import worker_environment
        before=dict(os.environ);env=worker_environment('GUI_PRIVATE_KEY')
        self.assertEqual(env['VLM_API_KEY'],'GUI_PRIVATE_KEY')
        self.assertEqual(dict(os.environ),before)
        self.assertEqual(env['PYTHONIOENCODING'],'utf-8')

    def test_windowless_launcher_uses_console_interpreter_for_captured_cli(self):
        from unittest.mock import patch
        from mye_c_automation.desktop_data import fake_command
        windowless=str(Path(sys.executable).with_name('pythonw.exe'))
        with patch('mye_c_automation.desktop_data.sys.executable',windowless):
            self.assertEqual(fake_command('twin',Path.cwd())[0],str(Path(windowless).with_name('python.exe')))

    def test_job_history_handles_incomplete_jobs_and_rejects_outside_ids(self):
        from mye_c_automation.desktop_data import list_jobs,load_job
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'jobs/JOB_abc';folder.mkdir(parents=True)
            (folder/'job.json').write_text(json.dumps(dict(job_id='JOB_abc',pid=1,shop_id=7)))
            (folder/'state.json').write_text(json.dumps(dict(state='CREATED')))
            (folder/'other.tmp').write_text('not evidence')
            rows=list_jobs(root)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['state'],'CREATED')
            self.assertIsNone(load_job(root,'JOB_abc')['result'])
            with self.assertRaises(ValueError):load_job(root,'../outside')

    def test_picture_pairs_use_approved_sha_and_local_files_without_downloading(self):
        from mye_c_automation.desktop_data import image_pairs
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);before=root/'before.bin';before.write_bytes(b'BEFORE');after=root/'after.bin';after.write_bytes(b'AFTER')
            a=hashlib.sha256(before.read_bytes()).hexdigest();b=hashlib.sha256(after.read_bytes()).hexdigest()
            (root/'full_inventory.json').write_text(json.dumps(dict(contents={a:dict(file=str(before)),b:dict(file=str(after))})))
            (root/'auto_decisions.json').write_text(json.dumps(dict(items=[dict(action='REPLACE_TWIN',decision='AUTO_SAFE',target=dict(pool='main',index=0),source=dict(original_sha256=a,sha256=b))])))
            pairs=image_pairs(root)
            self.assertEqual((pairs[0]['before'],pairs[0]['after']),(str(before),str(after)))
            after.write_bytes(b'CHANGED')
            with self.assertRaisesRegex(ValueError,'IMAGE_BYTES_CHANGED'):image_pairs(root)

    def test_uncertain_job_does_not_show_as_success(self):
        from mye_c_automation.desktop_data import status_label
        self.assertIn('未知',status_label('APPLY_UNKNOWN'))
        self.assertIn('部分',status_label('PARTIALLY_AUTO_FIXED'))
        self.assertNotEqual(status_label('DEFERRED'),status_label('AUTO_VERIFIED'))

    def test_real_tk_window_runs_fake_worker_and_displays_bound_pair(self):
        import time,tkinter as tk
        from mye_c_automation.desktop import DesktopApp
        from mye_c_automation.configuration import initialize_config
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);initialize_config(root/'config')
            window=tk.Tk();window.withdraw();app=DesktopApp(window,root/'config',root/'data')
            try:
                self.assertEqual(len(app.tabs.tabs()),3)
                app.start_fake();deadline=time.monotonic()+30
                while app.worker is not None and time.monotonic()<deadline:window.update();time.sleep(.02)
                self.assertIsNone(app.worker,'Fake worker did not finish')
                self.assertTrue(app.last_job_id)
                self.assertTrue(app.pairs)
                self.assertTrue(str(app.before_label.cget('image')))
                self.assertTrue(str(app.after_label.cget('image')))
                self.assertIn('验证通过',app.status.get())
            finally:window.destroy()

if __name__=='__main__':unittest.main()
