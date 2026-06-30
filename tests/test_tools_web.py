from unittest.mock import patch, MagicMock
import httpx
from dct.tools.web import _strip_html, _extract_title, fetch_url


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
    html = (
        "Hello &amp; welcome &lt;back&gt;! Here is a &#39;quote&#39; and &nbsp; space."
    )
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


@patch("dct.tools.web._get_validated_response")
@patch("dct.tools.web.validate_url")
def test_fetch_url_html(mock_validate_url, mock_get_validated_response):
    mock_validate_url.return_value = None
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = (
        "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
    )
    mock_response.url = "https://example.com"
    mock_response.status_code = 200
    mock_get_validated_response.return_value = mock_response

    result = fetch_url("example.com")

    mock_validate_url.assert_called_with("https://example.com")
    assert result.ok is True
    assert result.url == "https://example.com"
    assert result.status == 200
    assert result.title == "Test"
    assert "Content" in result.content


@patch("dct.tools.web._get_validated_response")
@patch("dct.tools.web.validate_url")
def test_fetch_url_plain_text(mock_validate_url, mock_get_validated_response):
    mock_validate_url.return_value = None
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.text = (
        "<html><body>Plain text content that might look like HTML</body></html>"
    )
    mock_response.url = "https://example.com"
    mock_response.status_code = 200
    mock_get_validated_response.return_value = mock_response

    result = fetch_url("https://example.com")

    assert result.ok is True
    assert (
        result.content
        == "<html><body>Plain text content that might look like HTML</body></html>"
    )


@patch("dct.tools.web.validate_url")
def test_fetch_url_validation_error(mock_validate_url):
    mock_validate_url.return_value = "Invalid URL"

    result = fetch_url("http://bad-url.com")

    assert result.ok is False
    assert result.message == "Invalid URL"


@patch("dct.tools.web._get_validated_response")
@patch("dct.tools.web.validate_url")
def test_fetch_url_request_exception(mock_validate_url, mock_get_validated_response):
    mock_validate_url.return_value = None
    mock_get_validated_response.side_effect = httpx.RequestError(
        "Connection error", request=MagicMock()
    )

    result = fetch_url("https://example.com")

    assert result.ok is False
    assert "Connection error" in result.message


@patch("dct.tools.web._get_validated_response")
@patch("dct.tools.web.validate_url")
def test_fetch_url_truncation(mock_validate_url, mock_get_validated_response):
    mock_validate_url.return_value = None
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.text = "A" * 50_000
    mock_response.url = "https://example.com"
    mock_response.status_code = 200
    mock_get_validated_response.return_value = mock_response

    result = fetch_url("https://example.com", max_chars=40_000)

    assert result.ok is True
    assert len(result.content) == 40_000
