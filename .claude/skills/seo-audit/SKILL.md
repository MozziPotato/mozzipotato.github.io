---
name: seo-audit
description: 블로그 검색엔진 노출 최적화(SEO) 상태를 전체 점검합니다 (구글, 네이버, 다음, 빙)
disable-model-invocation: false
---

# SEO 전체 점검 스킬

블로그의 검색엔진 노출 최적화 상태를 사이트 인프라, 포스트, 사이트 구조 3개 레벨로 점검합니다.
애드센스 수익화 블로그 관점에서 구글, 네이버, 다음, 빙 노출에 필요한 항목을 검토합니다.

## 실행 절차

1. **사이트 인프라 점검** (A 레벨)
2. **포스트 레벨 점검** (B 레벨) — 모든 포스트 대상
3. **사이트 구조 점검** (C 레벨) — 포스트 간 관계
4. 결과를 레벨별로 출력하고 개선 제안을 제시

## 입력

`$ARGUMENTS` — 없으면 전체 점검, 포스트 경로를 주면 해당 포스트만 B 레벨 점검

예시:
- `/seo-audit` (전체 점검)
- `/seo-audit blog/content/posts/20260419-xxx.md` (특정 포스트만)

---

## A. 사이트 인프라 체크리스트

사이트 전체에 영향을 미치는 설정들. 한 번 세팅하면 잘 안 바뀌므로 정기 점검 시 확인.

### A-1. hugo.toml 기본 설정
- `baseURL`이 실제 배포 URL과 일치하는지 (`https://mozzipotato.github.io/`)
- `languageCode = "ko"` 설정 여부
- `enableRobotsTXT = true` 설정 여부
- sitemap 설정 존재 여부 (`changefreq`, `priority`)

### A-2. robots.txt
- 파일 위치: `blog/layouts/robots.txt` (커스텀 오버라이드)
- `Sitemap:` 경로가 올바른지 (절대 URL)
- 다음(Daum) 웹마스터 도구 해시 포함 여부
- 불필요한 Disallow 규칙이 없는지

### A-3. sitemap.xml
- 파일 위치: `blog/layouts/sitemap.xml` (커스텀 오버라이드)
- `lastmod`, `changefreq`, `priority` 포함 여부
- 태그/카테고리 등 불필요한 페이지 제외 여부

### A-4. 검색엔진 소유권 인증
- 파일 위치: `blog/layouts/partials/extend_head.html`
- 구글 서치콘솔: `google-site-verification` 메타 태그 존재 여부
- 네이버 서치어드바이저: `naver-site-verification` 메타 태그 존재 여부
- 빙 웹마스터 도구: `msvalidate.01` 메타 태그 존재 여부
- 다음 웹마스터 도구: `robots.txt` 내 해시 또는 별도 인증 여부

### A-5. ads.txt (애드센스)
- 파일 위치: `blog/static/ads.txt`
- AdSense Publisher ID(`ca-pub-4208024076105019`)와 일치하는지
- 형식이 올바른지 (`google.com, pub-xxx, DIRECT, f08c47fec0942fa0`)

### A-6. RSS/Atom 피드
- Hugo 기본 RSS 생성 활성화 여부 (`hugo.toml`의 outputs 설정)
- 피드 URL이 접근 가능한지

### A-7. Open Graph 메타 태그
- 테마(PaperMod) 템플릿 존재: `themes/PaperMod/layouts/partials/templates/opengraph.html`
- `og:title`, `og:description`, `og:image`, `og:url`, `og:type` 생성 여부

### A-8. Twitter Card 메타 태그
- 테마(PaperMod) 템플릿 존재: `themes/PaperMod/layouts/partials/templates/twitter_cards.html`
- `twitter:card`, `twitter:title`, `twitter:description`, `twitter:image` 생성 여부

### A-9. 구조화 데이터 (JSON-LD)
- 테마(PaperMod) 템플릿 존재: `themes/PaperMod/layouts/partials/templates/schema_json.html`
- `BlogPosting` 스키마 — headline, datePublished, author, image 포함 여부
- `BreadcrumbList` 스키마 — 네비게이션 경로 생성 여부
- FAQ 스키마 — 적용 여부 (현재 미적용 → 개선 기회)

### A-10. canonical URL
- `head.html`에서 canonical 태그 자동 생성 여부
- 포스트별 `canonicalURL` 오버라이드 가능 여부

### A-11. 태그/카테고리 페이지 색인 제어
- `extend_head.html`에서 term 페이지에 `noindex, follow` 적용 여부
- 중복 콘텐츠 방지 설정

---

## B. 포스트 레벨 체크리스트

각 포스트(`blog/content/posts/*.md`)를 개별적으로 검토.

### B-1. front matter 필수 필드
다음 필드가 모두 존재하는지 확인. 누락 시 [실패]:
- `title` — 제목
- `description` — 메타 설명 (SEO 핵심)
- `date` — 발행일
- `slug` — URL 슬러그
- `tags` — 태그 배열 (최소 1개)
- `categories` — 카테고리 배열 (최소 1개)
- `cover.image` — 커버 이미지 URL
- `cover.alt` — 이미지 대체 텍스트

### B-2. description 길이
- 권장: 80~155자 (한국어 기준)
- 80자 미만 → [경고] 너무 짧아 클릭률 저하 우려
- 155자 초과 → [경고] 검색결과에서 잘림

### B-3. H2 태그 구조
- 본문에 `## ` (H2) 소제목이 최소 3개 이상 존재하는지
- H1(`# `)이 본문에 없는지 (title이 H1 역할)

### B-4. 내부 링크
- 본문에 다른 포스트로의 내부 링크(`(/posts/...`)가 최소 1개 존재하는지
- 없으면 → [경고] 고립된 포스트 (내부 링크 네트워크에서 분리)

### B-5. 커버 이미지 유효성
- `cover.image` URL에 `curl -s -o /dev/null -w "%{http_code}"` 로 HTTP 200 확인
- `premium_photo-` URL 사용 여부 (사용 시 → [실패])
- 기존 포스트와 이미지 중복 여부

### B-6. 커버 이미지 alt 텍스트
- `cover.alt` 필드 존재 여부
- 빈 문자열이 아닌지
- 포스트 주제와 관련 있는 내용인지 (수동 판단)

---

## C. 사이트 구조 체크리스트

포스트 간 관계와 전체 블로그 구조를 점검.

### C-1. 카테고리 분포
- 전체 카테고리별 포스트 수를 집계
- 특정 카테고리에 전체의 50% 이상 집중 → [경고]
- 포스트가 1개뿐인 카테고리 → [경고] (카테고리 통합 또는 추가 발행 권장)

### C-2. 내부 링크 네트워크
- 다른 포스트로부터 링크를 받지 못하는 고립된 포스트 목록
- 내부 링크가 하나도 없는 포스트 목록

### C-3. 카니발리제이션 위험
- 제목(title)에 동일한 핵심 키워드가 포함된 포스트 쌍 감지
- 예: "자동차보험 비교" vs "자동차보험 갱신" → 키워드 겹침 경고

### C-4. 발행 빈도
- 최근 30일 내 발행 포스트 수
- 7일 이상 발행 공백 → [경고]

---

## 출력 형식

```
## A. 사이트 인프라 (X/11 통과)
- [통과] sitemap.xml 정상
- [통과] robots.txt — Sitemap 경로 정상, 다음 해시 포함
- [경고] 빙 웹마스터 verification 없음
- [통과] ...

## B. 포스트 레벨 (N개 중 M개 문제)
- [실패] 20260419-xxx.md — description 180자 (155자 초과)
- [경고] 20260420-xxx.md — 내부 링크 없음
- [통과] 나머지 N개 포스트 정상

## C. 사이트 구조
- [통과] 카테고리 분포 — 5개 카테고리에 균등 분포
- [경고] 카니발리제이션 위험 — "자동차보험 비교" vs "자동차보험 갱신"
- [통과] 발행 빈도 — 최근 30일 12개 발행

## 개선 제안 (우선순위순)
1. 빙 웹마스터 도구 등록 및 verification 메타 태그 추가
2. 고립된 포스트 3개에 내부 링크 추가
3. ...
```

## 주의사항

- B-5(이미지 유효성)은 전체 포스트 검사 시 시간이 걸릴 수 있음 (curl 호출). 필요 시 건너뛸 수 있도록 안내
- 이 스킬의 체크리스트는 **점진적으로 확장**됨. 리서치로 새로운 SEO 인사이트를 얻으면 해당 레벨에 항목 추가
- 체크리스트 항목 추가 시 기존 항목 번호 체계(A-1, B-1, C-1)를 유지할 것
