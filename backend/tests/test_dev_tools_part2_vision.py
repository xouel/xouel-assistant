import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from PIL import Image

from app.config import CAPTURES_DIR
from app.schemas import AnalysisResult
from app.services.dev_tools import (
    capture_visual_context,
    analyze_screen,
)


@pytest.fixture
def sample_image(tmp_path: Path):
    """Cria uma imagem de teste no disco."""
    img_path = tmp_path / "print_explorer.png"
    img = Image.new("RGB", (100, 100), color="red")
    img.save(img_path)
    return img_path


def test_capture_clipboard_crop():
    # Simula o usuário recortando um pedaço da tela com Win + Shift + S
    dummy_crop = Image.new("RGB", (300, 150), color="green")
    with patch("PIL.ImageGrab.grabclipboard", return_value=dummy_crop):
        path, source = capture_visual_context(source_preference="auto")
        assert source == "clipboard_crop"
        assert path.exists()
        assert path.name == "latest_capture.png"


def test_capture_clipboard_file_from_explorer(sample_image):
    # Simula o usuário copiando um arquivo de imagem no Windows Explorer (Ctrl+C)
    with patch("PIL.ImageGrab.grabclipboard", return_value=[str(sample_image)]):
        path, source = capture_visual_context(source_preference="auto")
        assert source == "clipboard_file"
        assert path.exists()


def test_capture_fallback_fullscreen():
    # Simula clipboard sem imagem -> fallback automático para o monitor principal
    dummy_screen = Image.new("RGB", (1920, 1080), color="blue")
    with patch("PIL.ImageGrab.grabclipboard", return_value=None):
        with patch("PIL.ImageGrab.grab", return_value=dummy_screen):
            path, source = capture_visual_context(source_preference="auto", hide_window=False)
            assert source == "fullscreen"
            assert path.exists()


def test_capture_strict_clipboard_failure():
    # Usuário pediu apenas clipboard, mas não há imagem copiada
    with patch("PIL.ImageGrab.grabclipboard", return_value=None):
        with pytest.raises(ValueError) as exc:
            capture_visual_context(source_preference="clipboard")
        assert "Nenhuma imagem" in str(exc.value)


@pytest.mark.anyio
async def test_analyze_screen_flow():
    dummy_crop = Image.new("RGB", (100, 100), color="white")
    with patch("PIL.ImageGrab.grabclipboard", return_value=dummy_crop):
        with patch("app.services.dev_tools.analyze_image", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = "Interface limpa com botão azul centralizado. Sem erros visíveis."
            
            res = await analyze_screen(prompt="O que vê?")
            assert isinstance(res, AnalysisResult)
            assert res.status == "success"
            assert "Interface limpa" in res.analysis
            assert res.details["capture_source"] == "clipboard_crop"

