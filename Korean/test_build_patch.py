"""글꼴 선택 및 매니페스트 변조 거부 검사. python -m unittest discover -s Korean"""

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import build_patch as builder


FONT_KEYS = {'font': {'name'}, 'BFFont': {'name', 'font'},
             'appearance': {'fontName'}, 'textEdit': {'fontName'}}


def font_faces(data):
    return [node.get(key) for node in ET.fromstring(data).iter()
            for key in FONT_KEYS.get(node.tag, ()) if node.get(key)]


def font_independent_tree(data):
    root = ET.fromstring(data)
    for node in root.iter():
        for key in FONT_KEYS.get(node.tag, ()):
            if key in node.attrib:
                node.set(key, 'FONT_FAMILY')
    return ET.tostring(root, encoding='utf-8')


class FontBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.verified = builder.validate_sources()

    def test_default_has_only_system_font(self):
        faces = Counter(face for _, data in self.verified for face in font_faces(data))
        self.assertGreater(faces['Gulim'], 0)
        self.assertEqual(set(faces), {'Gulim'})

    def test_pretendard_changes_only_font_attributes(self):
        selected = builder.select_font(self.verified, 'pretendard')
        self.assertEqual([n for n, _ in selected], [n for n, _ in self.verified])
        for (name, old), (_, new) in zip(self.verified, selected):
            with self.subTest(file=name):
                self.assertEqual(font_independent_tree(old), font_independent_tree(new))
                self.assertTrue(all(face == 'Pretendard' for face in font_faces(new)))

    def test_original_explicit_font_files_are_covered(self):
        names = {n.casefold() for n, _ in self.verified}
        root = builder.PACKAGE.parent
        for path in (root / 'lang').rglob('*.xml'):
            try:
                original = path.read_bytes()
                faces = font_faces(original)
            except ET.ParseError:
                # Two pre-existing invalid files have no font tags. They are
                # outside this font update; do not silently approve new errors.
                self.assertNotIn(b'<font', original)
                continue
            if faces:
                self.assertIn(path.relative_to(root).as_posix().casefold(), names)

    def test_combined_archive_preserves_original_files_and_overrides(self):
        combined = dict(builder.merge_base_sources(self.verified, self.manifest))
        overlay = {n.casefold(): data for n, data in self.verified}
        self.assertEqual(len(combined), 485)
        self.assertEqual(len({n.casefold() for n in combined}), 485)
        for name, data in self.verified:
            self.assertEqual(combined[name], data)
        for record in self.manifest['base_files']:
            if record['path'].casefold() not in overlay:
                self.assertEqual(combined[record['path']],
                                 (builder.REPOSITORY / record['path']).read_bytes().replace(b'\r\n', b'\n'))

    def test_changed_original_xml_baseline_is_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest['base_files'][0]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            builder.merge_base_sources(self.verified, manifest)

    def test_release_filename_matches_upstream_and_requested_date(self):
        self.assertEqual(builder.release_filename('2026-10-08', 'system'),
                         'ZZZZZZKorlang2026-10-08.z2f')
        self.assertEqual(builder.release_filename('2026-10-08', 'pretendard'),
                         'ZZZZZZKorlang2026-10-08-Pretendard.z2f')
        with self.assertRaises(ValueError):
            builder.release_filename('../2026-10-08', 'system')

    def test_official_titles_and_generic_dinosaur_sentence(self):
        files = dict(self.verified)
        product = ET.fromstring(files['lang/1033/pdlc1_filtertext.xml'])
        self.assertEqual(next(n for n in product.iter('LOC_STRING')
                              if n.get('_locID') == 'FilterText:s_Product_PDLC1').text,
                         'Dino Danger Pack')
        text = ''.join(ET.fromstring(files['lang/1033/CP2_gameplay_entries.xml']).itertext())
        self.assertIn('위험한 공룡을 마취', text)

    def test_font_scaling_and_existing_save_setting(self):
        locale = ET.fromstring(dict(self.verified)['config/locale.xml'])
        self.assertEqual(locale.get('MaxFontScalingResolution'), '20000')
        self.assertEqual(locale.get('disableTextEditExtension'), 'true')

    def test_toc_has_one_directory_and_consistent_download_nodes(self):
        files = dict(self.verified)
        config = ET.fromstring(files['ui/zoopedia/config.xml'])
        self.assertEqual([n.get('name') for n in config.iter('dir')],
                         ['ui/zoopedia/korean_entries'])
        toc = [(n, b) for n, b in self.verified if '/korean_entries/' in n]
        self.assertEqual(len(toc), 69)
        orders = {}
        for _, data in toc:
            for node in ET.fromstring(data).iter('BFHelpEntry'):
                entry = node.get('entry')
                order = node.get('order', entry)
                self.assertEqual(orders.setdefault(entry, order), order)
        self.assertEqual(orders['zoopedia_home'], 'zoopedia_home')
        self.assertEqual(len(orders), 668)
        for entry in ('zoopedia_elephantasian', 'zoopedia_leopardblack',
                      'zoopedia_muskox'):
            self.assertTrue(orders[entry].startswith('zoopedia_ko_'))

    def test_heading_breaks_title_position_and_tooltip_terms(self):
        files = dict(self.verified)
        headings = []
        for name, data in self.verified:
            if not name.startswith('lang/'):
                continue
            for font in ET.fromstring(data).iter('font'):
                br = font.find('br')
                if br is not None and br.tail == '재밌는 사실':
                    self.assertTrue(font.text.endswith('에 대한'))
                    headings.append(font.text)
        self.assertEqual(len(headings), 177)
        self.assertIn('흰코뿔소에 대한', headings)
        self.assertNotIn('동물원 백과사전', files['lang/1033/aa_ui.xml'].decode('utf-8'))
        layout = ET.fromstring(files['ui/layout/zoopedia.xml'])
        label = next(n for n in layout.iter('UIText')
                     if n.get('name') == 'zoopedia_label')
        self.assertEqual(label.find('UIRegion').get('y'), '16')
        self.assertEqual(label.find('./UIAspect/default/BFFont').get('align'), 'center')


class ManifestRejectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=builder.PACKAGE)
        self.package = Path(self.temp.name)
        self.workspace = builder.PACKAGE.resolve()
        shutil.copytree(builder.PACKAGE / 'source', self.package / 'source')
        self.manifest = json.loads((builder.PACKAGE / 'manifest.json').read_text(encoding='utf-8'))
        self.override = patch.object(builder, 'PACKAGE', self.package)
        self.override.start()

    def tearDown(self):
        self.override.stop()
        if not self.package.resolve().is_relative_to(self.workspace):
            raise ValueError('Test cleanup escaped its package directory')
        self.temp.cleanup()

    def save_manifest(self):
        (self.package / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def reject(self):
        self.save_manifest()
        with self.assertRaises((ValueError, ET.ParseError)):
            builder.validate_sources()

    def edit_record(self, edit, needs_reference=False):
        for record in self.manifest['files']:
            path = self.package / 'source' / record['source_path']
            root = ET.fromstring(path.read_bytes())
            if needs_reference:
                candidates = [(node, key) for node in root.iter()
                              for key in node.attrib if key in builder.REFERENCE_ATTRIBUTES]
                if not candidates:
                    continue
                node, key = candidates[0]
                node.set(key, 'changed-resource-reference')
            else:
                node = next((n for n in root.iter('LOC_STRING') if n.get('_locID')), None)
                if node is None:
                    continue
                edit(node)
            changed = ET.tostring(root, encoding='utf-8')
            path.write_bytes(changed)
            # Retain semantic baselines, but refresh byte fields so these tests
            # exercise ID/token/reference checks rather than just hash mismatch.
            record.update(bytes=len(changed), sha256=builder.sha256(changed))
            return
        self.fail('No suitable XML for negative test')

    def test_invalid_xml(self):
        record = self.manifest['files'][0]
        (self.package / 'source' / record['source_path']).write_bytes(b'<broken>')
        self.reject()

    def test_unregistered_file(self):
        (self.package / 'source' / 'lang/1033/unregistered.xml').write_text('<ZT2Strings/>')
        self.reject()

    def test_path_traversal(self):
        self.manifest['files'][0]['source_path'] = '../escape.xml'
        self.reject()

    def test_id_change(self):
        self.edit_record(lambda n: n.set('_locID', 'unexpected:id'))
        self.reject()

    def test_format_token_change(self):
        self.edit_record(lambda n: setattr(n, 'text', (n.text or '') + '%1s'))
        self.reject()

    def test_reference_change(self):
        self.edit_record(None, needs_reference=True)
        self.reject()


if __name__ == '__main__':
    unittest.main()
