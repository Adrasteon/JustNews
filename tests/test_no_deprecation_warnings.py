import importlib
import warnings


def test_no_protobuf_upb_deprecation():
    """Import commonly used modules and assert no PyType_Spec / tp_new deprecation warning occurs."""
    modules = [
        'google._upb._message',
        'google.protobuf',
        'transformers',
        'sentence_transformers',
        'chromadb',
    ]

    # Ensure imports don't raise the specific deprecation warning
    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter('always', DeprecationWarning)
        for m in modules:
            try:
                importlib.import_module(m)
            except Exception:
                # If module is not available, ignore it for this import check.
                continue
        # Check for 'PyType_Spec' substring in deprecation warnings
        for w in warned:
            if 'PyType_Spec' in str(w.message) or 'tp_new' in str(w.message):
                raise AssertionError(f'DeprecationWarning detected: {w.message}')
