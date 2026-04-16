-- Supabase SQL Editor에서 실행하세요

-- 1. 조회수 테이블
CREATE TABLE page_views (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug text UNIQUE NOT NULL,
    view_count bigint DEFAULT 0,
    created_at timestamptz DEFAULT now()
);

-- 2. 조회수 증가 함수 (atomic upsert)
CREATE OR REPLACE FUNCTION increment_page_view(page_slug text)
RETURNS bigint AS $$
    INSERT INTO page_views (slug, view_count)
    VALUES (page_slug, 1)
    ON CONFLICT (slug)
    DO UPDATE SET view_count = page_views.view_count + 1
    RETURNING view_count;
$$ LANGUAGE sql;

-- 3. RLS 활성화
ALTER TABLE page_views ENABLE ROW LEVEL SECURITY;

-- 4. 익명 사용자 읽기 허용
CREATE POLICY "Allow anonymous read" ON page_views
    FOR SELECT USING (true);

-- ===== 홈페이지 조회수 통계 (Phase 추가) =====

-- 5. 일별 조회 로그 테이블
CREATE TABLE page_view_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug text NOT NULL,
    viewed_at date DEFAULT CURRENT_DATE
);
CREATE INDEX idx_pvl_viewed_at ON page_view_logs(viewed_at);

-- 6. RLS
ALTER TABLE page_view_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anonymous read" ON page_view_logs FOR SELECT USING (true);

-- 7. 기존 increment 함수를 교체: page_views upsert + 일별 로그 INSERT
CREATE OR REPLACE FUNCTION increment_page_view_v2(page_slug text)
RETURNS bigint AS $$
DECLARE
    result bigint;
BEGIN
    INSERT INTO page_views (slug, view_count)
    VALUES (page_slug, 1)
    ON CONFLICT (slug)
    DO UPDATE SET view_count = page_views.view_count + 1
    RETURNING view_count INTO result;

    INSERT INTO page_view_logs (slug) VALUES (page_slug);

    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 8. 통계 조회 함수 (홈페이지용)
CREATE OR REPLACE FUNCTION get_view_stats()
RETURNS json AS $$
    SELECT json_build_object(
        'total', (SELECT COALESCE(SUM(view_count), 0) FROM page_views),
        'today', (SELECT COUNT(*) FROM page_view_logs WHERE viewed_at = CURRENT_DATE)
    );
$$ LANGUAGE sql SECURITY DEFINER;
