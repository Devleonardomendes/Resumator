from pathlib import Path
import json
import sys
import tempfile
import wave

from resumator.pdf_export import export_response_docx, export_response_json, export_response_pdf
from resumator import pdf_export as pdf_export_module
from resumator.prompt_store import PromptStore
from resumator.ui import _resource_path, main


def self_test() -> int:
    output_dir = Path(tempfile.gettempdir()) / "resumator-11.4-self-test"
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_path = output_dir / "diagnostic.txt"
    ok_path = output_dir / "ok.txt"
    ok_path.unlink(missing_ok=True)

    def mark(stage: str) -> None:
        diagnostic_path.write_text(stage, encoding="utf-8")

    selected_prompt = None

    mark("exporting-pdf")
    export_response_pdf(
        output_dir / "self-test.pdf",
        "Teste automatizado do Resumator 11.4.",
        prompt_name=selected_prompt.name if selected_prompt else None,
    )
    mark("exporting-formatted-pdf")
    if not pdf_export_module._can_export_formatted_pdf():
        raise RuntimeError("ReportLab indisponível: exportação PDF formatada não está empacotada.")
    export_response_pdf(
        output_dir / "self-test-formatted.pdf",
        "Titulo\nTexto em negrito, italico e sublinhado.",
        prompt_name=selected_prompt.name if selected_prompt else None,
        formatted_html=(
            "<h1>Titulo</h1>"
            "<p>Texto em <strong>negrito</strong>, <em>italico</em> e <u>sublinhado</u>.</p>"
            "<ul><li>Item em lista</li></ul>"
        ),
    )
    mark("exporting-docx")
    export_response_docx(
        output_dir / "self-test.docx",
        "Teste automatizado do Resumator 11.4.",
        prompt_name=selected_prompt.name if selected_prompt else None,
    )
    mark("exporting-docx-fallback")
    original_docx = (pdf_export_module.Document, pdf_export_module.Inches, pdf_export_module.Pt)
    try:
        pdf_export_module.Document = None
        pdf_export_module.Inches = None
        pdf_export_module.Pt = None
        export_response_docx(
            output_dir / "self-test-fallback.docx",
            "Teste automatizado do fallback DOCX do Resumator 11.4.",
            prompt_name=selected_prompt.name if selected_prompt else None,
        )
    finally:
        pdf_export_module.Document, pdf_export_module.Inches, pdf_export_module.Pt = original_docx
    mark("exporting-json")
    export_response_json(
        output_dir / "self-test.json",
        "Teste automatizado do Resumator 11.4.",
        prompt_name=selected_prompt.name if selected_prompt else None,
    )
    mark("checking-export-confirmation")
    animation_path = _resource_path("assets", "export-success.webp")
    sound_path = _resource_path("assets", "export-success.wav")
    if not animation_path.is_file() or not sound_path.is_file():
        raise RuntimeError("Arquivos da confirmação animada não foram encontrados.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow indisponivel para validar a confirmacao animada.") from exc
    with Image.open(animation_path) as animation:
        if animation.size != (640, 360) or getattr(animation, "n_frames", 1) != 36:
            raise RuntimeError("Animação de confirmação inválida.")
    with wave.open(str(sound_path), "rb") as sound:
        duration_seconds = sound.getnframes() / sound.getframerate()
        if sound.getnchannels() != 2 or sound.getframerate() != 44100:
            raise RuntimeError("Áudio da confirmação usa um formato inesperado.")
        if not 2.95 <= duration_seconds <= 3.05:
            raise RuntimeError("Áudio da confirmação não tem duração de 3 segundos.")
    mark("checking-prompts")
    test_prompts_path = output_dir / "prompts.json"
    test_prompts_path.unlink(missing_ok=True)
    store = PromptStore(test_prompts_path)
    bom_prompts_path = output_dir / "prompts-with-bom.json"
    bom_prompts_path.write_text(
        json.dumps(
            {
                "version": 3,
                "prompts": [
                    {
                        "id": "self-test-bom-import",
                        "name": "Prompt com BOM",
                        "content": "Conteudo de teste para importacao com BOM.",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    imported, _ = store.import_from_file(bom_prompts_path)
    if imported != 1:
        raise RuntimeError("Falha no teste de importacao de prompts com BOM.")
    ok_path.write_text("ok", encoding="utf-8")
    mark("ok")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    main()

