---
name: review-post
description: 블로그 포스트를 8개 체크포인트로 품질 검수합니다
disable-model-invocation: false
---

# 포스트 품질 검수 스킬

블로그 포스트를 8개 항목으로 평가하고 개선점을 제시합니다.

## 실행 절차

1. `prompts/content_review.txt` 파일을 읽어서 평가 체크포인트와 출력 형식을 로딩합니다.
2. 대상 포스트를 확인합니다:
   - 파일 경로가 제공되면 해당 파일을 읽습니다.
   - 제공되지 않으면 사용자에게 요청합니다.
3. 8개 체크포인트를 **모두** 평가합니다 (각 0-100점).
4. 프롬프트에 명시된 JSON 형식으로 결과를 출력합니다.

## 입력

`$ARGUMENTS` — 검수할 포스트 파일 경로 또는 키워드

예시:
- `/review-post blog/content/posts/20260419-아파트-리모델링-비용-평수별-총정리.md`
- `/review-post` (대화 컨텍스트의 포스트 검수)

## 8개 평가 항목 (놓치지 말 것)

1. **seo_score** — 키워드 빈도, H2 구조, 메타 설명, FAQ
2. **adsense_score** — 길이, 정보 가치, 정책 위반, 독창성
3. **humanlike_score** — AI 느낌 표현, 문장 흐름, 패턴 반복
4. **readability_score** — 문장 길이, 단락 구분, 전문 용어 설명
5. **style_score** — ~요체 일관성, 톤, 이모지, 외부 링크
6. **audience_score** — 타겟 독자 적합성, 실용성, 검색 의도 충족
7. **accuracy_score** — 금액 단위, 교차 계산, 표/본문 수치 일치
8. **competitive_edge_score** — 독자적 가치, 구조화 정보, 검색 종료 가치

## 출력

프롬프트에 정의된 JSON 형식 (8개 점수 + issues + suggestions).
