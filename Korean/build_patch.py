"""기존 번역과 검증된 보완 XML을 묶는 주타이쿤 2 한국어 패치 빌더.

Python 3.9 이상과 표준 라이브러리만 사용합니다. 게임이나 네트워크에는
접근하지 않습니다. manifest.json은 보완판 source 파일의 기준이며 기존판은 사용하지 않습니다.
"""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


PACKAGE = Path(__file__).resolve().parent
REPOSITORY = PACKAGE.parent
RELEASE_DATE = "2026-10-11"
OUTPUT_NAME = "ZZZZZZKorlang" + RELEASE_DATE + "-Complete-Gulim.z2f"
PRETENDARD_OUTPUT_NAME = "ZZZZZZKorlang" + RELEASE_DATE + "-Complete-Pretendard.z2f"
FONT_FAMILIES = {"system": "Gulim", "pretendard": "Pretendard"}
EXPECTED_FILES = 431
EXPECTED_LANGUAGE_FILES = 332
EXPECTED_UI_FILES = 97
EXPECTED_CONFIG_FILES = 2
EXPECTED_BASE_FILES = 364
EXPECTED_ARCHIVE_FILES = 485
FIXED_TIMESTAMP = (2026, 10, 10, 0, 0, 0)
TOKEN_PATTERN = re.compile(
    r"%[A-Za-z_][A-Za-z0-9_]*%|%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[sdifugx]|\{\d+\}"
)
REFERENCE_ATTRIBUTES = frozenset({
    "src", "href", "image", "bgimg", "locid", "short", "long", "help",
    "msg", "data", "file", "modelfile", "template", "templateName", "ids",
    "opener", "sound", "cursor", "format", "fmt", "posformat",
})


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def signature(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return sha256(encoded)


def xml_facts(data):
    """태그, ID, 실행 형식 토큰, 리소스 참조의 정적 검증값을 계산합니다."""
    root = ET.fromstring(data)
    nodes = list(root.iter())
    ids = []
    references = []
    formats = []
    structure = []
    loc_count = 0
    for index, node in enumerate(nodes):
        structure.append([index, node.tag, sorted(node.attrib.items()), len(node)])
        if node.tag == "LOC_STRING":
            loc_count += 1
            if not node.get("_locID"):
                raise ValueError("_locID가 없는 LOC_STRING입니다.")
        for key, value in sorted(node.attrib.items()):
            if key in ("_locID", "locid", "id", "ids", "version"):
                ids.append([index, key, value])
            if key in REFERENCE_ATTRIBUTES:
                references.append([index, key, value])
        values = [("text", node.text), ("tail", node.tail)]
        values.extend(("attribute:" + key, value)
                      for key, value in sorted(node.attrib.items()))
        for field, value in values:
            found = TOKEN_PATTERN.findall(value or "")
            if found:
                formats.append([index, field, found])
    return {
        "bytes": len(data),
        "sha256": sha256(data),
        "node_count": len(nodes),
        "loc_string_count": loc_count,
        "id_signature_sha256": signature(ids),
        "format_token_signature_sha256": signature(formats),
        "reference_signature_sha256": signature(references),
        "structure_attribute_signature_sha256": signature(structure),
    }


def validate_path(name):
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("허용되지 않은 XML 경로입니다.")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name:
        raise ValueError("허용되지 않은 XML 경로입니다: " + name)
    if path.suffix != ".xml":
        raise ValueError("XML 파일만 허용합니다: " + name)
    if not (name.startswith("lang/1033/") or path.parts[0].lower() == "ui"
            or name in ("config/imeui.xml", "config/locale.xml")):
        raise ValueError("언어/UI 폴더와 지정된 IME 글꼴 XML만 허용합니다: " + name)
    return path


def validate_sources():
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("output_name") != OUTPUT_NAME:
        raise ValueError("지원하지 않는 매니페스트입니다.")
    records = manifest.get("files", [])
    if len(records) != EXPECTED_FILES:
        raise ValueError("검증 대상은 정확히 431개 XML이어야 합니다.")
    names = [record["path"] for record in records]
    source_names = [record.get("source_path", record["path"]) for record in records]
    if len(set(names)) != len(names) or len(set(name.casefold() for name in names)) != len(names):
        raise ValueError("매니페스트에 중복 경로가 있습니다.")
    if len(set(source_names)) != len(source_names):
        raise ValueError("매니페스트에 중복 소스 경로가 있습니다.")
    for name in names + source_names:
        validate_path(name)
    language_count = sum(name.startswith("lang/1033/") for name in names)
    ui_count = sum(PurePosixPath(name).parts[0].lower() == "ui" for name in names)
    config_count = sum(name.startswith("config/") for name in names)
    if (language_count != EXPECTED_LANGUAGE_FILES or ui_count != EXPECTED_UI_FILES
            or config_count != EXPECTED_CONFIG_FILES):
        raise ValueError("언어 XML 332개, UI XML 97개와 설정 XML 2개가 필요합니다.")
    if (manifest.get("language_xml_files") != language_count
            or manifest.get("ui_xml_files") != ui_count
            or manifest.get("config_xml_files") != config_count
            or manifest.get("total_xml_files") != len(names)):
        raise ValueError("매니페스트의 구성별 파일 수가 일치하지 않습니다.")
    if not re.fullmatch(r"[a-f0-9]{64}", manifest.get("reviewed_candidate_sha256", "")):
        raise ValueError("검토한 후보의 SHA256이 없습니다.")
    source = PACKAGE / "source"
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source 폴더가 없거나 심볼릭 링크입니다.")
    source = source.resolve()
    actual_files = set()
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("source의 심볼릭 링크는 허용하지 않습니다.")
        if path.is_file():
            actual_files.add(path.relative_to(source).as_posix())
    if actual_files != set(source_names):
        missing = sorted(set(source_names) - actual_files)
        extra = sorted(actual_files - set(source_names))
        raise ValueError("source 파일 목록이 다릅니다. 누락=%s 추가=%s" % (missing, extra))
    verified = []
    total_loc_strings = 0
    for record in records:
        name = record["path"]
        source_name = record.get("source_path", name)
        path = source.joinpath(*PurePosixPath(source_name).parts)
        if not path.resolve().is_relative_to(source):
            raise ValueError("source 밖의 경로입니다: " + name)
        data = path.read_bytes()
        facts = xml_facts(data)
        for key, value in facts.items():
            if record.get(key) != value:
                raise ValueError("검증값 불일치: %s (%s)" % (name, key))
        total_loc_strings += facts["loc_string_count"]
        verified.append((name, data))
    if manifest.get("loc_string_count") != total_loc_strings:
        raise ValueError("LOC_STRING 총수가 기준과 다릅니다.")
    return manifest, verified


def select_font(verified, font):
    """글꼴 선택은 검증된 XML의 글꼴 속성만 변경합니다."""
    family = FONT_FAMILIES[font]
    if font == "system":
        return verified
    result = []
    for name, data in verified:
        # source uses double-quoted XML attributes, validated by manifest.
        changed = re.sub(rb'\b(name|font|fontName)="Gulim"',
                         lambda match: match[1] + b'="' + family.encode('ascii') + b'"', data)
        before, after = ET.fromstring(data), ET.fromstring(changed)
        for old, new in zip(before.iter(), after.iter()):
            allowed = {"font": {"name"}, "BFFont": {"name", "font"},
                       "appearance": {"fontName"}, "textEdit": {"fontName"}}.get(old.tag, set())
            for key in set(old.attrib) | set(new.attrib):
                if old.get(key) != new.get(key):
                    if not (key in allowed and old.get(key) == FONT_FAMILIES['system']
                            and new.get(key) == family):
                        raise ValueError("글꼴 외의 속성이 변경되었습니다: " + name)
        result.append((name, changed))
    return result


def load_legacy_sources():
    """현재 lang/config의 일반 파일을 경로만 검사하고 바이트 그대로 읽습니다.

    매니페스트, 파일 개수, 해시, XML 구문 및 줄바꿈 변환에 의존하지 않습니다.
    디렉터리 링크도 순회 전에 거부하여 저장소 밖 파일이나 순환을 방지합니다.
    """
    repository = REPOSITORY.resolve()
    files = []
    seen = set()

    def visit(source):
        if (source.is_symlink() or getattr(source, 'is_junction', lambda: False)()
                or not source.resolve().is_relative_to(repository)):
            raise ValueError('기존판 경로가 링크이거나 저장소 밖입니다: ' + str(source))
        name = source.relative_to(REPOSITORY).as_posix()
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or str(path) != name
                or '\\' in name or ':' in name or path.parts[0] not in ('lang', 'config')):
            raise ValueError('기존판 경로가 허용되지 않습니다: ' + name)
        if source.is_dir():
            for child in sorted(source.iterdir()):
                visit(child)
        elif source.is_file():
            if name.casefold() in seen:
                raise ValueError('기존판에 중복 경로가 있습니다: ' + name)
            seen.add(name.casefold())
            files.append((name, source.read_bytes()))
        else:
            raise ValueError('기존판 경로가 일반 파일/폴더가 아닙니다: ' + name)

    for folder in ('lang', 'config'):
        visit(REPOSITORY / folder)
    return sorted(files)


def load_base_sources(manifest):
    """기존 lang/config만 검증하여 읽습니다. UI 보완은 포함하지 않습니다."""
    records = manifest.get('base_files', [])
    if len(records) != EXPECTED_BASE_FILES:
        raise ValueError('기존 XML 기준은 정확히 364개이어야 합니다.')
    actual = {path.relative_to(REPOSITORY).as_posix()
              for folder in ('lang', 'config')
              for path in (REPOSITORY / folder).rglob('*.xml')}
    names = [r['path'] for r in records]
    if actual != set(names) or len({n.casefold() for n in names}) != len(names):
        raise ValueError('기존 XML 파일 목록이 기준과 다릅니다.')
    merged = {}
    for record in records:
        name = record['path']
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or str(path) != name
                or '\\' in name or ':' in name or path.suffix != '.xml'
                or path.parts[0] not in ('lang', 'config')):
            raise ValueError('기존 XML 경로가 허용되지 않습니다: ' + name)
        source = REPOSITORY.joinpath(*path.parts)
        if source.is_symlink() or not source.resolve().is_relative_to(REPOSITORY.resolve()):
            raise ValueError('기존 XML 경로가 저장소 밖으로 나갑니다: ' + name)
        # Git checkout line endings differ between Windows and Linux.
        # Normalize only CRLF; original XML text and attributes are preserved.
        data = source.read_bytes().replace(b'\r\n', b'\n')
        if sha256(data) != record['sha256']:
            raise ValueError('기존 XML 해시가 기준과 다릅니다: ' + name)
        merged[name.casefold()] = (name, data)
    return sorted(merged.values())


def merge_base_sources(verified, manifest):
    merged = {n.casefold(): (n, d) for n, d in load_base_sources(manifest)}
    for name, data in verified:
        merged[name.casefold()] = (name, data)
    if len(merged) != EXPECTED_ARCHIVE_FILES:
        raise ValueError('통합 배포에는 XML 485개가 필요합니다.')
    return sorted(merged.values())


def apply_ui_weight(files, font):
    """굴림 메뉴 UI만 보정합니다. 기존 강조를 유지하고 동적 서식의 중첩을 피합니다.

    소스 매니페스트 검증 후 수행되는 재현 가능한 변환입니다.
    주피디아 본문 및 패키지 밖 게임 UI의 전체 굵기 보정은 아닙니다.
    """
    if font != 'system':
        return files
    def bf(match):
        tag = match.group()
        if re.search(rb'\bbold="[^"]*"', tag):
            return re.sub(rb'\bbold="[^"]*"', b'bold="1"', tag)
        return tag.replace(b'<BFFont', b'<BFFont bold="1"', 1)
    def rich(match):
        body = match.group(1)
        # Existing partial emphasis must retain its scope. Runtime substitutions
        # may themselves contain markup, so do not wrap their enclosing font.
        if re.search(rb'<b(?:\s|>)|<font\b|%[A-Za-z_][A-Za-z0-9_]*%', body):
            return match.group()
        opening = match.group().index(b'>') + 1
        return match.group()[:opening] + b'<b>' + body + b'</b></font>'
    result = []
    for name, data in files:
        lower = name.replace('\\', '/').lower()
        if lower.startswith('ui/') and lower.endswith('.xml'):
            data = re.sub(rb'<BFFont\b[^>]*>', bf, data)
        elif lower.startswith('lang/') and (lower.endswith('/ui.xml') or lower.endswith('_ui.xml')):
            data = re.sub(rb'<font\b[^>]*>(.*?)</font>', rich, data, flags=re.S)
        result.append((name, data))
    return result


def release_filename(release_date, font, edition='complete'):
    if date.fromisoformat(release_date).isoformat() != release_date:
        raise ValueError('릴리스 날짜는 YYYY-MM-DD 형식이어야 합니다.')
    if edition not in ('legacy', 'complete') or font not in FONT_FAMILIES:
        raise ValueError('지원하지 않는 배포판 또는 글꼴입니다.')
    if edition == 'legacy':
        if font != 'system':
            raise ValueError('기존판에는 글꼴 변환을 적용하지 않습니다.')
        suffix = ''
    else:
        suffix = '-Complete-Gulim' if font == 'system' else '-Complete-Pretendard'
    return 'ZZZZZZKorlang' + release_date + suffix + '.z2f'


def build_patch(verified, font="system", release_date=RELEASE_DATE, edition="complete"):
    output_name = release_filename(release_date, font, edition)
    destination = PACKAGE / output_name
    temporary = PACKAGE / (output_name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            for name, data in verified:
                info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0o600 << 16
                archive.writestr(info, data, compresslevel=9)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("생성한 패치의 CRC 검증에 실패했습니다.")
            if archive.namelist() != [name for name, _ in verified]:
                raise ValueError("생성한 패치의 파일 목록이 다릅니다.")
            for name, data in verified:
                if archive.read(name) != data:
                    raise ValueError("생성한 패치의 XML 내용이 다릅니다: " + name)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="검증만 하고 패치를 생성하지 않습니다.")
    parser.add_argument("--font", choices=tuple(FONT_FAMILIES), default="system",
                        help="기본값 system: 기존 한국어 패치의 굴림. pretendard: 별도 설치 필요.")
    parser.add_argument('--date', default=RELEASE_DATE, help='릴리스 파일명 날짜: YYYY-MM-DD')
    parser.add_argument("--edition", choices=("legacy", "complete"), default="complete",
                        help="legacy: 원본 lang/config, complete: 공식 콘텐츠 보완 통합판")
    args = parser.parse_args()
    try:
        release_filename(args.date, args.font, args.edition)
        if args.edition == 'legacy':
            verified = load_legacy_sources()
        else:
            manifest, verified = validate_sources()
            print("검증 완료: XML %d개, LOC_STRING %d개" % (len(verified), manifest["loc_string_count"]))
            verified = select_font(verified, args.font)
            verified = merge_base_sources(verified, manifest)
            verified = apply_ui_weight(verified, args.font)
        print("배포판: %s, 파일 %d개" % (args.edition, len(verified)))
        if not args.check:
            destination = build_patch(verified, args.font, args.date, args.edition)
            print("생성 완료: " + destination.name)
            print("SHA256: " + sha256(destination.read_bytes()))
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        print("빌드 실패: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
