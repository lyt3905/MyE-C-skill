import unittest
from mye_c_automation.title_rewrite import rewrite_title

class TitleRulesTests(unittest.TestCase):
    def test_sop_middle_dot_lists_independent_aliases_with_same_target(self):
        for source,target in (('小比例','Small Scale'),('极小比例','Small Scale'),('迷你版','Mini'),
                              ('再版','Reissue'),('再再版','Reissue'),('D级','Deluxe'),('翻斗车','Long Haul')):
            with self.subTest(source=source):
                result=rewrite_title(self.product('NA-H74 '+source+' 威震天'),7)
                self.assertTrue(result['ok'])
                self.assertIn(target,result['titleEn'])
                self.assertLessEqual(len(result['titleEn']),120)
    def product(self,title): return {'title':title,'titleEn':'Old title','identityJson':{'logoCode':'keep'},'weight':0.2,'price':20}
    def test_shop_prefix_and_megatank(self):
        for shop,prefix in [(4,'In Stock'),(7,'Hot Sale')]:
            result=rewrite_title(self.product('NewAge NA-H74 威震天 变形玩具'),shop)
            self.assertTrue(result['ok']);self.assertTrue(result['titleEn'].startswith(prefix+' Transformation'))
            self.assertIn('Megatank',result['titleEn']);self.assertNotIn('Megatron',result['titleEn'])
            self.assertIn('NA-H74',result['titleEn']);self.assertEqual(result['modelCode'],'NA-H74')
    def test_non_transforming_and_upgrade_kit(self):
        result=rewrite_title(self.product('DNA DK-52 配件包'),7)
        self.assertTrue(result['ok']);self.assertIn('Upgrade Kit',result['titleEn']);self.assertNotIn('Transformation',result['titleEn'])
    def test_hasbro_removed_and_brand_separate(self):
        result=rewrite_title(self.product('Hasbro SS86-05 威震天'),7)
        self.assertTrue(result['ok']);self.assertNotIn('Hasbro',result['titleEn']);self.assertEqual(result['brandCode'],200017853)
    def test_compression_preserves_mandatory_words(self):
        product=self.product('Collection Space NA-H74 威震天 擎天柱 大黄蜂 红蜘蛛 原创 动画色 金属色 传世 配件包')
        result=rewrite_title(product,7)
        self.assertTrue(result['ok']);self.assertLessEqual(len(result['titleEn']),120)
        self.assertIn('NA-H74',result['titleEn']);self.assertIn('Upgrade Kit',result['titleEn'])
        self.assertTrue(result['titleEn'].endswith('Action Figures Collection Gifts'))
        self.assertEqual(product['identityJson'],{'logoCode':'keep'})
    def test_unknown_shop_and_conflicting_model_defer(self):
        self.assertFalse(rewrite_title(self.product('NA-H74 威震天'),9)['ok'])
        product=self.product('NA-H74 威震天');product['identityJson']['modelCode']='MS-01'
        self.assertFalse(rewrite_title(product,7)['ok'])
    def test_no_source_is_deferred(self):
        self.assertFalse(rewrite_title({'titleEn':'Existing'},7)['ok'])
    def test_figure_set_and_no_model_invention(self):
        result=rewrite_title(self.product('大漫匠 手办摆件周边'),4)
        self.assertTrue(result['ok']);self.assertIn('Figure Set',result['titleEn']);self.assertIsNone(result['modelCode'])
    def test_normalization(self):
        for original,expected in [('NA H74','NA-H74'),('MF35','MF-35'),('DW-E09T','DW-E09T'),('LS03F','LS03F')]:
            result=rewrite_title(self.product(original+' 威震天'),7)
            self.assertEqual(result.get('modelCode'),expected)

    def test_english_source_identity_and_boundaries(self):
        result=rewrite_title(self.product('Transformers MPM-09 Jazz birthday gift'),7)
        self.assertTrue(result['ok'])
        self.assertIn('Transformation',result['titleEn'])
        self.assertIn('Jazz',result['titleEn'])
        self.assertNotIn(' RT ',result['titleEn'])
        self.assertEqual(result['brandCode'],200017853)
        result=rewrite_title(self.product('Transformers MPM-09 Jazz Optimus Prime birthday gift'),7)
        self.assertEqual(result['decision'],'DEFERRED')
        self.assertIn('SOURCE_ROLE_CONFLICT',result['reason_codes'])
    def test_english_aliases_do_not_match_inside_words(self):
        result=rewrite_title(self.product('MPM-09 birthday Jazzy Transformersish'),7)
        self.assertTrue(result['ok'])
        self.assertNotIn(' RT ',result['titleEn'])
        self.assertNotIn(' Jazz ',result['titleEn'])
        self.assertEqual(result['brandCode'],200014695)
