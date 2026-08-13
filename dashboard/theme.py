"""NHS Digital Service Manual styling — colours, header banner, CSS.

Matches the palette and header pattern used across this portfolio's other
NHS-branded Streamlit tools (the AIF Allocation Tool's blue theme and NHS
logo banner; the HeartLink dashboard's three-tier `england.nhs.uk` header
and metric-card treatment): https://service-manual.nhs.uk/design-system/styles/colour
"""

from __future__ import annotations

import streamlit as st

BLUE = "#005eb8"
DARK_BLUE = "#003087"
BLACK = "#0b0c0c"
TEXT = "#212b32"
GREY_MID = "#4c6272"
GREY_LIGHT = "#f0f4f5"
GREEN = "#007f3b"
RED = "#d5281b"
WHITE = "#ffffff"

# NHS logo mark, reproduced as inline SVG (same source used by the AIF
# Allocation Tool) so the header renders with no external image request.
_NHS_LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 16" height="28">
    <path d="M0 0h40v16H0z" fill="#005EB8"></path>
    <path d="M3.9 1.5h4.4l2.6 9h.1l1.8-9h3.3l-2.8 13H9l-2.7-9h-.1l-1.8 9H1.1
             M17.3 1.5h3.6l-1 4.9h4L25 1.5h3.5l-2.7 13h-3.5l1.1-5.6h-4.1l-1.2 5.6h-3.4
             M37.7 4.4c-.7-.3-1.6-.6-2.9-.6-1.4 0-2.5.2-2.5 1.3 0 1.8 5.1 1.2 5.1 5.1
             0 3.6-3.3 4.5-6.4 4.5-1.3 0-2.9-.3-4-.7l.8-2.7c.7.4 2.1.7 3.2.7s2.8-.2
             2.8-1.5c0-2.1-5.1-1.3-5.1-5 0-3.4 2.9-4.4 5.8-4.4 1.6 0 3.1.2 4 .6"
          fill="white"></path>
</svg>
"""

_CSS = f"""
<style>
.block-container {{
    padding-top: 1rem;
}}
.nhs-topbar {{
    background: {BLACK};
    color: {WHITE};
    font-size: 0.8rem;
    padding: 0.35rem 0.9rem;
    margin: -1rem -1rem 0 -1rem;
}}
.nhs-header {{
    background: {BLUE};
    color: {WHITE};
    padding: 0.9rem 1rem;
    margin: 0 -1rem 1rem -1rem;
    display: flex;
    align-items: center;
    gap: 0.9rem;
}}
.nhs-header__service {{
    font-size: 1.25rem;
    font-weight: 700;
    line-height: 1.2;
}}
.nhs-header__tagline {{
    font-size: 0.85rem;
    opacity: 0.9;
}}
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-left: 4px solid {BLUE} !important;
    border-radius: 4px;
}}
div[data-testid="stMetric"] {{
    background: {GREY_LIGHT};
    border-radius: 4px;
    padding: 0.6rem 0.8rem;
}}
div[data-testid="stMetricValue"] {{
    color: {BLUE};
}}
.nhs-badge-growth {{ color: {GREEN}; font-weight: 700; }}
.nhs-badge-decline {{ color: {RED}; font-weight: 700; }}
.nhs-badge-stable {{ color: {DARK_BLUE}; font-weight: 700; }}
</style>
"""


def inject_style() -> None:
    """Apply the NHS colour theme and layout tweaks to the current page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header(service_name: str, tagline: str) -> None:
    """NHS-style top bar + blue service header, matching the sibling apps."""
    st.markdown(
        '<div class="nhs-topbar">NHS England &middot; Open Data</div>'
        f'<div class="nhs-header">{_NHS_LOGO_SVG}'
        f'<div><div class="nhs-header__service">{service_name}</div>'
        f'<div class="nhs-header__tagline">{tagline}</div></div></div>',
        unsafe_allow_html=True,
    )
