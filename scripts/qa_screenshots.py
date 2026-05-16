"""Playwright QA for tool result rendering."""
import sys, os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18999"
QA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "tmp", "session-browser-qa", "03-tool-result-full-md-scroll"
)
os.makedirs(QA_DIR, exist_ok=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    # Open first session
    page.goto(f"{BASE}/sessions", wait_until="networkidle")
    href = page.evaluate("""() => {
        var a = document.querySelector('a[href*="/sessions/"]');
        return a ? a.getAttribute('href') : null;
    }""")
    if not href:
        print("ERROR: No sessions found")
        sys.exit(1)

    page.goto(f"{BASE}{href}", wait_until="networkidle", timeout=30000)

    # Switch to Timeline tab
    page.click('button[data-tab="timeline"]')
    page.wait_for_timeout(500)

    # Expand all rounds, LLM cards, subagent cards, and tool cards
    page.evaluate("""() => {
        // Show all detail rows
        document.querySelectorAll('.round-detail-row').forEach(function(el) {
            el.style.display = 'table-row';
        });
        // Open all LLM card bodies
        document.querySelectorAll('.llm-card__body').forEach(function(el) {
            el.classList.add('open');
        });
        // Open all subagent card bodies
        document.querySelectorAll('.subagent-card__body').forEach(function(el) {
            el.classList.add('open');
        });
        // Open all tool detail card bodies
        document.querySelectorAll('.tool-detail-card__body').forEach(function(el) {
            el.classList.add('open');
        });
        // Scroll past the summary table
        window.scrollTo(0, 600);
    }""")
    page.wait_for_timeout(800)

    # Find a tool result block with significant content
    idx = page.evaluate("""() => {
        var blocks = document.querySelectorAll('.tool-result-block');
        for (var i = 0; i < blocks.length; i++) {
            var raw = blocks[i].querySelector('.tool-result-raw');
            if (raw && raw.textContent.length > 500) {
                return i;
            }
        }
        return -1;
    }""")

    print(f"Found tool result block #{idx}")

    if idx >= 0:
        # Get block info
        block_info = page.evaluate(f"""() => {{
            var blocks = document.querySelectorAll('.tool-result-block');
            var block = blocks[{idx}];
            var raw = block.querySelector('.tool-result-raw');
            var wrapper = block.querySelector('.tool-result-wrapper');
            var rect = block.getBoundingClientRect();
            var scrollY = window.scrollY;
            return {{
                textLen: raw ? raw.textContent.length : 0,
                lastChars: raw ? raw.textContent.slice(-200) : '',
                docTop: rect.top + scrollY,
                docHeight: rect.height,
                scrollY: scrollY,
                wrapperMaxHeight: wrapper ? getComputedStyle(wrapper).maxHeight : 'n/a',
                wrapperOverflow: wrapper ? getComputedStyle(wrapper).overflow : 'n/a'
            }};
        }}""")
        print(f"Block textLen={block_info['textLen']}")
        print(f"Last 200 chars: {block_info['lastChars']}")
        print(f"Wrapper: maxHeight={block_info['wrapperMaxHeight']}, overflow={block_info['wrapperOverflow']}")
        print(f"docTop={block_info['docTop']}, docHeight={block_info['docHeight']}")

    # Screenshot 1: Raw view - clip from where the timeline detail starts
    clip_y = 600
    clip_h = min(700, 900)
    page.screenshot(path=os.path.join(QA_DIR, "01-raw-view.png"),
                    clip={"x": 0, "y": 0, "width": 1280, "height": 900})
    print(f"Screenshot raw: {QA_DIR}/01-raw-view.png")

    # Toggle first significant block to MD
    if idx >= 0:
        page.evaluate(f"""() => {{
            var blocks = document.querySelectorAll('.tool-result-block');
            var btn = blocks[{idx}].querySelector('.md-toggle-btn');
            if (btn) btn.click();
        }}""")
        page.wait_for_timeout(500)

        md_check = page.evaluate(f"""() => {{
            var blocks = document.querySelectorAll('.tool-result-block');
            var wrapper = blocks[{idx}].querySelector('.tool-result-wrapper');
            return wrapper ? {{
                hasIsMd: wrapper.classList.contains('is-md'),
                rawDisplay: getComputedStyle(wrapper.querySelector('.tool-result-raw')).display,
                mdDisplay: getComputedStyle(wrapper.querySelector('.tool-result-md')).display
            }} : null;
        }}""")
        print(f"MD toggle result: {md_check}")

    page.screenshot(path=os.path.join(QA_DIR, "02-md-view.png"),
                    clip={"x": 0, "y": 0, "width": 1280, "height": 900})
    print(f"Screenshot MD: {QA_DIR}/02-md-view.png")

    # Screenshot 3: Scroll to show more content
    page.evaluate("() => window.scrollTo(0, 1200)")
    page.wait_for_timeout(500)
    page.screenshot(path=os.path.join(QA_DIR, "03-full-timeline.png"),
                    clip={"x": 0, "y": 0, "width": 1280, "height": 900})
    print(f"Screenshot full: {QA_DIR}/03-full-timeline.png")

    browser.close()
    print("Done!")
