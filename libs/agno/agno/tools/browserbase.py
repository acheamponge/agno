"""
BrowserbaseTools — cloud browser automation via Browserbase.

Setup:
1. Install: `pip install browserbase playwright && playwright install`
2. Set env vars:
   - BROWSERBASE_API_KEY: Your Browserbase API key
   - BROWSERBASE_PROJECT_ID: Your Browserbase project ID

Credentials:
- Sign up at https://browserbase.com
- Create a project and get your API key from the dashboard
- Copy the Project ID from project settings
"""

import json
import re
from os import getenv
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

try:
    from browserbase import Browserbase
except ImportError:
    raise ImportError("`browserbase` not installed. Please install using `pip install browserbase`")


BROWSERBASE_INSTRUCTIONS = """
## BrowserbaseTools Usage

You have access to a cloud browser for web automation. Key tools:

- `navigate_to(url)`: Go to a URL
- `get_page_content()`: Get the current page content
- `click(selector)`: Click an element by CSS selector
- `type_text(selector, text)`: Type into an input field
- `fill_form({selector: value, ...})`: Fill multiple form fields
- `screenshot(path)`: Save a screenshot
- `wait_for_selector(selector)`: Wait for an element to appear

CSS Selector Examples:
- `#login-button` — element with id="login-button"
- `.submit-btn` — element with class="submit-btn"
- `input[name="email"]` — input with name="email"
- `button[type="submit"]` — submit button

The browser session persists between calls. Always close when done.
"""


class BrowserbaseTools(Toolkit):
    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        base_url: Optional[str] = None,
        enable_navigate_to: bool = True,
        enable_screenshot: bool = True,
        enable_get_page_content: bool = True,
        enable_close_session: bool = True,
        enable_click: bool = False,
        enable_type: bool = False,
        enable_get_element_text: bool = False,
        enable_fill_form: bool = False,
        enable_wait_for_selector: bool = False,
        enable_get_session_recording: bool = False,
        all: bool = False,
        block_ads: bool = False,
        solve_captchas: bool = False,
        parse_html: bool = True,
        max_content_length: Optional[int] = 100000,
        **kwargs,
    ):
        """Initialize BrowserbaseTools.

        Args:
            api_key (str, optional): Browserbase API key.
            project_id (str, optional): Browserbase project ID.
            base_url (str, optional): Custom Browserbase API endpoint URL (NOT the target website URL).
                Only use this if you're using a self-hosted Browserbase instance or need to connect to a different region.
            enable_navigate_to (bool): Enable the navigate_to tool. Defaults to True.
            enable_screenshot (bool): Enable the screenshot tool. Defaults to True.
            enable_get_page_content (bool): Enable the get_page_content tool. Defaults to True.
            enable_close_session (bool): Enable the close_session tool. Defaults to True.
            enable_click (bool): Enable the click tool for clicking elements. Defaults to False.
            enable_type (bool): Enable the type tool for typing text. Defaults to False.
            enable_get_element_text (bool): Enable getting text from specific elements. Defaults to False.
            enable_fill_form (bool): Enable filling form fields. Defaults to False.
            enable_wait_for_selector (bool): Enable waiting for elements. Defaults to False.
            enable_get_session_recording (bool): Enable getting session recording URL. Defaults to False.
            all (bool): Enable all tools. Defaults to False.
            block_ads (bool): Block ads in browser sessions. Defaults to False.
            solve_captchas (bool): Auto-solve CAPTCHAs. Defaults to False.
            parse_html (bool): If True, extract only visible text content instead of raw HTML. Defaults to True.
                This significantly reduces token usage and is recommended for most use cases.
            max_content_length (int, optional): Maximum character length for page content. Defaults to 100000.
                Content exceeding this limit will be truncated with a notice. Set to None for no limit.
        """
        self.parse_html = parse_html
        self.max_content_length = max_content_length
        self.block_ads = block_ads
        self.solve_captchas = solve_captchas

        self.api_key = api_key or getenv("BROWSERBASE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "BROWSERBASE_API_KEY is required. Please set the BROWSERBASE_API_KEY environment variable."
            )

        self.project_id = project_id or getenv("BROWSERBASE_PROJECT_ID")
        if not self.project_id:
            raise ValueError(
                "BROWSERBASE_PROJECT_ID is required. Please set the BROWSERBASE_PROJECT_ID environment variable."
            )

        self.base_url = base_url or getenv("BROWSERBASE_BASE_URL")

        # Initialize the Browserbase client with optional base_url
        if self.base_url:
            self.app = Browserbase(api_key=self.api_key, base_url=self.base_url)
            log_debug(f"Using custom Browserbase API endpoint: {self.base_url}")
        else:
            self.app = Browserbase(api_key=self.api_key)

        # Sync playwright state
        self._playwright = None
        self._browser = None
        self._page = None

        # Async playwright state
        self._async_playwright = None
        self._async_browser = None
        self._async_page = None

        # Shared session state
        self._session = None
        self._connect_url = None

        # Build tools lists
        # sync tools: used by agent.run() and agent.print_response()
        # async tools: used by agent.arun() and agent.aprint_response()
        tools: List[Any] = []
        async_tools: List[tuple] = []

        if all or enable_navigate_to:
            tools.append(self.navigate_to)
            async_tools.append((self.anavigate_to, "navigate_to"))
        if all or enable_screenshot:
            tools.append(self.screenshot)
            async_tools.append((self.ascreenshot, "screenshot"))
        if all or enable_get_page_content:
            tools.append(self.get_page_content)
            async_tools.append((self.aget_page_content, "get_page_content"))
        if all or enable_close_session:
            tools.append(self.close_session)
            async_tools.append((self.aclose_session, "close_session"))
        if all or enable_click:
            tools.append(self.click)
            async_tools.append((self.aclick, "click"))
        if all or enable_type:
            tools.append(self.type_text)
            async_tools.append((self.atype_text, "type_text"))
        if all or enable_get_element_text:
            tools.append(self.get_element_text)
            async_tools.append((self.aget_element_text, "get_element_text"))
        if all or enable_fill_form:
            tools.append(self.fill_form)
            async_tools.append((self.afill_form, "fill_form"))
        if all or enable_wait_for_selector:
            tools.append(self.wait_for_selector)
            async_tools.append((self.await_for_selector, "wait_for_selector"))
        if all or enable_get_session_recording:
            tools.append(self.get_session_recording)
            async_tools.append((self.aget_session_recording, "get_session_recording"))

        super().__init__(
            name="browserbase_tools",
            tools=tools,
            async_tools=async_tools,
            instructions=BROWSERBASE_INSTRUCTIONS,
            **kwargs,
        )

    def _ensure_session(self):
        """Ensures a session exists, creating one if needed."""
        if not self._session:
            try:
                browser_settings: Dict[str, Any] = {}
                if self.block_ads:
                    browser_settings["blockAds"] = True
                if self.solve_captchas:
                    browser_settings["solveCaptchas"] = True

                create_kwargs: Dict[str, Any] = {"project_id": self.project_id}
                if browser_settings:
                    create_kwargs["browser_settings"] = browser_settings

                self._session = self.app.sessions.create(**create_kwargs)  # type: ignore
                self._connect_url = self._session.connect_url if self._session else ""  # type: ignore
                if self._session:
                    log_debug(f"Created new session with ID: {self._session.id}")
            except Exception:
                logger.exception("Failed to create session")
                raise

    def _initialize_browser(self, connect_url: Optional[str] = None):
        """
        Initialize sync browser connection if not already initialized.
        Use provided connect_url or ensure we have a session with a connect_url
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "`playwright` not installed. Please install using `pip install playwright` and run `playwright install`"
            )

        if connect_url:
            self._connect_url = connect_url if connect_url else ""  # type: ignore
        elif not self._connect_url:
            self._ensure_session()

        if not self._playwright:
            self._playwright = sync_playwright().start()  # type: ignore
            if self._playwright:
                self._browser = self._playwright.chromium.connect_over_cdp(self._connect_url)
            context = self._browser.contexts[0] if self._browser else ""
            self._page = context.pages[0] or context.new_page()  # type: ignore

    def _cleanup(self):
        """Clean up sync browser resources."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    def _create_session(self) -> Dict[str, str]:
        """Creates a new browser session.

        Returns:
            Dictionary containing session details including session_id and connect_url.
        """
        self._ensure_session()
        return {
            "session_id": self._session.id if self._session else "",
            "connect_url": self._session.connect_url if self._session else "",
        }

    def navigate_to(self, url: str, connect_url: Optional[str] = None) -> str:
        """Navigates to a URL.

        Args:
            url (str): The URL to navigate to
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with navigation status
        """
        try:
            self._initialize_browser(connect_url)
            if self._page:
                self._page.goto(url, wait_until="networkidle")
            result = {"status": "success", "title": self._page.title() if self._page else "", "url": url}
            return json.dumps(result)
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e), "url": url})

    def screenshot(self, path: str, full_page: bool = True, connect_url: Optional[str] = None) -> str:
        """Takes a screenshot of the current page.

        Args:
            path (str): Where to save the screenshot
            full_page (bool): Whether to capture the full page
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string confirming screenshot was saved
        """
        try:
            self._initialize_browser(connect_url)
            if self._page:
                self._page.screenshot(path=path, full_page=full_page)
            return json.dumps({"status": "success", "path": path})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e), "path": path})

    def _extract_text_content(self, html: str) -> str:
        """Extract visible text content from HTML, removing scripts, styles, and tags.

        Args:
            html: Raw HTML content

        Returns:
            Cleaned text content
        """
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        # Remove all HTML tags
        html = re.sub(r"<[^>]+>", " ", html)
        # Decode common HTML entities
        html = html.replace("&nbsp;", " ")
        html = html.replace("&amp;", "&")
        html = html.replace("&lt;", "<")
        html = html.replace("&gt;", ">")
        html = html.replace("&quot;", '"')
        html = html.replace("&#39;", "'")
        # Normalize whitespace
        html = re.sub(r"\s+", " ", html)
        return html.strip()

    def _truncate_content(self, content: str) -> str:
        """Truncate content if it exceeds max_content_length.

        Args:
            content: The content to potentially truncate

        Returns:
            Original or truncated content with notice
        """
        if self.max_content_length is None or len(content) <= self.max_content_length:
            return content

        truncated = content[: self.max_content_length]
        return f"{truncated}\n\n[Content truncated. Original length: {len(content)} characters. Showing first {self.max_content_length} characters.]"

    def get_page_content(self, connect_url: Optional[str] = None) -> str:
        """Gets the content of the current page.

        Args:
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with page content (text-only if parse_html=True, otherwise raw HTML)
        """
        try:
            self._initialize_browser(connect_url)
            if not self._page:
                return json.dumps({"status": "error", "message": "No page available"})

            raw_content = self._page.content()
            url = self._page.url
            title = self._page.title()

            if self.parse_html:
                content = self._extract_text_content(raw_content)
            else:
                content = raw_content

            content = self._truncate_content(content)
            return json.dumps({"status": "success", "url": url, "title": title, "content": content})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e)})

    def close_session(self) -> str:
        """Closes a browser session.

        Returns:
            JSON string with closure status
        """
        try:
            self._cleanup()
            self._session = None
            self._connect_url = None

            return json.dumps(
                {
                    "status": "closed",
                    "message": "Browser resources cleaned up. Session will auto-close if not already closed.",
                }
            )
        except Exception as e:
            return json.dumps({"status": "warning", "message": f"Cleanup completed with warning: {str(e)}"})

    def click(self, selector: str, connect_url: Optional[str] = None) -> str:
        """Clicks an element on the page.

        Args:
            selector (str): CSS selector of element to click
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with click status
        """
        try:
            self._initialize_browser(connect_url)
            if self._page:
                self._page.click(selector)
            return json.dumps({"status": "success", "selector": selector})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e), "selector": selector})

    def type_text(self, selector: str, text: str, connect_url: Optional[str] = None) -> str:
        """Types text into an input element.

        Args:
            selector (str): CSS selector of input element
            text (str): Text to type
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with typing status
        """
        try:
            self._initialize_browser(connect_url)
            if self._page:
                self._page.fill(selector, text)
            return json.dumps({"status": "success", "selector": selector, "text_length": len(text)})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e), "selector": selector})

    def get_element_text(self, selector: str, connect_url: Optional[str] = None) -> str:
        """Gets text content of a specific element.

        Args:
            selector (str): CSS selector of element
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with the text content or error
        """
        try:
            self._initialize_browser(connect_url)
            if self._page:
                element = self._page.query_selector(selector)
                if element:
                    text = element.inner_text()
                    return json.dumps({"status": "success", "text": text, "selector": selector})
            return json.dumps({"status": "error", "message": f"Element not found: {selector}"})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e)})

    def fill_form(self, form_data: Dict[str, str], connect_url: Optional[str] = None) -> str:
        """Fills multiple form fields at once.

        Args:
            form_data (dict): Dictionary mapping CSS selectors to values
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with fill status
        """
        try:
            self._initialize_browser(connect_url)
            filled: List[str] = []
            if self._page:
                for selector, value in form_data.items():
                    self._page.fill(selector, value)
                    filled.append(selector)
            return json.dumps({"status": "success", "filled_fields": filled})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e)})

    def wait_for_selector(self, selector: str, timeout: int = 30000, connect_url: Optional[str] = None) -> str:
        """Waits for an element to appear on the page.

        Args:
            selector (str): CSS selector to wait for
            timeout (int): Timeout in milliseconds (default 30000)
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with wait status
        """
        try:
            self._initialize_browser(connect_url)
            if self._page:
                self._page.wait_for_selector(selector, timeout=timeout)
            return json.dumps({"status": "success", "selector": selector})
        except Exception as e:
            self._cleanup()
            return json.dumps({"status": "error", "message": str(e), "selector": selector})

    def get_session_recording(self) -> str:
        """Gets the recording URL for the current session.

        Returns:
            JSON string with recording information
        """
        try:
            if not self._session:
                return json.dumps({"status": "error", "message": "No active session"})

            recording = self.app.sessions.recording.retrieve(self._session.id)
            return json.dumps({"status": "success", "recording": str(recording)})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def _ainitialize_browser(self, connect_url: Optional[str] = None):
        """
        Initialize async browser connection if not already initialized.
        Use provided connect_url or ensure we have a session with a connect_url
        """
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "`playwright` not installed. Please install using `pip install playwright` and run `playwright install`"
            )

        if connect_url:
            self._connect_url = connect_url if connect_url else ""  # type: ignore
        elif not self._connect_url:
            self._ensure_session()

        if not self._async_playwright:
            self._async_playwright = await async_playwright().start()  # type: ignore
            if self._async_playwright:
                self._async_browser = await self._async_playwright.chromium.connect_over_cdp(self._connect_url)
            context = self._async_browser.contexts[0] if self._async_browser else None
            if context:
                self._async_page = context.pages[0] if context.pages else await context.new_page()

    async def _acleanup(self):
        """Clean up async browser resources."""
        if self._async_browser:
            await self._async_browser.close()
            self._async_browser = None
        if self._async_playwright:
            await self._async_playwright.stop()
            self._async_playwright = None
        self._async_page = None

    async def anavigate_to(self, url: str, connect_url: Optional[str] = None) -> str:
        """Navigates to a URL asynchronously.

        Args:
            url (str): The URL to navigate to
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with navigation status
        """
        try:
            await self._ainitialize_browser(connect_url)
            if self._async_page:
                await self._async_page.goto(url, wait_until="networkidle")
            title = await self._async_page.title() if self._async_page else ""
            result = {"status": "success", "title": title, "url": url}
            return json.dumps(result)
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e), "url": url})

    async def ascreenshot(self, path: str, full_page: bool = True, connect_url: Optional[str] = None) -> str:
        """Takes a screenshot of the current page asynchronously.

        Args:
            path (str): Where to save the screenshot
            full_page (bool): Whether to capture the full page
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string confirming screenshot was saved
        """
        try:
            await self._ainitialize_browser(connect_url)
            if self._async_page:
                await self._async_page.screenshot(path=path, full_page=full_page)
            return json.dumps({"status": "success", "path": path})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e), "path": path})

    async def aget_page_content(self, connect_url: Optional[str] = None) -> str:
        """Gets the content of the current page asynchronously.

        Args:
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with page content (text-only if parse_html=True, otherwise raw HTML)
        """
        try:
            await self._ainitialize_browser(connect_url)
            if not self._async_page:
                return json.dumps({"status": "error", "message": "No page available"})

            raw_content = await self._async_page.content()
            url = self._async_page.url
            title = await self._async_page.title()

            if self.parse_html:
                content = self._extract_text_content(raw_content)
            else:
                content = raw_content

            content = self._truncate_content(content)
            return json.dumps({"status": "success", "url": url, "title": title, "content": content})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e)})

    async def aclose_session(self) -> str:
        """Closes a browser session asynchronously.

        Returns:
            JSON string with closure status
        """
        try:
            await self._acleanup()
            self._session = None
            self._connect_url = None

            return json.dumps(
                {
                    "status": "closed",
                    "message": "Browser resources cleaned up. Session will auto-close if not already closed.",
                }
            )
        except Exception as e:
            return json.dumps({"status": "warning", "message": f"Cleanup completed with warning: {str(e)}"})

    async def aclick(self, selector: str, connect_url: Optional[str] = None) -> str:
        """Clicks an element on the page asynchronously.

        Args:
            selector (str): CSS selector of element to click
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with click status
        """
        try:
            await self._ainitialize_browser(connect_url)
            if self._async_page:
                await self._async_page.click(selector)
            return json.dumps({"status": "success", "selector": selector})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e), "selector": selector})

    async def atype_text(self, selector: str, text: str, connect_url: Optional[str] = None) -> str:
        """Types text into an input element asynchronously.

        Args:
            selector (str): CSS selector of input element
            text (str): Text to type
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with typing status
        """
        try:
            await self._ainitialize_browser(connect_url)
            if self._async_page:
                await self._async_page.fill(selector, text)
            return json.dumps({"status": "success", "selector": selector, "text_length": len(text)})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e), "selector": selector})

    async def aget_element_text(self, selector: str, connect_url: Optional[str] = None) -> str:
        """Gets text content of a specific element asynchronously.

        Args:
            selector (str): CSS selector of element
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with the text content or error
        """
        try:
            await self._ainitialize_browser(connect_url)
            if self._async_page:
                element = await self._async_page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    return json.dumps({"status": "success", "text": text, "selector": selector})
            return json.dumps({"status": "error", "message": f"Element not found: {selector}"})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e)})

    async def afill_form(self, form_data: Dict[str, str], connect_url: Optional[str] = None) -> str:
        """Fills multiple form fields at once asynchronously.

        Args:
            form_data (dict): Dictionary mapping CSS selectors to values
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with fill status
        """
        try:
            await self._ainitialize_browser(connect_url)
            filled: List[str] = []
            if self._async_page:
                for selector, value in form_data.items():
                    await self._async_page.fill(selector, value)
                    filled.append(selector)
            return json.dumps({"status": "success", "filled_fields": filled})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e)})

    async def await_for_selector(self, selector: str, timeout: int = 30000, connect_url: Optional[str] = None) -> str:
        """Waits for an element to appear on the page asynchronously.

        Args:
            selector (str): CSS selector to wait for
            timeout (int): Timeout in milliseconds (default 30000)
            connect_url (str, optional): The connection URL from an existing session

        Returns:
            JSON string with wait status
        """
        try:
            await self._ainitialize_browser(connect_url)
            if self._async_page:
                await self._async_page.wait_for_selector(selector, timeout=timeout)
            return json.dumps({"status": "success", "selector": selector})
        except Exception as e:
            await self._acleanup()
            return json.dumps({"status": "error", "message": str(e), "selector": selector})

    async def aget_session_recording(self) -> str:
        """Gets the recording URL for the current session asynchronously.

        Returns:
            JSON string with recording information
        """
        try:
            if not self._session:
                return json.dumps({"status": "error", "message": "No active session"})

            recording = self.app.sessions.recording.retrieve(self._session.id)
            return json.dumps({"status": "success", "recording": str(recording)})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
