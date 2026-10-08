# Zoo Tycoon 2 Unofficial Korean Patch
 
주타이쿤2 비공식 한국어 패치
* 모든 번역은 한글판 Zoo Tycoon 2의 형태와 유사하여야 합니다.
* 최대한 많은 부분을 한글화 하고자 합니다.
* 비공식도 한글화 대상입니다.
  * 비공식 파일의 z2f파일을 압축 프로그램을 사용해 ZIP형식으로 열면 "lang/1033"폴더가 있습니다.
  * 이 폴더안에 있는 모든 파일을 한글화 하면 됩니다.

## 설치법
1. Release에서 ZZZZZZKorlang[날짜].z2f 형태의 파일을 받습니다.
2. Zoo Tycoon 2가 설치된 위치에 넣습니다. 보통 "C:/Program Files (x86)/Microsoft Games/Zoo Tycoon 2"가 설치된 위치 입니다.

새로운 변경점이 발생하면 자동으로 생성됩니다.

https://cafe.naver.com/newzootycooncafe/187
이 네이버 카페글의 GaMERCaT님께서 작업하신 결과물을 누구나 수정 및 재배포가 가능하도록 배포해주신 덕분에 시작 할 수 있게 되었습니다.

## 공식 콘텐츠 번역 보충 패치

기존 한글판의 표현을 바탕으로 본편·공식 확장팩·공식 다운로드 문구를 보완한 [complete-korean](complete-korean) 모듈입니다. 같은 동물·시설의 용어와 설명을 맞추고, 주피디아의 한글·영문에 Pretendard를 적용합니다. 기존 번역과 비공식 모드 파일은 그대로 유지합니다.

1. 위의 기존 패치와 함께 릴리스의 `ZZZZZZZZ_Korlang_Complete_20261007.z2f`를 설치 폴더에 넣습니다.
2. [Pretendard](https://github.com/orioncactus/pretendard)의 정적 TTF Regular·Bold를 Windows의 모든 사용자용으로 설치합니다.
3. 게임을 다시 실행합니다. 보충 패치를 제거하려면 해당 파일만 삭제합니다.

게임 실행 파일이나 글꼴 파일은 포함하지 않습니다. 직접 빌드하려면 `python complete-korean/build_patch.py`를 실행합니다. 수정 범위·검증 상태와 상세 설치법은 [보충 패치 안내](complete-korean/README.md), 용어 기준은 [용어표](complete-korean/TERMINOLOGY.md)를 확인하십시오.
