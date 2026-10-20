"""Miniaturas persistentes; os arquivos originais nunca são modificados."""
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


def cached_thumbnail(upload_folder, folder, filename):
    source = Path(upload_folder) / folder / filename
    stat = source.stat()
    cache = Path(upload_folder) / '.thumbnails' / folder
    # A versão permite mudar dimensões/qualidade sem reutilizar arquivos antigos.
    target = cache / f'{source.stem}-{stat.st_mtime_ns}-{stat.st_size}-v1.webp'
    if target.is_file():
        return target
    cache.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        # Reduz JPEGs grandes antes de decodificar a imagem inteira, quando possível.
        original.draft('RGB', (640, 640))
        image = ImageOps.exif_transpose(original)
        image.thumbnail((640, 640), Image.Resampling.LANCZOS)
        image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as output:
                temporary = output.name
                image.save(output, format='WEBP', quality=78, method=4)
            # Workers podem gerar a mesma miniatura simultaneamente. O navegador
            # recebe somente arquivos completos, inclusive nessa situação.
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return target
