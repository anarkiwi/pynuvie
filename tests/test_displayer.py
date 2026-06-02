"""The displayer generator must byte-exactly reproduce NUVIEmaker's own generated
displayer (captured by driving the real tool via vice-driver) for independent
inputs -- proving the $33b0 generator port is correct and content-independent."""

import os

from nuvie._displayer import generate, DISPLAYER_LEN

REF = os.path.join(os.path.dirname(__file__), "..", "research", "nuviemaker_flibug")


def _nuf_body(name):
    return open(os.path.join(REF, name), "rb").read()[2:]


def _expect(name):
    return open(os.path.join(REF, name), "rb").read()[:DISPLAYER_LEN]


def test_generate_matches_real_nuviemaker_lv():
    if not os.path.exists(os.path.join(REF, "lv.nuf")):
        import pytest

        pytest.skip("reference captures not present")
    assert generate(_nuf_body("lv.nuf")) == _expect("lv_displayer.bin")


def test_generate_matches_real_nuviemaker_stripes():
    if not os.path.exists(os.path.join(REF, "stripes.nuf")):
        import pytest

        pytest.skip("reference captures not present")
    # same template, different input -> proves content-independence of the structure
    assert generate(_nuf_body("stripes.nuf")) == _expect("stripes_displayer.bin")
