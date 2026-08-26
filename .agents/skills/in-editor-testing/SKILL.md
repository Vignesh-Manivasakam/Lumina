---
name: in-editor-testing
description: Perform silent, headless in-editor browser testing using Playwright MCP without launching external desktop windows.
---

# In-Editor Browser Testing Workflow

When asked to test web endpoints, UI components, or local servers:
1. **Use the Playwright MCP Tools:** Prefer `playwright-headless` MCP tools to navigate, click, fill forms, and assert page states.
2. **Stay Headless:** Do not launch external headful browser windows.
3. **Capture Inline Output:** Return test assertions, console logs, and accessibility tree diffs directly in the chat or test report.
