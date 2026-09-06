# HydraValve Hub

유압밸브 제조사 공식 제품 페이지와 PDF를 자동 수집해 **파일명이 아니라 내용으로 검색**하는 GitHub Pages용 프로젝트입니다.

## 포함 브랜드
Bosch Rexroth, Yuken, Parker, Nachi, Tokyo Keiki, HYDAC, ATOS, HAWE, Sun Hydraulics, Danfoss, Walvoil, VALVOLE ITALIA, ARGO-HYTOS, Bucher Hydraulics.

## 검색 가능한 정보
- 모델번호 및 시리즈명
- 밸브 종류: 방향/압력/유량/체크/카운터밸런스·로드홀딩/비례·서보/카트리지/모듈러
- 압력(bar, psi)
- 유량(L/min, LPM, GPM)
- 전압(12/24/48/110/120/220/230 V, AC/DC)
- NG/CETOP/D02~D08/ISO 4401 표현
- 일부 포트 및 캐비티 표기

## GitHub에 올리는 순서
1. 새 GitHub 저장소를 만듭니다.
2. 이 폴더의 **내용 전체**를 저장소 루트에 업로드합니다.
3. 기본 브랜치를 `main`으로 둡니다.
4. 저장소 `Settings → Pages → Source`를 **GitHub Actions**로 선택합니다.
5. `Actions` 탭에서 `Update hydraulic catalog and deploy Pages`를 한 번 수동 실행합니다.
6. 이후 매일 자동으로 공식 제조사 자료를 다시 확인하고 검색 색인을 갱신합니다.

## 자동수집 방식
`sources.json`에 등록된 공식 제조사 도메인만 대상으로 합니다. `scripts/crawl.py`는 robots.txt를 확인하고, 요청 간격/문서 용량/페이지 수를 제한합니다. HTML과 PDF 텍스트에서 모델번호와 주요 사양을 추출해 `data/catalog.json`을 생성합니다.

사이트는 원본 PDF 파일 자체를 호스팅하지 않고 **검색용 색인·요약·공식 원본 URL**을 저장합니다.

## 주의
- 제조사 사이트 구조가 바뀌면 해당 브랜드의 시작 URL 또는 추출 규칙 수정이 필요할 수 있습니다.
- 자바스크립트로만 렌더링되는 검색 시스템이나 로그인 필요 자료는 일반 크롤러로 수집되지 않을 수 있습니다.
- 스캔 이미지 PDF는 OCR이 없으면 본문 추출이 제한됩니다. 추후 OCR 워크플로를 별도로 추가할 수 있습니다.
- 최종 제품 선정/설계에는 반드시 제조사 최신 원본 데이터시트를 확인하세요.
