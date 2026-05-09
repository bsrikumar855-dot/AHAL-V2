from app.intelligence.canonical_presenter import CanonicalProjectPresenter
from app.intelligence.intelligence_engine import IntelligenceEngine
from app.intelligence.product_identity import ProductIdentityResolver
from tests.intelligence.conftest import make_scan_result


NOISY_README = """# Create And Activate Virtual Environment

<p align="center">
  <img src="public/branding/ahal-logo-chatgpt-transparent.png" alt="AHAL AI Logo" width="280" />
</p>
"""


def noisy_fullstack_scan():
    return make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "package.json", "extension": ".json"},
            {"path": "app/main.py", "extension": ".py"},
            {"path": "frontend/src/main.tsx", "extension": ".tsx"},
            {"path": "public/branding/ahal-logo-chatgpt-transparent.png", "extension": ".png"},
        ],
        contents={
            "README.md": NOISY_README,
            "package.json": '{"name":"create-and-activate-virtual-environment","description":"<p align=\\"center\\">"}',
            "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health(): pass\n",
            "frontend/src/main.tsx": "import React from 'react'\nexport function App() { return null }\n",
            "public/branding/ahal-logo-chatgpt-transparent.png": b"",
        },
    )


def test_product_identity_rejects_image_markup_candidate():
    scan = noisy_fullstack_scan()
    identity = ProductIdentityResolver().resolve(scan_result=scan, intelligence_result=IntelligenceEngine().analyze(scan))

    assert identity.project_name is None
    assert "<p" not in identity.purpose_summary.lower()
    assert "logo-chatgpt-transparent" not in identity.purpose_summary.lower()


def test_canonical_summary_never_contains_html():
    scan = noisy_fullstack_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    canonical = CanonicalProjectPresenter().build("noise-session", scan, intelligence)
    combined = " ".join([canonical.product_summary, canonical.what, canonical.why]).lower()

    for token in ("<", ">", "img", "src=", "alt=", "width=", ".png"):
        assert token not in combined
    assert canonical.project_name == "Analyzed Project"
    assert "Create And Activate Virtual Environment" not in canonical.product_summary
    assert "Create And Activate Virtual Environment" not in canonical.what
    assert "Create And Activate Virtual Environment" not in canonical.why
