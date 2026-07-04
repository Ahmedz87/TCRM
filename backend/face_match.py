"""
face_match.py — local biometric face matching (InsightFace / ArcFace, CPU only).

Runs ENTIRELY on this server — no image ever leaves the box. Compares the photo on a
KYC ID document against the client's selfie and returns a similarity score + verdict.

The model (buffalo_l, ~300MB) is downloaded once on first use and cached. Embeddings are
512-dim L2-normalised, so the cosine similarity is just their dot product.
"""
import os
import threading

# tunable thresholds (cosine similarity of two normalised ArcFace embeddings)
MATCH_AT = 0.45     # >= this  -> same person (match)
REVIEW_AT = 0.30    # in [REVIEW_AT, MATCH_AT) -> manual review; below -> mismatch

_app = None
_lock = threading.Lock()


def _engine():
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                from insightface.app import FaceAnalysis
                a = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                a.prepare(ctx_id=-1, det_size=(640, 640))
                _app = a
    return _app


def _largest_embedding(path):
    """Return the L2-normalised embedding of the largest face in the image, or None."""
    import cv2
    if not path or not os.path.exists(path):
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    faces = _engine().get(img)
    if not faces:
        return None
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    return f.normed_embedding


def compare(id_path, selfie_path):
    """
    Compare the face on the ID against the selfie.
    Returns {ok, score, verdict, id_face, selfie_face, reason}.
      verdict: match | review | mismatch | no_face
    """
    import numpy as np
    try:
        e_id = _largest_embedding(id_path)
        e_self = _largest_embedding(selfie_path)
    except Exception as e:
        return {"ok": False, "score": None, "verdict": "error", "reason": str(e)[:200],
                "id_face": False, "selfie_face": False}

    if e_id is None or e_self is None:
        return {"ok": False, "score": None, "verdict": "no_face",
                "id_face": e_id is not None, "selfie_face": e_self is not None,
                "reason": "no face on ID" if e_id is None else "no face in selfie"}

    score = float(np.dot(e_id, e_self))   # both normalised -> cosine similarity
    verdict = "match" if score >= MATCH_AT else ("review" if score >= REVIEW_AT else "mismatch")
    return {"ok": True, "score": round(score, 4), "verdict": verdict,
            "id_face": True, "selfie_face": True, "reason": ""}
