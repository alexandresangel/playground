"""PDF text, model request, XML normalization, and extraction failures."""

import io
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from pypdf.errors import PdfReadError

from capture.workflow import extract_xml, prompts


def text_pdf(*pages):
    """Build a small real PDF with deterministic text or blank pages."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in pages:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_text_preserves_page_order_and_skips_empty_content():
    assert (
        extract_xml.pdf_to_text(text_pdf("First page", "", "Last page"))
        == "First page\n\nLast page"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pdf,error,message",
    [
        pytest.param(text_pdf(""), ValueError, "Could not extract text", id="textless-pdf"),
        pytest.param(b"%PDF-1.7\ncorrupt", PdfReadError, None, id="corrupt-pdf"),
    ],
)
async def test_unreadable_pdf_never_calls_model_or_resolver(workflow, pdf, error, message):
    with pytest.raises(error, match=message):
        await workflow.run(pdf_bytes=pdf)
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,error,message",
    [
        ("", RuntimeError, "Empty LLM response"),
        (None, RuntimeError, "Empty LLM response"),
        ("not XML", ValueError, "did not contain XML"),
        ("<broken", ValueError, "Invalid trade XML"),
    ],
)
async def test_bad_model_output_never_resolves(workflow, content, error, message):
    workflow.completion.return_value.choices[0].message.content = content
    with pytest.raises(error, match=message):
        await workflow.run()
    workflow.resolver.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "choices", [[], [SimpleNamespace(message=None)]], ids=["no-choices", "no-message"]
)
async def test_missing_completion_message_never_resolves(workflow, choices):
    workflow.completion.return_value.choices = choices
    with pytest.raises(RuntimeError, match="Empty LLM response"):
        await workflow.run()
    workflow.resolver.assert_not_called()


@pytest.mark.asyncio
async def test_model_exception_propagates_without_resolving(workflow):
    workflow.completion.side_effect = RuntimeError("model unavailable")
    with pytest.raises(RuntimeError, match="model unavailable"):
        await workflow.run()
    workflow.completion.assert_called_once()
    workflow.resolver.assert_not_called()


@pytest.mark.asyncio
async def test_missing_prompt_stops_before_model(workflow, monkeypatch):
    monkeypatch.setattr(prompts, "_catalog", {"default_prompt": "missing.txt"})
    with pytest.raises(RuntimeError, match="Cannot read Capture config file"):
        await workflow.run()
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


def test_document_sent_in_full_while_debug_preview_is_bounded(workflow):
    document = "A" * 2200
    detail = extract_xml.extract_trade_xml_detail(
        text_pdf(document), "iamLoan", workflow.config, workflow.azure
    )
    assert detail["pdf_text_length"] == len(document)
    assert detail["pdf_text_preview"] == document[:2000]
    assert workflow.completion.call_args.kwargs["messages"][1]["content"].endswith(document)
    assert detail["trade_xml_raw"] != detail["trade_xml"]
    assert detail["deployment"] == "same-model"
    assert detail["temperature"] == 0.5


@pytest.mark.parametrize(
    "content",
    [
        "<trade/>",
        "  <trade/>\n",
        "```xml\n<trade/>\n```",
        "```XML\n<trade/>\n```",
        "```\n<trade/>\n```",
        "Here is the XML:\n<trade/>",
    ],
)
def test_xml_response_wrappers_are_removed(content):
    assert extract_xml.extract_xml_from_llm(content) == "<trade/>"
