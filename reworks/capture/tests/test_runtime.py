import base64

import pytest

from capture.workflow.service import CaptureRuntime


def _runtime_for_decode(max_bytes: int = 20) -> CaptureRuntime:
    runtime = object.__new__(CaptureRuntime)
    runtime.capture_settings = {"max_pdf_bytes": max_bytes}
    return runtime


def test_decode_pdf_base64() -> None:
    runtime = _runtime_for_decode()
    data = b"%PDF-test"
    assert runtime.decode_pdf_base64(base64.b64encode(data).decode()) == data


def test_decode_pdf_data_uri() -> None:
    runtime = _runtime_for_decode()
    data = b"%PDF-test"
    encoded = base64.b64encode(data).decode()
    assert runtime.decode_pdf_base64(f"data:application/pdf;base64,{encoded}") == data


def test_decode_rejects_oversized_input_before_decode() -> None:
    runtime = _runtime_for_decode(max_bytes=3)
    with pytest.raises(ValueError, match="max size"):
        runtime.decode_pdf_base64(base64.b64encode(b"123456789").decode())
