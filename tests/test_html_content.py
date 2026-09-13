import pytest
from cement.parse import extract_html


def test_abri_keeps_abstract_outside_metadata_and_drops_menu():
    raw='<title>研究</title><form><div>選單垃圾</div><div id="CCMS_Content">研究標題</div><div class="page-footer">中文摘要：研究方法與結果</div></form>'
    title,pages=extract_html(raw,['https://www.abri.gov.tw/example'])
    assert title=='研究'
    assert '中文摘要' in pages[0]['text'] and '研究標題' in pages[0]['text']
    assert '選單垃圾' not in pages[0]['text']


def test_known_template_missing_region_fails_instead_of_using_navigation():
    with pytest.raises(ValueError,match='region missing'):
        extract_html('<div>menu</div>',['https://www.nist.gov/example'])
    _,pages=extract_html('<nav>menu</nav><main>cement content</main>')
    assert pages[0]['text']=='cement content'
