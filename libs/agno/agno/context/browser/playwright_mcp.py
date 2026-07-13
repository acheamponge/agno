"""PlaywrightMCPBackend — browser automation via Playwright's MCP server.

Runs `npx @playwright/mcp@latest` as a subprocess and exposes browser
tools (navigate, snapshot, screenshot, click, type) to the calling agent.

Requires Node.js 18+ (npx downloads the package on first run).
"""

from __future__ import annotations

import platform
from typing import Any, Literal

from agno.context.backend import ContextBackend
from agno.context.provider import Status
from agno.utils.log import log_warning


def _get_platform_user_agent() -> str:
    """Generate a realistic Chrome user agent based on the current platform."""
    system = platform.system()
    if system == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    elif system == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    else:
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class PlaywrightMCPBackend(ContextBackend):
    """Backend for `BrowserContextProvider` that runs Playwright's MCP server."""

    def __init__(
        self,
        *,
        headless: bool = True,
        browser: Literal["chromium", "firefox", "webkit"] = "chromium",
        user_agent: str | None = None,
        use_platform_user_agent: bool = False,
        viewport_size: str | None = None,
        device: str | None = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        tool_name_prefix: str | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.headless = headless
        self.browser = browser
        # Explicit user_agent takes precedence, then platform-based if requested
        if user_agent:
            self.user_agent: str | None = user_agent
        elif use_platform_user_agent:
            self.user_agent = _get_platform_user_agent()
        else:
            self.user_agent = None
        self.viewport_size = viewport_size
        self.device = device
        self.include_tools = include_tools
        self.exclude_tools = exclude_tools
        self.tool_name_prefix = tool_name_prefix
        self.timeout_seconds = timeout_seconds
        self._mcp_tools: Any = None

    def status(self) -> Status:
        mode = "headless" if self.headless else "headed"
        return Status(ok=True, detail=f"playwright-mcp ({self.browser}, {mode})")

    async def astatus(self) -> Status:
        return self.status()

    def get_tools(self) -> list:
        if self._mcp_tools is None:
            self._mcp_tools = self._build_tools()
        return [self._mcp_tools]

    def _build_tools(self) -> Any:
        from mcp import StdioServerParameters

        from agno.tools.mcp import MCPTools

        cmd_args = ["@playwright/mcp@latest"]
        if self.headless:
            cmd_args.append("--headless")
        if self.browser != "chromium":
            cmd_args.append(f"--browser={self.browser}")
        if self.user_agent:
            cmd_args.append(f"--user-agent={self.user_agent}")
        if self.viewport_size:
            cmd_args.append(f"--viewport-size={self.viewport_size}")
        if self.device:
            cmd_args.append(f"--device={self.device}")

        return MCPTools(
            server_params=StdioServerParameters(command="npx", args=cmd_args),
            transport="stdio",
            include_tools=self.include_tools,
            exclude_tools=self.exclude_tools,
            tool_name_prefix=self.tool_name_prefix,
            timeout_seconds=self.timeout_seconds,
        )

    async def asetup(self) -> None:
        """Start the Playwright MCP server and connect.

        On failure, logs a warning; the browser backend will be
        unavailable until the next restart.
        """
        if self._mcp_tools is None:
            self._mcp_tools = self._build_tools()
        if getattr(self._mcp_tools, "initialized", False):
            return
        try:
            await self._mcp_tools._connect()
        except Exception as exc:
            log_warning(f"PlaywrightMCPBackend setup failed — {type(exc).__name__}: {exc}.")
            self._mcp_tools = None

    async def aclose(self) -> None:
        """Stop the MCP server and clear cached state."""
        tools = self._mcp_tools
        self._mcp_tools = None
        if tools is None:
            return
        try:
            await tools.close()
        except Exception as exc:
            log_warning(f"PlaywrightMCPBackend close raised {type(exc).__name__}: {exc}")
