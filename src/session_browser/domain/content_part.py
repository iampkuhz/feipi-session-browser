"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from session_browser.domain.enums import DomainStrEnum

# 说明:─── ContentPart type constants ──────────────────────────────────────────


class ContentPartType(DomainStrEnum):
    """ContentPartType contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        TEXT: Public contract field or enum value.
        MARKDOWN: Public contract field or enum value.
        JSON: Public contract field or enum value.
        IMAGE: Public contract field or enum value.
        CODE: Public contract field or enum value.
        HTML: Public contract field or enum value.
    """

    TEXT = 'text'
    MARKDOWN = 'markdown'
    JSON = 'json'
    IMAGE = 'image'
    CODE = 'code'
    HTML = 'html'


# 说明:─── Context-level part roles (structural, within API messages) ──────────


class ContextPartType(DomainStrEnum):
    """ContextPartType contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        SYSTEM_PROMPT: Public contract field or enum value.
        USER_MESSAGE: Public contract field or enum value.
        ASSISTANT_MESSAGE: Public contract field or enum value.
        TOOL_RESULT: Public contract field or enum value.
        TOOL_USE: Public contract field or enum value.
        ATTACHMENT: Public contract field or enum value.
        IMAGE_CONTENT: Public contract field or enum value.
        DOCUMENT_CONTENT: Public contract field or enum value.
        UNKNOWN: Public contract field or enum value.
    """

    SYSTEM_PROMPT = 'system_prompt'
    USER_MESSAGE = 'user_message'
    ASSISTANT_MESSAGE = 'assistant_message'
    TOOL_RESULT = 'tool_result'
    TOOL_USE = 'tool_use'
    ATTACHMENT = 'attachment'
    IMAGE_CONTENT = 'image_content'
    DOCUMENT_CONTENT = 'document_content'
    UNKNOWN = 'unknown'


# 说明:─── Detection helpers ───────────────────────────────────────────────────

# Image URL patterns: common image extensions 或 data URIs
_IMAGE_URL_RE = re.compile(
    r'(?i)https?://\S+\.(?:png|jpe?g|gif|webp|svg|bmp|ico|tiff?)(?:\?\S*)?$'
    r'|'
    r'^data:image/'
    r'|'
    r'!\[.*?\]\(https?://\S+\)'  # Markdown 图片语法
)

# JSON detection: starts,使用 { 或 [ 和 parses successfully
_JSON_START_RE = re.compile(r'^\s*[\{\[]')

# HTML detection: starts,使用 一个 tag (possibly,在之后 whitespace/BOM)
_HTML_TAG_RE = re.compile(r'^\s*<[a-zA-Z!/][\s\S]*>', re.DOTALL)

# Code block indicators: fenced code block 或 known code patterns at start
_FENCED_CODE_RE = re.compile(r'^```', re.MULTILINE)

# 说明:Python / JS / etc. patterns that strongly suggest code (not prose)
_CODE_PATTERNS = [
    re.compile(r'^(def |class |async def |import |from .+ import )', re.MULTILINE),
    re.compile(r'^(const |let |var |function |export |import \{)', re.MULTILINE),
    re.compile(r'^(func |package |import \()', re.MULTILINE),  # Go
    re.compile(r'^(pub (fn|struct|enum|mod|use|impl|trait))', re.MULTILINE),  # Rust 语法模式
]

# 说明:Common file extensions that indicate code
_CODE_EXTENSIONS = {
    '.py',
    '.ts',
    '.tsx',
    '.js',
    '.jsx',
    '.rb',
    '.rs',
    '.go',
    '.java',
    '.cpp',
    '.c',
    '.cs',
    '.swift',
    '.kt',
    '.scala',
    '.php',
    '.sh',
    '.bash',
    '.zsh',
    '.R',
    '.pl',
    '.lua',
    '.dart',
    '.ex',
    '.exs',
    '.erl',
    '.hs',
    '.ml',
    '.fs',
    '.clj',
    '.lisp',
    '.rkt',
    '.sql',
    '.proto',
    '.graphql',
    '.tf',
    '.hcl',
    '.nix',
    '.d',
    '.nim',
    '.zig',
    '.v',
    '.vim',
    '.el',
    '.cmake',
    '.gradle',
    '.groovy',
    '.bat',
    '.cmd',
    '.ps1',
    '.awk',
    '.sed',
}

# 说明:Extensions that are NOT code (documents, data, config-as-doc)
_NOT_CODE_EXTENSIONS = {
    '.md',
    '.markdown',
    '.mdx',
    '.txt',
    '.rst',
    '.org',
    '.adoc',
    '.pdf',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.ppt',
    '.pptx',
}


def is_image_url(payload: str) -> bool:
    """is_image_url function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        payload: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not payload:
        return False
    return bool(_IMAGE_URL_RE.search(payload))


def is_json(payload: str) -> bool:
    """is_json function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        payload: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not payload:
        return False
    if not _JSON_START_RE.match(payload):
        return False
    try:
        json.loads(payload)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def is_html(payload: str) -> bool:
    """is_html function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        payload: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not payload:
        return False
    m = _HTML_TAG_RE.match(payload)
    if not m:
        return False
    # Reject,如果 it looks like 一个 single short inline tag in prose
    # (e.g. "Use <code>,用于 inline code")
    first_tag = m.group(0).strip()
    if len(payload.strip()) < 200 and first_tag.count('<') == 1 and first_tag.count('>') == 1:
        # Short text,使用 一个 inline tag — likely prose, not 一个 full HTML doc
        return False
    return True


def is_code_block(payload: str, filename_hint: str = '') -> bool:
    """is_code_block function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        payload: Input value supplied by the caller for this pipeline step.
        filename_hint: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not payload:
        return False

    # 说明:Fenced code
    if _FENCED_CODE_RE.match(payload):
        return True

    # 说明:File extension hint
    if filename_hint:
        lower = filename_hint.lower()
        for ext in _CODE_EXTENSIONS:
            if lower.endswith(ext):
                return True
        for ext in _NOT_CODE_EXTENSIONS:
            if lower.endswith(ext):
                return False

    # Code pattern heuristics (at least 一个 pattern must match near 该 start)
    first_lines = '\n'.join(payload.splitlines()[:10])
    return any(pattern.search(first_lines) for pattern in _CODE_PATTERNS)


def detect_content_type(payload: str, filename_hint: str = '') -> str:
    """detect_content_type function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        payload: Input value supplied by the caller for this pipeline step.
        filename_hint: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not payload or not payload.strip():
        return ContentPartType.TEXT

    if is_image_url(payload):
        return ContentPartType.IMAGE

    if is_json(payload):
        return ContentPartType.JSON

    if is_html(payload):
        return ContentPartType.HTML

    if is_code_block(payload, filename_hint):
        return ContentPartType.CODE

    return ContentPartType.MARKDOWN


# 说明:─── ContentPart model ───────────────────────────────────────────────────


@dataclass
class ContentPart:
    """ContentPart contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        part_type: Public contract field or enum value.
        content: Public contract field or enum value.
        language: Public contract field or enum value.
        filename: Public contract field or enum value.
        metadata: Public contract field or enum value.
        context_type: Public contract field or enum value.
        title: Public contract field or enum value.
        content_bytes: Public contract field or enum value.
        token_hint: Public contract field or enum value.
    """

    part_type: str
    content: str
    language: str = ''
    filename: str = ''
    metadata: dict = field(default_factory=dict)

    # 说明:Multipart context fields (I-08)
    context_type: str = ContextPartType.UNKNOWN
    title: str = ''
    content_bytes: int = 0
    token_hint: int = 0

    @property
    def is_text(self) -> bool:
        """is_text method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.part_type == ContentPartType.TEXT

    @property
    def is_markdown(self) -> bool:
        """is_markdown method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.part_type == ContentPartType.MARKDOWN

    @property
    def is_json(self) -> bool:
        """is_json method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.part_type == ContentPartType.JSON

    @property
    def is_image(self) -> bool:
        """is_image method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.part_type == ContentPartType.IMAGE

    @property
    def is_code(self) -> bool:
        """is_code method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.part_type == ContentPartType.CODE

    @property
    def is_html(self) -> bool:
        """is_html method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.part_type == ContentPartType.HTML

    # 说明:─── Context type convenience properties ────────────────────────────

    @property
    def is_system_prompt(self) -> bool:
        """is_system_prompt method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.context_type == ContextPartType.SYSTEM_PROMPT

    @property
    def is_user_message(self) -> bool:
        """is_user_message method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.context_type == ContextPartType.USER_MESSAGE

    @property
    def is_tool_result(self) -> bool:
        """is_tool_result method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.context_type == ContextPartType.TOOL_RESULT

    @property
    def is_attachment(self) -> bool:
        """is_attachment method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return self.context_type == ContextPartType.ATTACHMENT

    # 说明:─── Auto-computed metadata ────────────────────────────────────────

    def compute_metadata(self) -> None:
        """compute_metadata method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.
        """
        if self.content_bytes == 0 and self.content:
            self.content_bytes = len(self.content.encode('utf-8'))
        if self.token_hint == 0 and self.content:
            # 说明:Heuristic: ~4 chars per token (English text average).
            # For JSON/code 该 ratio is closer to 3-3.5;,用于 prose ~4-5.
            self.token_hint = max(1, len(self.content) // 4)

    @staticmethod
    def compute_all(parts: list[ContentPart]) -> list[ContentPart]:
        """compute_all method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            parts: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        for part in parts:
            part.compute_metadata()
        return parts
