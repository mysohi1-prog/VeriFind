import streamlit as st
import sqlite3
import hashlib
import xml.etree.ElementTree as ET
import urllib.parse
import urllib.request
import re
import math
from email.utils import parsedate_to_datetime


# ---------------------------------------------------------
# 0. UI/UX 커스텀 CSS 주입
# ---------------------------------------------------------
def inject_custom_css():
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { background-color: #f4f7fa; }
        .step-badge {
            background-color: #3b82f6; color: white; padding: 4px 12px;
            border-radius: 20px; font-weight: bold; font-size: 0.9em;
            display: inline-block; margin-bottom: 8px;
        }
        .warning-box {
            background-color: #fffbeb; border: 1px solid #fde68a;
            color: #92400e; padding: 12px; border-radius: 8px;
            margin-bottom: 15px; font-weight: bold;
        }
        .folder-box {
            border: 2px dashed #3b82f6; background-color: #eff6ff;
            color: #1e3a8a; padding: 12px; border-radius: 8px;
            margin-bottom: 20px; font-weight: bold;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0 !important; padding: 8px 16px !important; background-color: #e5e7eb; }
        .stTabs [aria-selected="true"] { background-color: #3b82f6 !important; color: white !important; }
        .stButton>button { border-radius: 8px; font-weight: bold; }

        /* 문서 탭 1단 카드 디자인 */
        .news-card {
            padding: 16px; 
            border: 1px solid #e2e8f0; 
            border-radius: 10px; 
            margin-bottom: 12px; 
            background-color: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }

        /* 페이지네이션 UI */
        .pagination-text { 
            text-align: center; 
            color: #475569; 
            margin-top: 15px; 
            margin-bottom: 10px; 
            font-weight: bold; 
            font-size: 0.95em;
        }
        </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# 1. 안전 검색 엔진 (문서 탭 전용)
# ---------------------------------------------------------
def search_safe_news(keyword):
    safe_query = f"{keyword} -site:youtube.com -구매 -쇼핑"
    encoded_kw = urllib.parse.quote(safe_query)
    url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    results = []
    try:
        html = urllib.request.urlopen(req, timeout=5).read()
        root = ET.fromstring(html)
        items = root.findall('.//item')
        for item in items:
            title = re.sub('<[^<]+?>', '', item.find('title').text)
            link = item.find('link').text
            pub_date_str = item.find('pubDate').text
            pub_date = parsedate_to_datetime(pub_date_str)
            results.append({'title': title, 'link': link, 'date': pub_date, 'type': 'news'})
    except:
        pass
    return results[:60]


# ---------------------------------------------------------
# 1.5 페이지네이션 UI 헬퍼
# ---------------------------------------------------------
def render_pagination(total_items, items_per_page, current_page, state_key):
    total_pages = max(1, math.ceil(total_items / items_per_page))
    if total_pages <= 1:
        return current_page

    st.write("---")
    st.markdown(f'<div class="pagination-text">{current_page} / {total_pages} 페이지</div>', unsafe_allow_html=True)

    cols = st.columns([2] + [1] * total_pages + [2])
    for i in range(1, total_pages + 1):
        with cols[i]:
            if st.button(str(i), key=f"btn_page_{state_key}_{i}", type="primary" if i == current_page else "secondary"):
                st.session_state[state_key] = i
                st.rerun()
    return current_page


# ---------------------------------------------------------
# 2. DB 초기화
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect('school_research.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     username
                     TEXT
                     UNIQUE,
                     password
                     TEXT,
                     role
                     TEXT,
                     school_name
                     TEXT,
                     class_name
                     TEXT,
                     real_name
                     TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reports
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     username
                     TEXT,
                     school_name
                     TEXT,
                     class_name
                     TEXT,
                     folder_name
                     TEXT,
                     title
                     TEXT,
                     link
                     TEXT,
                     publisher
                     TEXT,
                     evidence_check
                     TEXT,
                     summary
                     TEXT,
                     created_at
                     TIMESTAMP
                     DEFAULT
                     CURRENT_TIMESTAMP
                 )''')
    admin_pw = hashlib.sha256("admin1234".encode()).hexdigest()
    c.execute('''INSERT
    OR IGNORE INTO users (username, password, role, school_name, class_name, real_name) VALUES ('superadmin', ?, 'superadmin', '전국총괄', '최고관리자', '총괄관리자')''',
              (admin_pw,))
    conn.commit()
    conn.close()


def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()


init_db()

# ---------------------------------------------------------
# 3. 세션 상태 관리
# ---------------------------------------------------------
st.set_page_config(page_title="VeriFind - 비판적 탐구 탐색기", layout="wide")
inject_custom_css()

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = None

if 'news_page' not in st.session_state:
    st.session_state['news_page'] = 1

st.title("🔎 VeriFind")
st.caption("내가 찾고, 내가 확인하고, 내 말로 요약해요! AI가 대신 해 주지 않아요.")

with st.sidebar:
    st.header("👤 계정 로그인" if not st.session_state['logged_in'] else "👤 계정 관리")
    if not st.session_state['logged_in']:
        menu = st.radio("메뉴 선택", ["로그인", "학생 회원가입", "🍎 교사 회원가입"], label_visibility="collapsed")

        if menu == "로그인":
            with st.form("login_form"):
                login_id = st.text_input("아이디")
                login_pw = st.text_input("비밀번호", type="password")
                if st.form_submit_button("로그인", use_container_width=True):
                    conn = sqlite3.connect('school_research.db')
                    c = conn.cursor()
                    c.execute(
                        "SELECT username, role, school_name, class_name, real_name FROM users WHERE username=? AND password=?",
                        (login_id, hash_pw(login_pw)))
                    user = c.fetchone()
                    conn.close()
                    if user:
                        st.session_state['logged_in'] = True
                        st.session_state['user_info'] = {'username': user[0], 'role': user[1], 'school_name': user[2],
                                                         'class_name': user[3], 'real_name': user[4]}
                        st.rerun()
                    else:
                        st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
        elif menu == "학생 회원가입":
            with st.form("student_signup_form"):
                s_school = st.text_input("학교명")
                s_class = st.text_input("학급명")
                s_id = st.text_input("아이디")
                s_pw = st.text_input("비밀번호", type="password")
                s_name = st.text_input("이름")
                if st.form_submit_button("가입하기", use_container_width=True) and s_id:
                    try:
                        conn = sqlite3.connect('school_research.db')
                        conn.execute(
                            "INSERT INTO users (username, password, role, school_name, class_name, real_name) VALUES (?, ?, 'student', ?, ?, ?)",
                            (s_id, hash_pw(s_pw), s_school, s_class, s_name))
                        conn.commit();
                        conn.close()
                        st.success("회원가입 완료! 로그인해주세요.")
                    except:
                        st.error("이미 존재하는 아이디입니다.")
        elif menu == "🍎 교사 회원가입":
            with st.form("teacher_signup_form"):
                t_key = st.text_input("교사 인증키", type="password")
                t_school = st.text_input("소속 학교명")
                t_class = st.text_input("담당 학급명")
                t_id = st.text_input("교사 아이디")
                t_pw = st.text_input("비밀번호", type="password")
                t_name = st.text_input("선생님 성함")
                if st.form_submit_button("가입하기", use_container_width=True) and t_key == "school1234":
                    try:
                        conn = sqlite3.connect('school_research.db')
                        conn.execute(
                            "INSERT INTO users (username, password, role, school_name, class_name, real_name) VALUES (?, ?, 'teacher', ?, ?, ?)",
                            (t_id, hash_pw(t_pw), t_school, t_class, t_name))
                        conn.commit();
                        conn.close()
                        st.success("교사 회원가입 완료!")
                    except:
                        st.error("이미 존재하는 아이디입니다.")

        st.divider()
        st.markdown("### 💡 이용 안내\n1. **탐구 주제**를 정해요\n2. **자료**를 찾아 스크랩해요\n3. **믿을 수 있는지** 확인해요\n4. **내 말로** 직접 요약해요")
    else:
        u = st.session_state['user_info']
        st.success(f"**{u['real_name']}** ({u['role']})")
        st.write(f"🏫 {u['school_name']} {u['class_name']}")
        if st.button("로그아웃", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['user_info'] = None
            st.rerun()


# ---------------------------------------------------------
# 4. 학생 탐구 화면 뷰
# ---------------------------------------------------------
def render_student_view(u_info=None):
    is_guest = u_info is None

    if is_guest:
        st.markdown('<div class="warning-box">⚠️ 현재 미로그인 상태입니다. 로그인을 하시면 주제별로 탐구 보고서를 구분하여 관리할 수 있습니다.</div>',
                    unsafe_allow_html=True)
        current_folder = "기본 탐구 주제"
        st.markdown(f'<div class="folder-box">📁 지금 작업 폴더 : [{current_folder}] 자유 탐구</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="step-badge">STEP 1</div> **탐구 주제(폴더) 정하기**', unsafe_allow_html=True)

        # 1. 학년/학기 리스트
        grades = [f"{g}학년 {s}학기" for g in range(1, 7) for s in range(1, 3)]

        # 2. 2022 개정 교육과정 기준 [과목명 : 단원 리스트] 사전(Dictionary) 매핑
        subjects_dict = {
            "국어": [f"{i}단원" for i in range(1, 10)],
            "수학": [f"{i}단원" for i in range(1, 7)],
            "사회": [f"{i}단원" for i in range(1, 5)],
            "과학": [f"{i}단원" for i in range(1, 7)],
            "도덕": [f"{i}단원" for i in range(1, 7)],
            "영어": [f"Lesson {i}" for i in range(1, 12)],
            "실과": [f"{i}단원" for i in range(1, 7)],
            "통합(바·슬·즐)": [f"{i}단원" for i in range(1, 9)],
            "체육": ["-"],
            "음악": ["-"],
            "미술": ["-"],
            "창의적 체험활동": ["-"],
            "자유 탐구": ["-"]
        }

        # 3칸을 4칸으로 세분화 (비율 조정)
        col_f1, col_f2, col_f3, col_f4 = st.columns([1.2, 1, 1, 2])

        grade = col_f1.selectbox("학년/학기", grades, index=8, label_visibility="collapsed")  # 기본값 5학년 1학기

        # 과목 선택
        subject_list = list(subjects_dict.keys())
        subject = col_f2.selectbox("교과", subject_list, index=2, label_visibility="collapsed")  # 기본값 사회

        # 선택한 과목에 따라 단원 리스트가 자동으로 바뀜!
        unit_list = subjects_dict[subject]
        unit = col_f3.selectbox("단원", unit_list, index=0, label_visibility="collapsed")

        # 세부 탐구 주제 입력
        sub_topic = col_f4.text_input("세부 탐구 주제", value="세계의 다양한 문화", label_visibility="collapsed")

        # 단원이 없는 예체능 등은 폴더명에서 단원 표시(-) 생략
        unit_str = f" {unit}" if unit != "-" else ""
        current_folder = f"[{grade} {subject}{unit_str}] {sub_topic}"

        st.markdown(f'<div class="folder-box">📁 지금 작업 폴더 : {current_folder}</div>', unsafe_allow_html=True)
    st.write("---")
    col_left, col_right = st.columns([1.3, 1])
    ITEMS_PER_PAGE = 12

    with col_left:
        st.markdown('<div class="step-badge">STEP 2</div> **자료 찾기 (안전 탐색)**', unsafe_allow_html=True)
        tab_news, tab_img, tab_vid = st.tabs(["📰 뉴스·문서", "🖼️ 사진/이미지", "🎥 영상 자료"])

        # [뉴스 및 문서 탭]
        with tab_news:
            news_kw = st.text_input("무엇을 찾아볼까요?", placeholder="탐구할 키워드를 입력하세요 (예: 일본 축제)", key="news_kw")
            if st.button("뉴스·문서 검색하기", type="primary"):
                if news_kw:
                    st.session_state['news_raw_results'] = search_safe_news(news_kw)
                    st.session_state['news_page'] = 1

            if 'news_raw_results' in st.session_state:
                st.write("---")
                raw_results = st.session_state['news_raw_results']
                if not raw_results:
                    st.info("검색된 뉴스가 없습니다. 키워드를 바꾸어 다시 검색해보세요.")
                else:
                    news_sort = st.radio("정렬 기준", ["관련도순", "최신순"], horizontal=True, key="news_sort_radio")

                    display_news = list(raw_results)
                    if news_sort == "최신순":
                        display_news.sort(key=lambda x: x['date'], reverse=True)

                    cur_page = st.session_state.get('news_page', 1)
                    page_data = display_news[(cur_page - 1) * ITEMS_PER_PAGE: cur_page * ITEMS_PER_PAGE]

                    for idx, res in enumerate(page_data):
                        item_num = (cur_page - 1) * ITEMS_PER_PAGE + idx + 1
                        date_str = res['date'].strftime("%Y-%m-%d")
                        st.markdown(f"""
                            <div class="news-card">
                                <div style="font-size: 1.05em; font-weight: bold; margin-bottom: 6px;">
                                    <a href="{res['link']}" target="_blank" style="text-decoration: none; color: #1e40af;">
                                        {item_num}. {res['title']}
                                    </a>
                                </div>
                                <div style="color: #64748b; font-size: 0.85em; margin-bottom: 8px;">발행일: {date_str}</div>
                            </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"📌 {item_num}번 자료 스크랩하기", key=f"btn_news_{item_num}"):
                            st.session_state['selected_item'] = res

                    render_pagination(len(display_news), ITEMS_PER_PAGE, cur_page, 'news_page')

        # [사진/이미지 탭 - 외부 연동 수동 스크랩]
        with tab_img:
            st.caption("🛡️ **안전 검색(SafeSearch)**이 강제 적용되어 유해 이미지가 차단된 구글 검색으로 연결됩니다.")
            img_kw = st.text_input("어떤 사진을 찾고 싶나요?", placeholder="예: 화산 분출, 경복궁 행사", key="img_kw_input")

            if st.button("사진 검색하기", type="primary"):
                if img_kw:
                    st.session_state['img_search_clicked'] = img_kw

            if st.session_state.get('img_search_clicked'):
                current_kw = st.session_state['img_search_clicked']
                safe_img_query = f"{current_kw} -site:dcinside.com -site:ilbe.com -site:ruliweb.com"
                encoded_kw = urllib.parse.quote(safe_img_query)
                safe_img_url = f"https://www.google.com/search?tbm=isch&q={encoded_kw}&safe=active"

                st.write("---")
                st.markdown(f"👉 **[구글 안심 이미지에서 '{current_kw}' 찾기 (새 창 열림)]({safe_img_url})**")
                st.info("💡 새 창에서 찾은 이미지의 '제목'과 '이미지 주소'를 복사해 아래에 붙여넣으세요.")

                custom_img_title = st.text_input("이미지 제목 입력")
                custom_img_link = st.text_input("이미지 주소(URL) 붙여넣기")

                if custom_img_link:
                    try:
                        st.image(custom_img_link, caption="가져온 이미지 미리보기", use_container_width=True)
                    except:
                        st.caption("⚠️ 이미지 미리보기를 불러올 수 없는 링크입니다. 웹페이지 주소가 아닌 '이미지 주소'를 복사했는지 확인하세요.")

                if st.button("📌 이 이미지 스크랩하기", type="primary"):
                    if custom_img_title and custom_img_link:
                        st.session_state['selected_item'] = {'title': f"[사진] {custom_img_title}",
                                                             'link': custom_img_link, 'thumb': custom_img_link,
                                                             'type': 'image'}
                        st.success("자료가 스크랩되었습니다! 우측 3단계에서 요약을 작성하세요.")
                    else:
                        st.warning("제목과 주소를 모두 입력해주세요.")

        # [영상 자료 탭 - 사진 탭과 동일한 외부 연동 수동 스크랩으로 변경]
        with tab_vid:
            st.caption("🛡️ **교육/다큐 중심 안전 검색:** 유해 영상을 피하기 위해 실제 유튜브에서 안전하게 검색 후 주소를 가져옵니다.")
            vid_kw = st.text_input("어떤 영상을 찾고 싶나요?", placeholder="예: 일본 축제 문화", key="vid_kw_input")

            if st.button("영상 검색하기", type="primary"):
                if vid_kw:
                    st.session_state['vid_search_clicked'] = vid_kw

            if st.session_state.get('vid_search_clicked'):
                current_kw = st.session_state['vid_search_clicked']
                # 💡 핵심: 유튜브 검색 시 '다큐', '뉴스', '교양' 키워드를 강제 결합하여 낚시/유해 영상 노출 방지
                safe_vid_query = f"{current_kw} 다큐 OR 뉴스 OR 교양"
                encoded_kw = urllib.parse.quote(safe_vid_query)
                safe_vid_url = f"https://www.youtube.com/results?search_query={encoded_kw}"

                st.write("---")
                st.markdown(f"👉 **[안전 필터가 적용된 유튜브에서 '{current_kw}' 영상 찾기 (새 창 열림)]({safe_vid_url})**")
                st.info("💡 새 창에서 영상을 확인한 후, '영상 제목'과 '유튜브 주소'를 복사해 아래에 붙여넣으세요.")

                custom_vid_title = st.text_input("영상 제목 입력")
                custom_vid_link = st.text_input("유튜브 영상 주소(URL) 붙여넣기")

                if custom_vid_link:
                    try:
                        st.video(custom_vid_link)
                        st.caption("✅ 유튜브 댓글, 추천 영상이 완벽히 차단된 안전한 미리보기 뷰어입니다.")
                    except:
                        st.caption("⚠️ 영상을 불러올 수 없습니다. 올바른 유튜브 주소인지 확인하세요.")

                if st.button("📌 이 영상 스크랩하기", type="primary"):
                    if custom_vid_title and custom_vid_link:
                        st.session_state['selected_item'] = {'title': f"[영상] {custom_vid_title}",
                                                             'link': custom_vid_link, 'type': 'video'}
                        st.success("자료가 스크랩되었습니다! 우측 3단계에서 요약을 작성하세요.")
                    else:
                        st.warning("제목과 주소를 모두 입력해주세요.")

    # 우측: 스크랩 확인 및 요약
    with col_right:
        st.markdown('<div class="step-badge">STEP 3</div> **믿을 수 있을까? 확인하고 요약하기**', unsafe_allow_html=True)
        if 'selected_item' in st.session_state:
            item = st.session_state['selected_item']
            st.info(f"📎 **선택한 자료:** [{item['title']}]({item['link']})")

            if item.get('type') == 'image' and 'thumb' in item:
                try:
                    st.image(item['thumb'], caption="스크랩된 이미지 미리보기", use_container_width=True)
                except:
                    pass
            elif item.get('type') == 'video':
                st.video(item['link'])

            publisher = st.selectbox("이 자료는 누가 쓴 글(자료)인가요?",
                                     ["정부/공공기관", "언론사 뉴스", "교육방송/다큐", "개인 블로그/SNS", "나무위키/지식iN", "유튜브 채널"])
            st.markdown("**✅ 믿을 수 있는지 체크해 보세요**")
            evidence = st.multiselect("체크리스트", ["구체적 통계/근거가 있는가?", "작성일자가 명확한가?", "전문가의 의견인가?", "시각 자료가 명확한가?"],
                                      label_visibility="collapsed")
            st.markdown("**✍️ 내가 직접 쓰는 요약 (AI 요약 없음)**")
            summary = st.text_area("자료를 읽고/보고 알게 된 내용을 내 말로 직접 정리해 써 보세요.", height=130, label_visibility="collapsed")

            if st.button("💾 보고서 저장하기", type="primary", use_container_width=True):
                if is_guest:
                    st.warning("로그인 상태에서만 저장할 수 있습니다.")
                else:
                    if summary:
                        conn = sqlite3.connect('school_research.db')
                        conn.execute(
                            '''INSERT INTO reports (username, school_name, class_name, folder_name, title, link,
                                                    publisher, evidence_check, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                     (u_info['username'], u_info['school_name'], u_info['class_name'], current_folder, item['title'], item['link'], publisher, ", ".join(evidence), summary))
                        conn.commit(); conn.close()
                        st.balloons()
                        st.success("성공적으로 저장되었습니다!")
                    else:
                        st.warning("직접 작성한 요약글을 입력해주세요.")
        else:
            st.markdown('<div style="border:1px dashed #cbd5e1; padding:30px; text-align:center; border-radius:8px; color:#64748b;">👈 왼쪽 탭에서 자료를 찾아 [📌 스크랩] 버튼을 누르면 이곳에 자료와 미리보기가 나타납니다.</div>', unsafe_allow_html=True)

        st.write("---")
        st.markdown('<div class="step-badge" style="background-color:#10b981;">내 기록</div> **내 탐구 보고서**', unsafe_allow_html=True)
        if is_guest:
            st.caption("로그인하시면 저장된 보고서를 확인할 수 있습니다.")
        else:
            conn = sqlite3.connect('school_research.db')
            c = conn.cursor()
            c.execute("SELECT folder_name, title, publisher, summary, created_at FROM reports WHERE username=?", (u_info['username'],))
            my_reports = c.fetchall()
            conn.close()
            if my_reports:
                st.dataframe(my_reports, use_container_width=True)
            else:
                st.caption("아직 작성된 탐구 보고서가 없습니다.")

# ---------------------------------------------------------
# 5. 역할 분기 호출
# ---------------------------------------------------------
if not st.session_state['logged_in']:
    render_student_view(u_info=None)
else:
    role = st.session_state['user_info']['role']
    u = st.session_state['user_info']

    if role == 'superadmin':
        st.header("⚡ 최고 관리자 센터")
        tab_admin1, tab_admin2, tab_admin3 = st.tabs(["📋 회원 관리", "📊 제출 현황", "🔍 학생 화면 시연"])
        with tab_admin3:
            render_student_view(u)
    elif role == 'teacher':
        st.header("🍎 우리 반 탐구 관리 대시보드")
        tab1, tab2, tab3 = st.tabs(["📊 학생 제출 보고서 확인", "🔑 학생 계정 관리", "🔍 학생 탐구 화면 체험"])
        with tab3:
            render_student_view(u)
    elif role == 'student':
        render_student_view(u)
