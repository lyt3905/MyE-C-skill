"""Generate a local deployment review; never provision users, ACLs or services."""
import json
import shutil
from pathlib import Path
from mye_c_automation.resources import resource_path

def build_review(install_root,output_directory):
    install_root=Path(install_root).expanduser().resolve();output=Path(output_directory).expanduser().resolve()
    if install_root==Path(install_root.anchor):raise ValueError('INSTALL_ROOT_CANNOT_BE_DRIVE_ROOT')
    output.mkdir(parents=True,exist_ok=True)
    helper=output/'New-ExecutorDeploymentReview.ps1'
    if not helper.exists():shutil.copyfile(resource_path('assets/deployment/New-ExecutorDeploymentReview.ps1'),helper)
    report=output/'deployment-review.json'
    result=dict(schema='automation-deployment-review/v1',install_root=str(install_root),write_enabled=False,
        live_verification='NOT_RUN',windows_helper=str(helper),review_file=str(report),
        pending=['Configure independent accounts, secrets and data paths','Run doctor/configure check locally','Use the Windows review helper to resolve explicit account SIDs',
            'Complete existing executor deployment_preflight and cross-account probes','Obtain separate real-readonly and real-write authorization'],
        existing_preflight_module='mye_c_automation.executor.deployment_preflight')
    with report.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    return result
