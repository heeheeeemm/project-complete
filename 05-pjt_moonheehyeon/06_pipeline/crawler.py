"""
crawler.py : 토스증권 커뮤니티 댓글 수집 모듈

03_toss_comments 에서 만든 함수를 한 파일에 모았습니다.
다른 파일에서는 fetch_comments() 하나만 가져다 쓰면 됩니다.

    from crawler import fetch_comments
    comments = fetch_comments('삼성전자', limit=20)
"""

import time
import re
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

MAIN_URL = 'https://www.tossinvest.com/'


# ------------------------------------------------------------
# 브라우저 실행 (headless 옵션 추가)
# ------------------------------------------------------------
def get_driver(headless=False):
    """옵션을 적용한 크롬 브라우저를 실행해 돌려준다"""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    if headless:
        # 창 없이 백그라운드로 실행 (웹 서비스 안에서 실행할 때)
        chrome_options.add_argument('--headless=new')
        # 창 크기를 지정하지 않으면 작은 화면(모바일) 배치로 그려질 수 있음
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--remote-debugging-pipe')
    # Selenium Manager가 이전에 내려받은 드라이버가 있으면 네트워크 없이 재사용한다.
    driver_root = Path.home() / '.cache' / 'selenium' / 'chromedriver' / 'win64'
    cached_drivers = sorted(driver_root.glob('*/chromedriver.exe'), reverse=True)
    service = Service(str(cached_drivers[0])) if cached_drivers else Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    # 토스 페이지가 응답하지 않아도 한 요청이 무기한 멈추지 않게 한다.
    driver.set_page_load_timeout(25)
    return driver


# ------------------------------------------------------------
# 03_toss_comments 에서 만든 함수
# ------------------------------------------------------------
def open_main(driver):
    """토스증권 메인 페이지에 접속하고, 화면이 그려질 때까지 기다린다"""
    driver.get(MAIN_URL)

    # 왼쪽 메뉴(#ts-lnb)는 자바스크립트가 화면을 그린 뒤에 나타나는 요소
    # 최대 10초 동안 반복 확인 -> 나타나는 순간 바로 다음 줄로 진행
    # 10초가 지나도 없으면 TimeoutException 발생
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#ts-lnb'))
    )
    print('[접속] 토스증권 메인 페이지 로딩 완료')


def close_popups(driver):
    """첫 진입 시 뜨는 안내 팝업의 닫기 버튼을 모두 누른다"""
    # 팝업은 페이지가 그려진 뒤 조금 늦게 뜨는 경우가 있어 잠깐 대기
    time.sleep(0.3)

    # XPath: //태그[@속성='값'] -> aria-label 이 '닫기'인 모든 button
    for close_btn in driver.find_elements(By.XPATH, "//button[@aria-label='닫기']"):
        try:
            if close_btn.is_displayed():
                # 일부 닫기 버튼은 다른 요소(왼쪽 메뉴)에 가려져 일반 click() 이 실패함
                # -> 자바스크립트로 버튼을 직접 클릭
                driver.execute_script('arguments[0].click();', close_btn)
                time.sleep(0.5)
        except Exception:
            # 닫기에 실패해도 진행에는 큰 문제가 없으므로 넘어감
            pass


def search_company(driver, company_name):
    """'/' 단축키로 검색창을 열고 회사명을 검색한다"""
    close_popups(driver)

    # 단축키는 페이지 전체(body)에 포커스가 있어야 동작
    driver.execute_script('document.activeElement.blur(); document.body.focus();')
    ActionChains(driver).send_keys('/').perform()

    # 검색 모달 안의 입력창이 나타날 때까지 대기
    search_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[@placeholder='검색어를 입력해주세요']")
        )
    )
    search_input.send_keys(company_name)

    def read_first_result_name(current_driver):
        """DOM이 교체되어도 첫 검색 결과를 새로 찾아 종목명만 읽는다."""
        all_lines = []
        for result in current_driver.find_elements(
            By.CSS_SELECTOR, "a[href*='/stocks/']"
        ):
            try:
                lines = [line.strip() for line in result.text.splitlines() if line.strip()]
            except StaleElementReferenceException:
                continue
            all_lines.extend(lines)

        # 부분 검색어가 포함된 줄을 우선 사용한다.
        for line in all_lines:
            if company_name.replace(' ', '') in line.replace(' ', ''):
                return line
        # 검색어 표기가 다른 경우 가격·등락률이 아닌 첫 짧은 문장을 사용한다.
        for line in all_lines:
            if len(line) <= 30 and not re.search(r'[₩$%]|\d{3,}', line):
                return line
        return False

    try:
        result_name = WebDriverWait(driver, 2, poll_frequency=0.1).until(
            read_first_result_name
        )
    except TimeoutException:
        result_name = ''

    # 검색 결과가 나타나는 동안 React가 input을 교체할 수 있으므로
    # 이전 search_input을 다시 사용하지 않고 현재 활성 화면에 Enter를 보낸다.
    ActionChains(driver).send_keys(Keys.ENTER).perform()
    print(f'[검색] {company_name}')
    return result_name


def get_stock_code(driver):
    """검색 후 이동한 종목 페이지 주소에서 종목 코드를 꺼낸다"""
    # 검색이 끝나면 .../stocks/종목코드/order 로 이동 -> 주소가 바뀔 때까지 대기
    WebDriverWait(driver, 15).until(EC.url_contains('/order'))

    # 예) https://www.tossinvest.com/stocks/A005930/order
    #     split('/') -> [..., 'stocks', 'A005930', 'order']
    #     'stocks' 바로 다음 칸이 종목 코드
    parts = driver.current_url.split('/')
    stock_code = parts[parts.index('stocks') + 1]
    print(f'[종목 코드] {stock_code} ({driver.current_url})')
    return stock_code


def get_company_name(driver, fallback):
    """종목 상세 화면에서 실제 매칭된 공식 종목명을 읽는다."""
    for selector in ("meta[property='og:title']", "meta[name='twitter:title']"):
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                title = element.get_attribute('content').strip()
            except StaleElementReferenceException:
                continue
            candidates = [part.strip() for part in re.split(r'[-|]', title)]
            for candidate in candidates:
                if candidate and '토스증권' not in candidate:
                    return candidate.split(' 주가', 1)[0].strip()

    for selector in ('#stock-content h1', 'main h1', 'h1'):
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                name = element.text.strip()
            except StaleElementReferenceException:
                continue
            if name:
                return name

    # 화면 구조가 바뀐 경우 브라우저 제목의 첫 부분을 보조 수단으로 사용한다.
    for candidate in re.split(r'[-|]', driver.title):
        candidate = candidate.strip()
        if candidate and '토스증권' not in candidate:
            return candidate.split(' 주가', 1)[0].strip()
    return fallback


def open_community(driver, stock_code):
    """종목 코드로 커뮤니티 페이지 주소를 만들어 바로 이동한다"""
    community_url = f'https://www.tossinvest.com/stocks/{stock_code}/community'
    driver.get(community_url)

    # 댓글 영역(#stock-content)이 나타날 때까지 대기
    # 시간이 초과해도 프로그램을 멈추지 않고 안내만 출력
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#stock-content'))
        )
        print('[커뮤니티] 댓글 영역 로딩 완료')
    except TimeoutException:
        print('[커뮤니티] 10초 안에 댓글 영역을 찾지 못했습니다. 화면을 확인하세요.')


# 댓글 본문 선택자 : 클래스 이름이 아니라 "역할"을 나타내는 속성을 기준으로
#   - 개발자 도구에 보이는 클래스 이름(예: tc3tm85)은 사이트를 새로 배포할 때마다 바뀜
#   - style 안의 --fold-after-lines("N줄까지만 보여주고 접기")는 게시글 본문에만 있음
COMMENT_SELECTOR = "span[style*='--fold-after-lines']"


def read_visible_comments(driver, comments):
    """지금 화면에 보이는 댓글을 comments 리스트에 추가한다 (중복 제외)"""
    for span in driver.find_elements(By.CSS_SELECTOR, COMMENT_SELECTOR):
        try:
            text = span.text.strip()
        except StaleElementReferenceException:
            continue
        if text and text not in comments:
            comments.append(text)


def has_new_visible_comment(driver, known_comments):
    """현재 화면에 아직 수집하지 않은 댓글이 나타났는지 확인한다."""
    for span in driver.find_elements(By.CSS_SELECTOR, COMMENT_SELECTOR):
        try:
            text = span.text.strip()
        except StaleElementReferenceException:
            continue
        if text and text not in known_comments:
            return True
    return False


def find_scroll_container(driver):
    """댓글 목록을 감싼 내부 스크롤 영역을 찾는다 (없으면 None)"""
    # 댓글 목록은 페이지 전체(window)가 아니라 내부의 별도 스크롤 상자에서 스크롤됨
    # data-id 가 'base-ui-' 로 시작하고 '-viewport' 로 끝나는 div
    try:
        return driver.find_element(
            By.CSS_SELECTOR, "div[data-id^='base-ui-'][data-id$='-viewport']"
        )
    except Exception:
        return None


def collect_comments(driver, limit=20, max_scroll=30):
    """스크롤을 반복하며 댓글을 최대 limit 개까지 모아 돌려준다"""
    # 첫 댓글이 화면에 그려질 때까지 대기
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, COMMENT_SELECTOR))
        )
    except TimeoutException:
        print('[수집] 댓글을 찾지 못했습니다. 선택자가 바뀌었는지 확인하세요.')
        return []

    comments = []
    prev_count = -1  # 직전 반복의 댓글 개수
    stagnant_rounds = 0  # 댓글 개수가 그대로인 횟수

    for scroll in range(max_scroll):
        read_visible_comments(driver, comments)
        print(f'[수집] 스크롤 {scroll + 1}회 -> 누적 {len(comments)}개')

        # React가 목록을 다시 그릴 수 있으므로 매 반복마다 최신 스크롤 영역을 찾는다.
        scroll_container = find_scroll_container(driver)

        # 목표 개수 도달 또는 스크롤 상자가 없으면 종료
        if len(comments) >= limit or scroll_container is None:
            break

        # 스크롤해도 5번 연속 늘지 않으면 더 이상 댓글이 없다고 판단
        if len(comments) == prev_count:
            stagnant_rounds += 1
            if stagnant_rounds >= 5:
                break
        else:
            stagnant_rounds = 0
        prev_count = len(comments)

        try:
            # 클릭/키 입력 사이에 요소가 교체되는 문제를 피하고 현재 요소를 바로 스크롤한다.
            driver.execute_script(
                'arguments[0].scrollTop = arguments[0].scrollHeight;',
                scroll_container,
            )
        except StaleElementReferenceException:
            # 다음 반복에서 새 요소를 다시 찾는다.
            continue
        # 무조건 1.5초 쉬지 않고 새 댓글이 나타나는 순간 다음 반복으로 넘어간다.
        try:
            WebDriverWait(driver, 1.2, poll_frequency=0.15).until(
                lambda current_driver: has_new_visible_comment(
                    current_driver, comments
                )
            )
        except TimeoutException:
            pass

    # 마지막 스크롤에서 limit 보다 많이 모일 수 있으므로 정확히 잘라서 반환
    return comments[:limit]


# ------------------------------------------------------------
# 외부에서 사용할 함수 : 회사명 => 댓글 리스트
# ------------------------------------------------------------
def fetch_company_data(company_name, limit=20, headless=False):
    """검색 결과 최상단 종목의 공식명과 댓글을 함께 돌려준다."""
    driver = get_driver(headless)
    try:
        open_main(driver)
        searched_name = search_company(driver, company_name)
        stock_code = get_stock_code(driver)
        actual_company = searched_name or get_company_name(driver, company_name)
        open_community(driver, stock_code)
        return {
            'actual_company': actual_company,
            'stock_code': stock_code,
            'comments': collect_comments(driver, limit=limit),
        }
    except TimeoutException:
        # 없는 회사명이면 종목 페이지로 이동하지 못해 시간 초과 발생
        print(f'[수집 실패] {company_name} : 종목 페이지를 찾지 못했습니다.')
        return {'actual_company': '', 'stock_code': '', 'comments': []}
    finally:
        driver.quit()


def fetch_comments(company_name, limit=20, headless=False):
    """기존 실습과 호환되도록 댓글 목록만 돌려준다."""
    return fetch_company_data(company_name, limit, headless)['comments']


# 이 파일을 직접 실행할 때만 동작 (import 할 때는 실행되지 않음)
if __name__ == '__main__':
    for idx, comment in enumerate(fetch_comments('삼성전자', limit=5), 1):
        print(f'{idx:02d}. {comment}')
