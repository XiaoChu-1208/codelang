"""macOS on-device OCR via the Vision framework (VNRecognizeTextRequest).

This is the same text engine that powers macOS Live Text — fully on-device,
offline, fast, and excellent at mixed CJK + Latin. We use it to turn a
screenshot region into text so codelang can look words up in contexts where
the text can't be selected/copied (images, PDFs, video, locked-down fields).

Requires pyobjc-framework-Vision + pyobjc-framework-Quartz (macOS only).

Public surface:
    ocr_image_file(path) -> str          # OCR a PNG/JPEG on disk
    available() -> bool                   # are the Vision bindings importable?

The capture half (interactive crosshair → temp PNG) lives in capture_mac.py;
this module deliberately only does image → text so it's trivially testable
against a fixture PNG.
"""
from __future__ import annotations

import sys

try:
    import Quartz
    import Vision
    from Foundation import NSURL
    _HAVE_VISION = True
except ImportError as _e:  # pragma: no cover — exercised only where Vision is absent
    _HAVE_VISION = False
    _IMPORT_ERROR = _e


# Recognition languages, most-preferred first. zh-Hans/zh-Hant first so mixed
# Chinese UI text isn't mis-segmented, but English terms (codelang's bread and
# butter) still recognize cleanly since Vision is multilingual per-request.
DEFAULT_LANGUAGES = ["zh-Hans", "zh-Hant", "en-US"]


def available() -> bool:
    return _HAVE_VISION


def _cg_image_from_file(path: str):
    """Load an image file into a CGImage (what VNImageRequestHandler wants)."""
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        raise OCRError(f"cannot read image: {path}")
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cg is None:
        raise OCRError(f"cannot decode image: {path}")
    return cg


class OCRError(RuntimeError):
    pass


def ocr_image_file(path: str, languages: list[str] | None = None) -> str:
    """Run on-device OCR over an image file and return the recognized text.

    Lines are joined with '\\n' in top-to-bottom, reading order. Returns "" if
    Vision finds no text. Raises OCRError if Vision isn't available or the
    image can't be decoded.
    """
    if not _HAVE_VISION:
        raise OCRError(f"Vision framework not available: {_IMPORT_ERROR}")

    cg = _cg_image_from_file(path)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)

    lines: list[str] = []

    def _completion(request, error):
        if error is not None:
            return
        for obs in request.results() or []:
            # topCandidates_(1) → highest-confidence transcription for this line
            cand = obs.topCandidates_(1)
            if cand and len(cand):
                lines.append(str(cand[0].string()))

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(_completion)
    # Accurate (vs Fast) — quality matters far more than the ~50ms cost for a
    # small region, and accuracy is dramatically better on small/AA'd text.
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(languages or DEFAULT_LANGUAGES)
    request.setUsesLanguageCorrection_(True)

    ok = handler.performRequests_error_([request], None)
    # performRequests_error_ runs the completion handler synchronously before
    # it returns, so `lines` is fully populated here.
    if not ok:
        # Returns (False, error) tuple on some pyobjc versions; treat as empty.
        return ""
    return "\n".join(lines).strip()


if __name__ == "__main__":  # quick manual test: python -m desktop.ocr_mac <image>
    print("Vision available:", available())
    if len(sys.argv) > 1:
        print(repr(ocr_image_file(sys.argv[1])))
