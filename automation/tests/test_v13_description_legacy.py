import tempfile
import unittest
from pathlib import Path
from mye_c_automation import audit_one
from mye_c_automation import auto_deletions
from mye_c_automation import approved_deletions
from mye_c_automation import site_client
from mye_c_automation import description_refs
from mye_c_automation.apply_token_plan import execute_plan, compile_mutation, ApplyError
from mye_c_automation.token_opt_plan import PlanError
import test_token_opt


class OpaqueBomb:
    def get(self,*args):raise AssertionError('fixed value must not be read')
    def __deepcopy__(self,memo):raise AssertionError('fixed value must not be parsed or copied by obsolete tools')
    def __str__(self):raise AssertionError('fixed value must not be stringified')


class LegacyDescriptionScopeTests(unittest.TestCase):
    def test_obsolete_helpers_reject_before_reading_the_fixed_value(self):
        opaque=OpaqueBomb()
        calls=[(audit_one.description_checks,(opaque,[])),(auto_deletions.deletion_description,(opaque,set(),{})),
               (approved_deletions.remove_description_images,(opaque,set())),(site_client.remap_description,(opaque,{})),
               (site_client.prune_description,(opaque,[])),(description_refs.parse_description,(opaque,)),
               (description_refs.apply_exact_description_ops,(opaque,{},lambda _:self.fail('no resolver')))]
        for function,args in calls:
            with self.subTest(function=function.__name__),self.assertRaisesRegex(ValueError,'DESCRIPTION_OPERATION_FORBIDDEN'):
                function(*args)

    def test_legacy_preview_rejects_description_plan_before_reading_site(self):
        product=test_token_opt.product_fixture();plan=test_token_opt.plan_fixture(product)
        plan['desired']['description']={'remove':[]}
        class Site:
            calls=0
            def product(self,pid):self.calls+=1;return product
        site=Site()
        with tempfile.TemporaryDirectory() as root,self.assertRaisesRegex(PlanError,'DESCRIPTION_OPERATION_FORBIDDEN'):
            execute_plan(site,plan,Path(root)/'plan.json')
        self.assertEqual(site.calls,0)

    def test_direct_legacy_compiler_refuses_before_resolving_or_reading_description(self):
        product=test_token_opt.product_fixture();product['descriptionJson']=OpaqueBomb()
        plan=test_token_opt.plan_fixture(test_token_opt.product_fixture());plan['desired']['description']={}
        with self.assertRaisesRegex(ApplyError,'DESCRIPTION_OPERATION_FORBIDDEN'):
            compile_mutation(product,plan,lambda _:self.fail('no resolver'))
