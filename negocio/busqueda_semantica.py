"""Embeddings multilingües ONNX locales, sin APIs ni descargas en una consulta.

El modelo se provisiona explícitamente con preparar_busqueda. Si no está,
la recuperación conserva el camino por conceptos y palabras, sin inventar.
"""
from functools import lru_cache
import logging
import threading
from django.conf import settings

MODELO = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
logger = logging.getLogger(__name__)
_lock = threading.Lock()


@lru_cache(maxsize=1)
def modelo_local():
    if not settings.BUSQUEDA_SEMANTICA:
        return None
    try:
        import os
        os.environ.setdefault('HF_HOME', str(settings.MODELO_BUSQUEDA_DIR / 'hub'))
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=MODELO, cache_dir=str(settings.MODELO_BUSQUEDA_DIR),
                             local_files_only=True, threads=2)
    except Exception:
        logger.warning('Modelo semántico local no disponible; se usa búsqueda por conceptos.')
        return None


@lru_cache(maxsize=512)
def vector(texto):
    modelo = modelo_local()
    if modelo is None:
        return None
    # Límite al cache y una sola inferencia simultánea por proceso.
    with _lock:
        return next(modelo.embed([texto[:1800]]))


def similitud(consulta, texto):
    a, b = vector(consulta), vector(texto)
    if a is None or b is None:
        return None
    import numpy as np
    denominador = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominador) if denominador else 0.0
