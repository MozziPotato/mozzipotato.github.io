# CLAUDE.md — 프로젝트 규칙

## 현재 상황 (최우선 이해 사항)
- **LLM API(Anthropic)를 직접 호출할 수 없는 상황**이다.
- 따라서 `main.py`의 자동화 파이프라인(`python main.py daily` 등)은 실행 불가.
- 대신 **Claude Code(너)에게 직접 블로그 작업을 시킨다**: 키워드 선정, 아웃라인, 본문 작성, 포스트 파일 생성, 커밋/푸시 등.
- `src/` 코드를 실행하는 게 아니라, 너가 그 역할을 대신하는 것이 핵심.

## Git 계정 (필수!)
- 이 프로젝트는 **개인 프로젝트**. 회사(gowid) 계정 사용 금지.
- 커밋 전 반드시 확인:
  - `git config user.name` → `MozziPotato`
  - `git config user.email` → `qkrwjdtjq93@gmail.com`
- 만약 회사 계정으로 되어 있으면, 커밋 전에 반드시 개인 계정으로 변경할 것.

## 프로젝트 개요
- Hugo + PaperMod 테마 블로그 (Jekyll 아님!)
- 애드센스 수익화 목적의 블로그 자동화 프로젝트
- 블로그 이름: Human Intelligence
- 배포: GitHub Pages (https://mozzipotato.github.io)

## AdSense
- Publisher ID: `ca-pub-4208024076105019`
- 코드 위치: `blog/layouts/partials/extend_head.html`

## 핵심 구조
- `blog/` — Hugo 블로그 (content, layouts, themes/PaperMod, hugo.toml)
- `src/` — Python 자동화 코드 (orchestrator, content_writer, publisher 등)
- `prompts/` — LLM 프롬프트 파일
- `config.yaml` — 자동화 설정
- `main.py` — CLI 진입점 (setup, daily, weekly, generate, tv-scout, cost)
- `data/blog.db` — SQLite DB

## 포스트 작성 규칙
- **커버 이미지 중복 금지**: 새 포스트 작성 시, 기존 포스트들의 `cover.image` URL과 중복되지 않는 이미지를 선택할 것. 작성 전 `grep "image:" blog/content/posts/` 로 기존 이미지 목록 확인 필수.
- **커버 이미지 적합성**: 이미지가 포스트 주제와 관련 있는지 확인 (예: 열차 포스트에 바다 사진 사용 금지)
- **premium_photo 사용 금지**: Unsplash `premium_photo-` URL은 유료 이미지라 404 발생. 반드시 `photo-` 로 시작하는 무료 이미지만 사용.
- **이미지 URL 유효성 검증 필수**: 커버 이미지 선택 후 `curl -s -o /dev/null -w "%{http_code}" "<URL>"` 으로 HTTP 200 확인. 200이 아니면 다른 이미지 선택.
- **이미지 URL 생성(hallucination) 금지**: Unsplash URL을 기억/추측으로 만들지 말 것. Unsplash 사이트에서 실제 이미지 URL을 확인할 것.
- **바로가기 포스트**: 사이트 제목(H3) 밑에 바로 버튼을 달지 말고, 해당 사이트가 제공하는 핵심 기능 소개를 한 줄 추가한 뒤 버튼을 배치할 것
- **바로가기 버튼**: `{{</* link-button url="..." text="..." */>}}` shortcode 사용
- **시간 민감 정보 사전 검증**: 출시일·시행일·가격·베타/정식 상태·통계는 본문 작성 직전 WebSearch로 최신 상태 재확인. "예정", "곧", "임박" 같은 미래형 표현은 작성 시점에 이미 사건이 일어났을 수 있으므로 반드시 검증 (예: 셋로그 안드로이드 "4월 말 출시 예정"이라 적었는데 실제로는 4/23 이미 출시된 케이스 발생). 신규 앱·SNS·최근 시행 제도처럼 며칠 단위로 변하는 주제는 1차 출처(공식 사이트/SNS/보도자료) 확인 필수, 본문에 "YYYY년 MM월 DD일 기준" 시점 한정 표기.

## 금지 사항
- `gh` CLI 사용 금지 (GitHub CLI 인증 안 됨, 사용할 일 없음)

## 자동화 파이프라인
- 키워드 연구 → 아웃라인(Haiku) → 본문 작성(Sonnet) → 검수 → 이미지(Unsplash) → Git 푸시
- 월간 API 예산: $30
