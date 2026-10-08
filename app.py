import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import traceback

# -----------------------------------------------------------------------------
# 0. 최고 관리자(Super Admin) 및 교사 회원가입 보안 설정
# -----------------------------------------------------------------------------
SUPER_ADMIN_USER = "superadmin"
SUPER_ADMIN_PASS = "admin1234"
TEACHER_REGISTER_KEY = "school1234"

# -----------------------------------------------------------------------------
# 1. DB (SQLite) 초기화 및 마이그레이션
# -----------------------------------------------------------------------------
DB_FILE = "school_research.db"


def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1) 기본 테이블 구조 생성 (없을 경우)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            name TEXT,
            role TEXT DEFAULT 'student',
            school_name TEXT DEFAULT '기본초등학교',
            class_name TEXT DEFAULT '일반학급'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            school_name TEXT,
            class_name TEXT,
            topic TEXT,
            title TEXT,
            source_type TEXT,
            has_evidence TEXT,
            created_date TEXT,
            summary TEXT,
            link TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            topic TEXT,
            UNIQUE(username, topic)
        )
    ''')

    # 2) [핵심 수정] 기존 DB가 있을 때 컬럼을 먼저 추가(마이그레이션)
    migration_queries = [
        'ALTER TABLE users ADD COLUMN role TEXT DEFAULT "student"',
        'ALTER TABLE users ADD COLUMN school_name TEXT DEFAULT "기본초등학교"',
        'ALTER TABLE users ADD COLUMN class_name TEXT DEFAULT "일반학급"',
        'ALTER TABLE reports ADD COLUMN school_name TEXT DEFAULT "기본초등학교"',
        'ALTER TABLE reports ADD COLUMN class_name TEXT DEFAULT "일반학급"',
        'ALTER TABLE reports ADD COLUMN topic TEXT DEFAULT "기본 탐구 주제"'
    ]
    for query in migration_queries:
        try:
            c.execute(query)
        except sqlite3.OperationalError:
            pass  # 이미 컬럼이 존재하면 무시

    # 3) 컬럼 추가 후 최고 관리자 계정 생성
    c.execute(
        'INSERT OR IGNORE INTO users (username, password, name, role, school_name, class_name) VALUES (?, ?, ?, ?, ?, ?)',
        (SUPER_ADMIN_USER, make_hashes(SUPER_ADMIN_PASS), '최고 관리자', 'super_admin', '전체 관리국', '총괄'))

    conn.commit()
    conn.close()


def add_user(username, password, name, role="student", school_name="기본초등학교", class_name="일반학급"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users(username, password, name, role, school_name, class_name) VALUES (?,?,?,?,?,?)',
                  (username, make_hashes(password), name, role, school_name, class_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def login_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, password, name, role, school_name, class_name FROM users WHERE username = ?',
              (username,))
    data = c.fetchone()
    conn.close()
    if data and check_hashes(password, data[1]):
        return {
            "username": data[0],
            "name": data[2],
            "role": data[3],
            "school_name": data[4],
            "class_name": data[5]
        }
    return None


# ----- [최고 관리자 전용 DB 함수] -----
def get_global_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users WHERE role = "student"')
    total_students = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE role = "teacher"')
    total_teachers = c.fetchone()[0]
    c.execute('SELECT COUNT(DISTINCT school_name) FROM users WHERE role = "teacher"')
    total_schools = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM reports')
    total_reports = c.fetchone()[0]
    conn.close()
    return total_students, total_teachers, total_schools, total_reports


def get_all_users_global():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('''
        SELECT username as "아이디", name as "이름", role as "역할", 
               school_name as "학교명", class_name as "학급명"
        FROM users ORDER BY role, school_name, class_name
    ''', conn)
    conn.close()
    return df


def reset_any_password(username, new_password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE users SET password = ? WHERE username = ?', (make_hashes(new_password), username))
    conn.commit()
    conn.close()


def delete_user_account(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE username = ?', (username,))
    c.execute('DELETE FROM reports WHERE username = ?', (username,))
    c.execute('DELETE FROM user_topics WHERE username = ?', (username,))
    conn.commit()
    conn.close()


def load_all_reports_global():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('''
        SELECT school_name as "학교명", class_name as "학급명", username as "학생 아이디", 
               topic as "탐구 폴더", title as "제목", source_type as "출처 유형", 
               has_evidence as "근거 유무", created_date as "작성 시점", 
               summary as "학생 작성 요약", link as "원문 링크"
        FROM reports ORDER BY school_name, class_name, topic, username
    ''', conn)
    conn.close()
    return df


# ----- [교사 및 학생용 DB 함수] -----
def get_all_schools():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT DISTINCT school_name FROM users WHERE role = "teacher"')
    schools = [row[0] for row in c.fetchall() if row[0]]
    conn.close()
    if not schools:
        schools = ["한국초등학교", "서울초등학교", "부산초등학교"]
    return schools


def get_classes_by_school(school_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT DISTINCT class_name FROM users WHERE role = "teacher" AND school_name = ?', (school_name,))
    classes = [row[0] for row in c.fetchall() if row[0]]
    conn.close()
    if not classes:
        classes = ["3학년 1반", "3학년 2반", "4학년 1반", "5학년 1반", "6학년 1반"]
    return classes


def get_students_by_school_and_class(school_name, class_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, name FROM users WHERE role = "student" AND school_name = ? AND class_name = ?',
              (school_name, class_name))
    data = c.fetchall()
    conn.close()
    return data


def load_class_reports(school_name, class_name):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('''
        SELECT username as "학생 아이디", topic as "탐구 폴더", title as "제목", 
               source_type as "출처 유형", has_evidence as "근거 유무", 
               created_date as "작성 시점", summary as "학생 작성 요약", link as "원문 링크"
        FROM reports WHERE school_name = ? AND class_name = ? ORDER BY topic, username
    ''', conn, params=(school_name, class_name))
    conn.close()
    return df


def add_user_topic(username, topic):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT OR IGNORE INTO user_topics (username, topic) VALUES (?, ?)', (username, topic))
        conn.commit()
    finally:
        conn.close()


def save_report(username, school_name, class_name, topic, title, source_type, has_evidence, created_date, summary,
                link):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO reports (username, school_name, class_name, topic, title, source_type, has_evidence, created_date, summary, link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (username, school_name, class_name, topic, title, source_type, has_evidence, created_date, summary, link))
    conn.commit()
    conn.close()


def load_user_topics(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT DISTINCT topic FROM (
            SELECT topic FROM reports WHERE username = ?
            UNION
            SELECT topic FROM user_topics WHERE username = ?
        )
    ''', (username, username))
    topics = [row[0] for row in c.fetchall() if row[0]]
    conn.close()
    return topics


def load_user_reports_by_topic(username, topic):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('''
        SELECT title as "제목", source_type as "출처 유형", has_evidence as "근거 유무", 
               created_date as "작성 시점", summary as "내가 작성한 요약", link as "원문 링크"
        FROM reports WHERE username = ? AND topic = ?
    ''', conn, params=(username, topic))
    conn.close()
    return df


init_db()

# -----------------------------------------------------------------------------
# 2. 페이지 기본 설정 및 세션 초기화
# -----------------------------------------------------------------------------
st.set_page_config(page_title="학생 주도 비판적 자료수집 탐색기", page_icon="🔍", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = "student"
if "school_name" not in st.session_state:
    st.session_state.school_name = ""
if "class_name" not in st.session_state:
    st.session_state.class_name = ""
if "current_topic" not in st.session_state:
    st.session_state.current_topic = "기본 탐구 주제"

# -----------------------------------------------------------------------------
# 3. 사이드바 - 로그인 및 회원가입
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("👤 계정 로그인")

    if not st.session_state.logged_in:
        auth_menu = st.radio("메뉴 선택", ["로그인", "학생 회원가입", "🍎 교사 회원가입"])

        if auth_menu == "로그인":
            input_user = st.text_input("아이디")
            input_pass = st.text_input("비밀번호", type="password")
            if st.button("로그인"):
                user_info = login_user(input_user, input_pass)
                if user_info:
                    st.session_state.logged_in = True
                    st.session_state.username = user_info["username"]
                    st.session_state.user_name = user_info["name"]
                    st.session_state.user_role = user_info["role"]
                    st.session_state.school_name = user_info["school_name"]
                    st.session_state.class_name = user_info["class_name"]
                    st.success(f"{user_info['name']}님 환영합니다!")
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

        elif auth_menu == "학생 회원가입":
            st.caption("소속 학교와 담당 학급을 정확히 선택해 주세요.")
            schools = get_all_schools()
            selected_school = st.selectbox("1. 소속 학교 선택", schools)
            classes = get_classes_by_school(selected_school)
            selected_class = st.selectbox("2. 담당 학급 선택", classes)

            new_user = st.text_input("3. 사용할 학생 아이디")
            new_name = st.text_input("4. 학생 이름 (예: 홍길동)")
            new_pass = st.text_input("5. 비밀번호 설정", type="password")

            if st.button("학생 계정 만들기"):
                if new_user and new_name and new_pass:
                    if add_user(new_user, new_pass, new_name, role="student", school_name=selected_school,
                                class_name=selected_class):
                        st.success("학생 회원가입 성공! 로그인해 주세요.")
                    else:
                        st.error("이미 존재하는 아이디입니다.")
                else:
                    st.warning("모든 항목을 입력해 주세요.")

        elif auth_menu == "🍎 교사 회원가입":
            st.caption("교사 전용 회원가입 화면입니다.")
            teacher_key = st.text_input("교사 인증키 입력", type="password", help="초기 설정키: school1234")
            t_school = st.text_input("소속 학교명 입력", placeholder="예: 서울초등학교, 부산초등학교")
            t_class = st.text_input("담당 학급 입력", placeholder="예: 3학년 4반, 5학년 1반")
            t_user = st.text_input("선생님 사용할 아이디")
            t_name = st.text_input("선생님 성함 (예: 김철수 선생님)")
            t_pass = st.text_input("비밀번호 설정", type="password")

            if st.button("교사 계정 만들기"):
                if teacher_key != TEACHER_REGISTER_KEY:
                    st.error("교사 인증키가 올바르지 않습니다.")
                elif not (t_school and t_class and t_user and t_name and t_pass):
                    st.warning("모든 항목을 입력해 주세요.")
                else:
                    if add_user(t_user, t_pass, t_name, role="teacher", school_name=t_school.strip(),
                                class_name=t_class.strip()):
                        st.success(f"[{t_school.strip()} {t_class.strip()}] 교사 계정이 생성되었습니다! 로그인해 주세요.")
                    else:
                        st.error("이미 존재하는 아이디입니다.")
    else:
        role_map = {"super_admin": "👑 최고 관리자", "teacher": "🍎 교사", "student": "🎒 학생"}
        role_label = role_map.get(st.session_state.user_role, "🎒 학생")
        st.success(
            f"🔓 **{st.session_state.user_name}** ({role_label})\n\n🏫 **{st.session_state.school_name}**\n📍 **{st.session_state.class_name}**")
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.user_name = ""
            st.session_state.user_role = "student"
            st.session_state.school_name = ""
            st.session_state.class_name = ""
            st.rerun()

    st.divider()
    st.header("💡 이용 안내")
    st.markdown("""
    1. **주제 생성**: 규격화된 항목 선택 후 탐구 폴더를 생성합니다.
    2. **자료 탐색**: 키워드를 입력하고 검증된 자료를 직접 읽습니다.
    3. **비판적 요약**: 스스로 작성한 핵심 내용만 보고서에 저장합니다.
    """)

# -----------------------------------------------------------------------------
# 4. 실시간 검색 및 시스템 진단 함수
# -----------------------------------------------------------------------------
BLOCKED_KEYWORDS = ["gambling", "adult", "casino", "betting", "poker", "torrent"]


def is_blocked(link):
    return any(bad in link.lower() for bad in BLOCKED_KEYWORDS)


def fetch_rss_results_debug(search_term, seen_links):
    results = []
    logs = []
    try:
        encoded_query = urllib.parse.quote(search_term)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        logs.append(f"📡 요청 URL: {url}")

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.getcode()
            logs.append(f"✅ 구글 RSS 서버 응답 코드: {status_code}")
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        logs.append(f"📦 검색 수집 항목 개수: {len(items)}개")

        for item in items:
            title = item.find('title').text if item.find('title') is not None else '제목 없음'
            link = item.find('link').text if item.find('link') is not None else '#'
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''

            if link not in seen_links:
                if not is_blocked(link):
                    seen_links.add(link)
                    results.append({
                        'title': title,
                        'body': f"보도/게시 일시: {pub_date[:25]} | 클릭하여 원문을 직접 읽고 검증해 보세요.",
                        'href': link
                    })
                else:
                    logs.append(f"🛡️ 유해 블록리스트 차단 링크: {link}")
    except Exception as e:
        logs.append(f"❌ 오류 발생: {str(e)}")
        logs.append(traceback.format_exc())

    return results, logs


def search_broad_keyword(query):
    seen_links = set()
    results = []
    r1, _ = fetch_rss_results_debug(query, seen_links)
    results.extend(r1)
    if len(results) < 4:
        words = query.split()
        if len(words) > 1:
            short_query = " ".join(words[-2:])
            r2, _ = fetch_rss_results_debug(short_query, seen_links)
            results.extend(r2)
    return results[:8]


# -----------------------------------------------------------------------------
# 5. 메인 화면 (최고 관리자 vs 교사 대시보드 vs 학생 탐구 화면)
# -----------------------------------------------------------------------------

# [A] 최고 관리자 로그인 시 (super_admin 계정)
if st.session_state.logged_in and st.session_state.user_role == "super_admin":
    st.title("👑 사이트 총괄 최고 관리자 센터")
    st.caption("전국 가입 현황 파악, 계정 관리 및 시스템 전체 오류를 총괄 제어합니다.")

    # 상단 요약 지표
    t_students, t_teachers, t_schools, t_reports = get_global_stats()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🏫 등록된 총 학교 수", f"{t_schools} 개교")
    m2.metric("🍎 가입된 총 교사 수", f"{t_teachers} 명")
    m3.metric("🎒 가입된 총 학생 수", f"{t_students} 명")
    m4.metric("📄 누적 수집 보고서 수", f"{t_reports} 건")

    st.divider()

    sa_tab1, sa_tab2, sa_tab3, sa_tab4 = st.tabs([
        "👥 전체 회원 계정 총괄 관리",
        "📋 전국 학교 보고서 백업 감시",
        "🛠️ 네트워크 & 구글 RSS 연결 진단",
        "⚙️ 사이트 전반 설정"
    ])

    with sa_tab1:
        st.subheader("👥 가입 유저 통합 관리")
        all_users_df = get_all_users_global()
        st.dataframe(all_users_df, use_container_width=True)

        st.divider()
        col_sa1, col_sa2 = st.columns(2)

        with col_sa1:
            st.markdown("##### 🔑 특정 유저 비밀번호 강제 초기화")
            user_list = all_users_df["아이디"].tolist()
            selected_user_reset = st.selectbox("초기화 대상 아이디 선택", user_list, key="sb_reset")
            new_pass_val = st.text_input("새로운 비밀번호 입력", value="1234", key="in_reset")
            if st.button("비밀번호 즉시 변경"):
                reset_any_password(selected_user_reset, new_pass_val)
                st.success(f"'{selected_user_reset}' 계정의 비밀번호가 [{new_pass_val}](으)로 수정되었습니다.")

        with col_sa2:
            st.markdown("##### 🗑️ 계정 강제 삭제 (DB 완전 삭제)")
            selected_user_del = st.selectbox("삭제 대상 아이디 선택", user_list, key="sb_del")
            if st.button("⚠️ 계정 삭제 실행", type="primary"):
                if selected_user_del == SUPER_ADMIN_USER:
                    st.error("최고 관리자 계정은 삭제할 수 없습니다.")
                else:
                    delete_user_account(selected_user_del)
                    st.success(f"'{selected_user_del}' 계정이 성공적으로 삭제되었습니다.")
                    st.rerun()

    with sa_tab2:
        st.subheader("📋 전체 제출 보고서 통합 모아보기")
        global_reports_df = load_all_reports_global()
        if not global_reports_df.empty:
            st.dataframe(global_reports_df, use_container_width=True)
            csv_global = global_reports_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 전국 전체 데이터통합 백업 다운로드 (CSV)",
                data=csv_global,
                file_name="전국_비판적자료수집기_전체보고서_백업.csv",
                mime="text/csv"
            )
        else:
            st.caption("아직 제출된 보고서 데이터가 없습니다.")

    with sa_tab3:
        st.subheader("🛠️ 시스템 헬스 체크 & 원격 진단")
        st.caption("클라우드 서버 네트워크 상태 및 구글 RSS API 실시간 응답 상태를 검사합니다.")
        test_q = st.text_input("진단 키워드", value="2026년 유망 직업")
        if st.button("🔍 시스템 종합 응답 테스트"):
            seen_set = set()
            t_res, t_log = fetch_rss_results_debug(test_q, seen_set)
            for l in t_log:
                st.code(l, language="text")
            if t_res:
                st.success(f"검색 엔진 정상 작동 중! ({len(t_res)}건 데이터 정상 수집)")
            else:
                st.error("검색 응답 실패. 로그를 확인하세요.")

    with sa_tab4:
        st.subheader("⚙️ 서버 환경 정보")
        st.write(f"- **데이터베이스 파일:** `{DB_FILE}` (SQLite3)")
        st.write(f"- **최고 관리자 계정:** `{SUPER_ADMIN_USER}`")
        st.write(f"- **기본 교사 인증키:** `{TEACHER_REGISTER_KEY}`")

# [B] 교사 계정 로그인 시 (담당 학급 전용 대시보드)
elif st.session_state.logged_in and st.session_state.user_role == "teacher":
    st.title(f"🍎 {st.session_state.school_name} {st.session_state.class_name} 대시보드")
    st.caption(
        f"[{st.session_state.school_name} {st.session_state.class_name}] 담당 학생들의 계정, 보고서 제출 현황 및 검색 엔진 상태를 관리합니다.")

    admin_tab1, admin_tab2, admin_tab3 = st.tabs([
        "🔑 내 반 학생 비밀번호 초기화",
        "📊 우리 반 전체 제출물 모아보기",
        "🛠️ 검색기 테스트 및 실시간 오류 진단"
    ])

    with admin_tab1:
        st.subheader(f"👥 [{st.session_state.school_name} {st.session_state.class_name}] 학생 계정 목록")
        class_students = get_students_by_school_and_class(st.session_state.school_name, st.session_state.class_name)
        if class_students:
            student_dict = {f"{s[1]} ({s[0]})": s[0] for s in class_students}
            selected_student_label = st.selectbox("비밀번호를 초기화할 학생 선택", list(student_dict.keys()))
            target_username = student_dict[selected_student_label]

            reset_pw_input = st.text_input("새 비밀번호 지정", value="1234")
            if st.button("비밀번호 초기화"):
                reset_student_password(target_username, reset_pw_input)
                st.success(f"'{selected_student_label}' 학생의 비밀번호가 [{reset_pw_input}](으)로 초기화되었습니다!")
        else:
            st.info(f"아직 [{st.session_state.school_name} {st.session_state.class_name}]에 가입한 학생이 없습니다.")

    with admin_tab2:
        st.subheader(f"📋 [{st.session_state.school_name} {st.session_state.class_name}] 탐구 보고서 모음")
        class_df = load_class_reports(st.session_state.school_name, st.session_state.class_name)
        if not class_df.empty:
            st.dataframe(class_df, use_container_width=True)
            csv_class = class_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 [{st.session_state.school_name} {st.session_state.class_name}] 전체 보고서 다운로드 (CSV)",
                data=csv_class,
                file_name=f"{st.session_state.school_name}_{st.session_state.class_name}_전체_탐구보고서.csv",
                mime="text/csv"
            )
        else:
            st.caption("아직 제출된 학생 탐구 보고서가 없습니다.")

    with admin_tab3:
        st.subheader("🛠️ 학생용 검색 엔진 및 네트워크 진단")
        st.caption("학생들에게 검색 오류가 발생하거나 차단되는지 사전 테스트할 수 있습니다.")
        test_query = st.text_input("진단용 키워드 테스트 입력", value="기후변화 원인")
        if st.button("🔍 검색 엔진 및 RSS 연결 테스트 실행"):
            seen_links = set()
            test_results, test_logs = fetch_rss_results_debug(test_query, seen_links)
            with st.expander("실시간 네트워크 & 파싱 로그 보기", expanded=True):
                for log in test_logs:
                    st.code(log, language="text")
            if test_results:
                st.success(f"정상 작동 중! ({len(test_results)}개의 결과 수집 성공)")
                for res in test_results:
                    st.write(f"- **[{res['title']}]** ({res['href']})")
            else:
                st.error("검색 결과가 없습니다.")

# [C] 학생 로그인 및 일반 접속 화면
else:
    st.title("🔍 스스로 탐구하는 비판적 자료수집기")
    st.caption("AI의 자동 요약에 의존하지 않고, 직접 원문 사이트를 읽고 검증하며 진짜 정보를 찾아보세요!")

    if st.session_state.logged_in:
        with st.container(border=True):
            st.subheader("📁 탐구 주제(폴더) 관리")
            tab1, tab2 = st.tabs(["📂 기존 탐구 주제 선택", "➕ 새 규격화 주제 만들기"])

            with tab1:
                existing_topics = load_user_topics(st.session_state.username)
                if "기본 탐구 주제" not in existing_topics:
                    existing_topics.insert(0, "기본 탐구 주제")
                if st.session_state.current_topic not in existing_topics:
                    existing_topics.append(st.session_state.current_topic)

                selected_topic = st.selectbox(
                    "내가 저장해둔 탐구 주제 목록에서 선택하기:",
                    existing_topics,
                    index=existing_topics.index(st.session_state.current_topic)
                )
                st.session_state.current_topic = selected_topic

            with tab2:
                st.caption("학년/학기, 월, 교과/단원은 선택하고, 세부주제만 자유롭게 작성하세요.")
                c1, c2, c3, c4 = st.columns([2, 1.5, 2.5, 4])

                grade_term_options = ["3학년 1학기", "3학년 2학기", "4학년 1학기", "4학년 2학기", "5학년 1학기", "5학년 2학기", "6학년 1학기",
                                      "6학년 2학기"]
                with c1:
                    term_select = st.selectbox("학년/학기", grade_term_options, index=1)
                month_options = [f"{m}월" for m in range(1, 13)]
                with c2:
                    month_select = st.selectbox("월", month_options, index=8)
                subject_unit_options = ["사회 1단원", "사회 2단원", "사회 3단원", "과학 1단원", "과학 2단원", "과학 3단원", "과학 4단원", "국어 1단원",
                                        "국어 2단원", "국어 3단원", "실과 1단원", "실과 2단원", "창체/자율", "기타 탐구"]
                with c3:
                    subject_select = st.selectbox("교과/단원", subject_unit_options, index=0)
                with c4:
                    sub_topic_input = st.text_input("세부주제 (자유 입력)", placeholder="예: 세계의 의복, 미래 유망 직종")

                formatted_topic_name = f"[{term_select} {month_select} {subject_select} {sub_topic_input.strip()}]".strip()

                if sub_topic_input.strip():
                    st.info(f"🏷️ 자동 완성될 표준 폴더명: **{formatted_topic_name}**")
                else:
                    st.caption("세부주제를 입력하면 완성될 표준 폴더명이 표시됩니다.")

                if st.button("✨ 이 이름으로 새 탐구 폴더 만들기"):
                    if not sub_topic_input.strip():
                        st.error("세부주제를 입력해 주세요!")
                    else:
                        add_user_topic(st.session_state.username, formatted_topic_name)
                        st.session_state.current_topic = formatted_topic_name
                        st.success(f"새 탐구 폴더 '{formatted_topic_name}'(이)가 성공적으로 생성되었습니다!")
                        st.rerun()
    else:
        st.warning("⚠️ **현재 미로그인 상태입니다.** 로그인을 하시면 주제별로 탐구 보고서를 구분하여 관리할 수 있습니다.")

    st.markdown(f"### 📌 현재 작업 중인 탐구 폴더: `{st.session_state.current_topic}`")

    col1, col2 = st.columns([3, 2])

    # ----- [좌측 칼럼] 원문 검색기 -----
    with col1:
        st.subheader("1️⃣ 인터넷 자료 검색")
        search_keyword = st.text_input("탐구할 키워드를 입력하세요", placeholder="예: 기후변화 원인, 세종대왕 업적, 세계의 전통 의복")

        if search_keyword:
            with st.spinner("관련 주제의 원문 자료를 가져오는 중입니다..."):
                items = search_broad_keyword(search_keyword)

            if items:
                st.success(f"'{search_keyword}' 검색 결과입니다. 원문을 직접 방문해 읽어보세요!")
                for idx, item in enumerate(items):
                    title = item.get('title', '제목 없음')
                    description = item.get('body', '요약 정보가 없습니다.')
                    link = item.get('href', '#')

                    with st.container(border=True):
                        st.markdown(f"### {title}")
                        st.write(f"📄 **사이트 브리프:** {description}")
                        st.markdown(f"[🔗 **[클릭] 원문 사이트 가서 직접 읽기**]({link})")

                        if st.button(f"📌 이 자료를 검증하고 스크랩하기", key=f"btn_{idx}"):
                            st.session_state.selected_item = {"title": title, "link": link}
                            st.toast("우측에서 체크리스트를 작성해 주세요!", icon="👉")
            else:
                st.info("검색 결과가 없습니다. 다른 단어로 검색해 보세요.")

    # ----- [우측 칼럼] 검증 및 보고서 저장 -----
    with col2:
        st.subheader("2️⃣ 출처 검증 및 직접 요약")
        selected = st.session_state.get("selected_item", None)

        if selected:
            title_text = selected.get('title', '')
            with st.form("scrap_form"):
                st.info(f"선택한 자료: **{title_text}**")
                st.caption(f"📂 저장 위치: **{st.session_state.current_topic}**")

                q1 = st.selectbox("1. 이 글을 작성한 주체(출처)는 어디인가요?",
                                  ["언론사/뉴스", "정부/공공기관", "전문 연구기관", "개인 블로그/지식iN", "기타"])
                q2 = st.radio("2. 글에 근거/통계가 명확한가요?", ["예", "아니오", "명확하지 않음"])
                q3 = st.text_input("3. 자료 작성 시점", placeholder="예: 2024년 5월")
                student_summary = st.text_area("✍️ 내가 직접 정리하는 핵심 내용 (복사-붙여넣기 금지!)", placeholder="원문을 읽고 스스로 요약해 보세요!")

                submit_btn = st.form_submit_button("💾 현재 폴더 보고서에 저장")

                if submit_btn:
                    if not st.session_state.logged_in:
                        st.error("🔒 저장하려면 먼저 왼쪽 사이드바에서 [로그인]을 해주세요!")
                    elif not student_summary.strip():
                        st.error("한 줄 요약 내용을 직접 작성해 주세요!")
                    else:
                        save_report(
                            st.session_state.username,
                            st.session_state.school_name,
                            st.session_state.class_name,
                            st.session_state.current_topic,
                            selected['title'],
                            q1, q2, q3,
                            student_summary,
                            selected['link']
                        )
                        st.success(f"'{st.session_state.current_topic}' 폴더에 성공적으로 저장되었습니다!")
                        st.session_state.selected_item = None
                        st.rerun()
        else:
            st.write("👈 좌측에서 자료의 **[📌 이 자료를 검증하고 스크랩하기]** 버튼을 눌러주세요.")

        st.divider()

        # ----- 하단: 선택된 폴더에 해당하는 보고서만 표시 -----
        if st.session_state.logged_in:
            st.subheader(f"3️⃣ {st.session_state.current_topic} 탐구 보고서")
            user_df = load_user_reports_by_topic(st.session_state.username, st.session_state.current_topic)

            if not user_df.empty:
                st.dataframe(user_df, use_container_width=True)
                csv = user_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label=f"📥 {st.session_state.current_topic} 보고서 다운로드 (CSV)",
                    data=csv,
                    file_name=f"{st.session_state.user_name}_{st.session_state.current_topic}_보고서.csv",
                    mime="text/csv"
                )
            else:
                st.caption(f"아직 '{st.session_state.current_topic}' 폴더에 저장된 자료가 없습니다.")
        else:
            st.subheader("3️⃣ 내 탐구 보고서 목록")
            st.caption("로그인하시면 주제별로 저장된 보고서를 선택해 확인할 수 있습니다.")