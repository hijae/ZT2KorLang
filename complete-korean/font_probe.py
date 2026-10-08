"""Windows GDI의 실제 글꼴 선택을 확인합니다. 게임 화면 검증은 아닙니다.

글꼴 등록·삭제나 시스템 설정 변경 없이 메모리 DC만 사용합니다.
Python 표준 라이브러리로 실행: python font_probe.py --font system
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


FAMILIES = {'system': 'Gulim', 'pretendard': 'Pretendard'}


def probe(family, weight, text):
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
    gdi.CreateFontW.restype = wintypes.HFONT
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.GetTextFaceW.argtypes = [wintypes.HDC, ctypes.c_int, wintypes.LPWSTR]
    gdi.GetTextFaceW.restype = ctypes.c_int
    gdi.GetGlyphIndicesW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                                   ctypes.POINTER(wintypes.WORD), wintypes.DWORD]
    gdi.GetGlyphIndicesW.restype = wintypes.DWORD
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteObject.restype = wintypes.BOOL
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.DeleteDC.restype = wintypes.BOOL
    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        raise ctypes.WinError(ctypes.get_last_error())
    font = gdi.CreateFontW(-20, 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, family)
    if not font:
        gdi.DeleteDC(dc)
        raise ctypes.WinError(ctypes.get_last_error())
    previous = gdi.SelectObject(dc, font)
    try:
        selected = ctypes.create_unicode_buffer(64)
        if not gdi.GetTextFaceW(dc, len(selected), selected):
            raise ctypes.WinError(ctypes.get_last_error())
        glyphs = (wintypes.WORD * len(text))()
        if gdi.GetGlyphIndicesW(dc, text, len(text), glyphs, 1) == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        missing = ['U+%04X' % ord(char) for char, glyph in zip(text, glyphs) if glyph == 0xffff]
        match = selected.value.casefold() == family.casefold()
        if family == 'Gulim' and selected.value == '굴림':
            match = True
        return {'requested_family': family, 'selected_family': selected.value,
                'weight': weight, 'family_matches': match,
                'checked_characters': len(text), 'missing_glyphs': missing}
    finally:
        gdi.SelectObject(dc, previous)
        gdi.DeleteObject(font)
        gdi.DeleteDC(dc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', choices=tuple(FAMILIES), default='system')
    parser.add_argument('--missing-font-control', action='store_true',
                        help='설치되지 않은 시험용 이름의 대체 글꼴을 함께 기록합니다.')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Windows에서만 실행할 수 있습니다.')
    # Collect ordinary Hangul, Latin and digits used in all reviewed XML text.
    # Control characters, tags, non-BMP symbols and private-use glyphs are not
    # evidence of this Korean/Latin rendering test.
    characters = set('주피디아 관람객 Malgun Gothic Pretendard Ailuropoda melanoleuca 0123456789')
    for path in (Path(__file__).parent / 'source').rglob('*.xml'):
        root = ET.fromstring(path.read_bytes())
        for text in root.itertext():
            characters.update(c for c in text if ('가' <= c <= '힣') or ('!' <= c <= '~'))
    text = ''.join(sorted(characters))
    results = [probe(FAMILIES[args.font], weight, text) for weight in (400, 700)]
    report = {'scope': 'offscreen Windows GDI; not game or clean-PC testing',
              'font': args.font, 'results': results}
    if args.missing_font_control:
        report['missing_font_control'] = probe('ZT2_Missing_Font_Test_2608', 400, text)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(r['family_matches'] and not r['missing_glyphs'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
