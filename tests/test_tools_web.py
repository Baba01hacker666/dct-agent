from unittest.mock import patch
from dct.tools.web import _strip_html, _extract_title


def test_strip_html_basic():
    html = "<html><body><h1>Hello World</h1><p>This is a test.</p></body></html>"
    text = _strip_html(html)
    assert "Hello World" in text
    assert "This is a test." in text


def test_strip_html_decomposes_layout_and_scripts():
    html = """
    <html>
        <head>
            <style>body { background: #fff; }</style>
            <script>console.log("hello");</script>
        </head>
        <body>
            <header>
                <nav><a href="/">Home</a></nav>
            </header>
            <main>
                <aside>Sidebar content</aside>
                <article>
                    <h1>Article Title</h1>
                    <p>Main content here.</p>
                </article>
                <form action="/submit">
                    <input type="text" name="name" />
                </form>
            </main>
            <footer>
                <p>&copy; 2026</p>
            </footer>
        </body>
    </html>
    """
    text = _strip_html(html)

    # Decomposed elements should be gone
    assert "console.log" not in text
    assert "background: #fff" not in text
    assert "Home" not in text
    assert "Sidebar content" not in text
    assert "name" not in text
    assert "2026" not in text

    # Main content should remain
    assert "Article Title" in text
    assert "Main content here." in text


def test_strip_html_entity_unescaping():
    html = "Hello &amp; welcome &lt;back&gt;! Here is a &#39;quote&#39; and &nbsp; space."
    text = _strip_html(html)
    assert "Hello & welcome <back>! Here is a 'quote' and   space." in text


def test_strip_html_whitespace_handling():
    html = """
    <p>Line 1</p>


    <p>Line 2</p>
    """
    text = _strip_html(html)
    assert text == "Line 1\n\nLine 2"


def test_strip_html_fallback():
    # Simulate bs4 not being installed
    with patch("builtins.__import__") as mock_import:
        original_import = __import__

        def side_effect(name, *args, **kwargs):
            if name == "bs4":
                raise ImportError("Mocked ImportError")
            return original_import(name, *args, **kwargs)

        mock_import.side_effect = side_effect

        html = "<html><body><h1>Hello World</h1><script>alert(1)</script></body></html>"
        text = _strip_html(html)
        assert "Hello World" in text
        assert "alert(1)" not in text


def test_extract_title_bs4():
    html = "<html><head><title>My Nice Website &amp; Blog</title></head><body></body></html>"
    assert _extract_title(html) == "My Nice Website & Blog"


def test_extract_title_regex_fallback():
    # If bs4 is missing
    with patch("builtins.__import__") as mock_import:
        original_import = __import__

        def side_effect(name, *args, **kwargs):
            if name == "bs4":
                raise ImportError("Mocked ImportError")
            return original_import(name, *args, **kwargs)

        mock_import.side_effect = side_effect

        html = "<html><head><title>Fallback Title &amp; More</title></head><body></body></html>"
        assert _extract_title(html) == "Fallback Title & More"
