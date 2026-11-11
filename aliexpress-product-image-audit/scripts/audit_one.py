# -*- coding: utf-8 -*-
"""Read-only, single-product pre-audit.

Usage:
    .venv\\Scripts\\python.exe -X utf8 audit_one.py <pid> [--shop 7] [--no-ocr] [--force]

The only remote mutation is selecting the current shop.  This script never calls
product save/status/upload/translate/blacklist endpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
CJK_RE = re.compile(r"[\u3400-\u9fff]")
URL_RE = re.compile(r"https?://[^\s\"'<>\\]+")
STORE_WORDS = ("store", "shop", "toys", "toy store", "模玩", "玩具店", "商城", "店铺")
HASBRO = "200017853"
BANDAI = "200014695"
DUPLICATE_DISTANCE = 8
WORKFLOW_VERSION = "token-opt-v1"
EVIDENCE_SCHEMA = "image-evidence/v1"
METRICS_SCHEMA = "token-opt-metrics/v1"
OCR_EXTRACTOR_FINGERPRINT = "rapidocr-onnxruntime:default|full+top28x2+bottom28x2|score>=0.50|v1"
EVIDENCE_CACHE = ROOT / ".cache" / "audit_evidence" / "v1"


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _image_urls(product: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every main/detail/sku occurrence; include skuImageUrl fallbacks."""
    out: list[dict[str, Any]] = []
    images = product.get("images") or {}
    for kind in ("main", "detail", "sku"):
        for idx, value in enumerate(images.get(kind) or []):
            url = value.get("url") if isinstance(value, dict) else value
            if url:
                out.append({"kind": kind, "index": idx, "url": str(url), "source": "images"})

    known_sku = {x["url"] for x in out if x["kind"] == "sku"}
    for idx, sku in enumerate(product.get("skus") or []):
        if not isinstance(sku, dict):
            continue
        url = sku.get("skuImageUrl") or sku.get("imageUrl") or sku.get("image")
        if url and str(url) not in known_sku:
            out.append({"kind": "sku", "index": idx, "url": str(url), "source": "skus"})
            known_sku.add(str(url))
    return out


def _decode(path: Path) -> np.ndarray | None:
    """Decode by content, so WEBP bytes behind .jpg extensions work."""
    try:
        return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    except (OSError, ValueError, cv2.error):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, TypeError, ValueError):
        return None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _phash(gray: np.ndarray) -> str:
    img = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(img)[:8, :8]
    median = np.median(dct[1:, 1:])
    bits = (dct > median).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
    return f"{value:016x}"


def _ham(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _edge_band(gray: np.ndarray, side: str) -> dict[str, Any] | None:
    """Find a contiguous near-uniform white/black band touching one edge."""
    h, w = gray.shape
    axis_len = h if side in ("top", "bottom") else w
    limit = max(1, min(axis_len // 4, int(round(axis_len * 0.20))))
    white = gray >= 248
    black = gray <= 7
    if side == "top":
        slices = ((white[y, :], black[y, :]) for y in range(limit))
    elif side == "bottom":
        slices = ((white[h - 1 - y, :], black[h - 1 - y, :]) for y in range(limit))
    elif side == "left":
        slices = ((white[:, x], black[:, x]) for x in range(limit))
    else:
        slices = ((white[:, w - 1 - x], black[:, w - 1 - x]) for x in range(limit))

    colour = None
    thickness = 0
    scores: list[float] = []
    for white_line, black_line in slices:
        wf, bf = float(white_line.mean()), float(black_line.mean())
        current, score = ("white", wf) if wf >= bf else ("black", bf)
        if score < 0.985 or (colour is not None and current != colour):
            break
        colour = current
        thickness += 1
        scores.append(score)
    # Imported listings can carry very thin 7–9 px bands even on 800 px images.
    # Cap the threshold at 6 px; border_candidates() separately suppresses
    # three/four-edge same-colour product canvases.
    min_px = max(3, min(6, int(round(axis_len * 0.012))))
    fraction = thickness / axis_len
    # A frame is a thin strip. A large uniform area is usually the product's
    # white/black canvas, not an imported-store border.
    if thickness < min_px or fraction > 0.06 or thickness >= limit:
        return None
    return {
        "side": side,
        "color": colour,
        "pixels": thickness,
        "fraction": round(thickness / axis_len, 4),
        "uniformity": round(float(np.mean(scores)), 4),
    }


def border_candidates(gray: np.ndarray) -> list[dict[str, Any]]:
    hits = [hit for side in ("top", "bottom", "left", "right")
            if (hit := _edge_band(gray, side)) is not None]
    # Three or four same-colour edge bands usually mean a deliberate white/black
    # product canvas. Imported-store frames in the known cases are thin bands on
    # one or two edges; suppress the canvas pattern to keep flags compact.
    if len(hits) >= 3 and len({hit["color"] for hit in hits}) == 1:
        return []
    return hits


def residual_stats(gray: np.ndarray) -> dict[str, Any]:
    """Small medianBlur(61) residual summary; never serializes pixel arrays."""
    h, w = gray.shape
    scale = min(1.0, 800.0 / max(h, w))
    if scale < 1.0:
        gray = cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))),
                          interpolation=cv2.INTER_AREA)
    residual = gray.astype(np.int16) - cv2.medianBlur(gray, 61).astype(np.int16)
    absolute = np.abs(residual)
    p01, p99 = np.percentile(residual, [1, 99])
    abs_p95, abs_p99 = np.percentile(absolute, [95, 99])
    strong_fraction = float((absolute >= 12).mean())
    # Deliberately broad triage flag: it asks for human residual review, not a watermark verdict.
    candidate = bool(abs_p99 >= 18 and 0.006 <= strong_fraction <= 0.12 and absolute.mean() <= 10.0)
    return {
        "sample": [int(gray.shape[1]), int(gray.shape[0])],
        "mean_abs": round(float(absolute.mean()), 2),
        "p01": round(float(p01), 1),
        "p99": round(float(p99), 1),
        "abs_p95": round(float(abs_p95), 1),
        "abs_p99": round(float(abs_p99), 1),
        "strong_fraction": round(strong_fraction, 4),
        "candidate": candidate,
    }


def _ocr_items(engine: Any, image: np.ndarray, region: str, x0: int = 0, y0: int = 0,
               inverse_scale: float = 1.0) -> list[dict[str, Any]]:
    result, _ = engine(image)
    items: list[dict[str, Any]] = []
    for box, text, score in (result or []):
        if float(score) < 0.50:
            continue
        xs = [float(point[0]) * inverse_scale + x0 for point in box]
        ys = [float(point[1]) * inverse_scale + y0 for point in box]
        items.append({
            "text": str(text),
            "score": round(float(score), 3),
            "rect": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
            "region": region,
        })
    return items


def _classify_ocr(items: list[dict[str, Any]], title_text: str = "") -> tuple[str, list[dict[str, Any]]]:
    try:
        from watermark_ocr import classify, norm
        tagged = classify(items)
        title_norm = norm(title_text)
        norm_text = norm
        classifier = "watermark_ocr.classify"
    except Exception as exc:  # keeps --no-ocr and degraded environments usable
        tagged = []
        title_norm = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title_text.lower())
        norm_text = lambda value: re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())
        for item in items:
            low = item["text"].lower()
            reason = "店铺名" if any(word in low for word in STORE_WORDS) else "其他"
            tagged.append((item, reason != "其他", reason))
        classifier = f"fallback:{type(exc).__name__}"

    hits: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item, flagged, reason in tagged:
        text = item["text"].strip()
        text_norm = norm_text(text)
        cjk = bool(CJK_RE.search(text))
        store_hint = any(word in text.lower() for word in STORE_WORDS)
        explicit_store = bool(re.search(r"\b(?:store|shop)\b|玩具店|店铺|商城", text, re.I))
        # Brand/model text already present in the title is normally official packaging,
        # unless it explicitly identifies a store or shop.
        if text_norm and len(text_norm) >= 4 and text_norm in title_norm and not explicit_store:
            continue
        # Single CJK glyphs are overwhelmingly texture/part-shape OCR noise. A real
        # store mark still survives when classify() flags it or it contains a store hint.
        if cjk and len(text_norm) < 2 and not flagged and not store_hint:
            continue
        if not (flagged or cjk or store_hint):
            continue
        reasons = []
        if flagged:
            reasons.append(str(reason))
        if cjk:
            reasons.append("CJK")
        if store_hint and "店铺名" not in reasons:
            reasons.append("store_hint")
        key = (text.lower(), tuple(item["rect"]), item["region"], tuple(reasons))
        if key in seen:
            continue
        seen.add(key)
        hits.append({"text": text, "reasons": reasons, "score": item["score"],
                     "rect": item["rect"], "region": item["region"]})
    return classifier, hits


def _classify_ocr_passes(passes: list[list[dict[str, Any]]], title_text: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Classify cached/raw OCR by pass so repeated strip reads do not look tiled."""
    all_items: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    classifiers: set[str] = set()
    for items in passes:
        classifier, pass_hits = _classify_ocr(items, title_text=title_text)
        classifiers.add(classifier)
        all_items.extend(items)
        hits.extend(pass_hits)

    deduped: list[dict[str, Any]] = []
    for hit in hits:
        box = hit["rect"]
        merged = False
        for previous in deduped:
            if previous["text"].casefold() != hit["text"].casefold():
                continue
            old = previous["rect"]
            ix0, iy0, ix1, iy1 = max(box[0], old[0]), max(box[1], old[1]), min(box[2], old[2]), min(box[3], old[3])
            intersection = max(0, ix1 - ix0) * max(0, iy1 - iy0)
            area_a = max(1, (box[2] - box[0]) * (box[3] - box[1]))
            area_b = max(1, (old[2] - old[0]) * (old[3] - old[1]))
            if intersection / float(area_a + area_b - intersection) < 0.45:
                continue
            previous["reasons"] = sorted(set(previous["reasons"] + hit["reasons"]))
            previous.setdefault("also_seen_in", []).append(hit["region"])
            previous["score"] = max(previous["score"], hit["score"])
            merged = True
            break
        if not merged:
            deduped.append(hit)
    return all_items, deduped, ",".join(sorted(classifiers))


def run_ocr(engine: Any, image: np.ndarray, title_text: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    h, w = image.shape[:2]
    crop_h = max(1, int(round(h * 0.28)))
    top = cv2.resize(image[:crop_h], None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    bottom = cv2.resize(image[h - crop_h:], None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    passes = [
        _ocr_items(engine, image, "full"),
        _ocr_items(engine, top, "top28_x2", inverse_scale=0.5),
        _ocr_items(engine, bottom, "bottom28_x2", y0=h - crop_h, inverse_scale=0.5),
    ]
    return _classify_ocr_passes(passes, title_text=title_text)


def classify_cached_ocr(items: list[dict[str, Any]], title_text: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Reclassify title-dependent flags without rerunning title-independent OCR."""
    regions = ("full", "top28_x2", "bottom28_x2")
    passes = [[item for item in items if item.get("region") == region] for region in regions]
    return _classify_ocr_passes(passes, title_text=title_text)


def title_checks(product: dict[str, Any], shop: int) -> dict[str, Any]:
    title = str(product.get("titleEn") or "")
    expected_prefix = "Hot Sale" if shop == 7 else "In Stock" if shop == 4 else None
    identity = _json_obj(product.get("identityJson"))
    model = str(identity.get("modelCode") or "").strip()
    compact_model = re.sub(r"[\s\-_]+", "", model)
    def has_token(token: str) -> bool:
        return bool(token and re.search(r"(?<![A-Za-z0-9])" + re.escape(token) +
                                        r"(?![A-Za-z0-9])", title, re.I))
    model_present = has_token(model)
    compact_present = has_token(compact_model)
    dual_required = bool(model and compact_model.lower() != model.lower())
    dual_ok = bool(model and model_present and (compact_present if dual_required else True))
    transform_text = "%s %s" % (title, product.get("title") or "")
    transform = bool(re.search(r"\btransformation\b|\btransformers?\b|\btransforming\s+toy|变形", transform_text, re.I))
    expected_brand = HASBRO if transform else BANDAI
    actual_brand = str(product.get("brand") or product.get("brandId") or "")
    anomalies: list[str] = []
    if expected_prefix and not title.startswith(expected_prefix + " "):
        anomalies.append("title_prefix")
    if len(title) > 120:
        anomalies.append("title_length")
    if not model:
        anomalies.append("modelCode_missing")
    elif not dual_ok:
        anomalies.append("modelCode_title_inclusion")
    translation_present = bool(str(product.get("titleTranslationZh") or "").strip())
    if actual_brand != expected_brand:
        anomalies.append("brand_rule")
    if not translation_present:
        anomalies.append("titleTranslationZh_missing")
    return {
        "title": title,
        "length": len(title),
        "expected_prefix": expected_prefix,
        "prefix_ok": expected_prefix is None or title.startswith(expected_prefix + " "),
        "modelCode": model or None,
        "model_in_title": model_present,
        "compact_model_in_title": compact_present,
        "dual_format_ok": dual_ok if model else None,
        "brand": actual_brand or None,
        "expected_brand": expected_brand,
        "brand_rule_basis": "title indicates transforming/Transformers" if transform else "other",
        "brand_ok": actual_brand == expected_brand,
        "titleTranslationZh_present": translation_present,
        "anomalies": anomalies,
    }


def description_checks(product: dict[str, Any], live_image_urls: Iterable[str]) -> dict[str, Any]:
    raw = product.get("descriptionJson")
    parse_error = None
    parsed: Any = None
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            parse_error = f"{type(exc).__name__}: {str(exc)[:100]}"
    elif raw is not None:
        parsed = raw
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False) if raw is not None else ""
    urls = sorted(set(URL_RE.findall(text)))
    image_ext = re.compile(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", re.I)
    image_refs = [url for url in urls if image_ext.search(url)]
    live_names = {url.split("?", 1)[0].rsplit("/", 1)[-1] for url in live_image_urls}
    unmatched = [url for url in image_refs
                 if url.split("?", 1)[0].rsplit("/", 1)[-1] not in live_names]
    # These are candidates only: common footer/template images are intentionally external.
    return {
        "present": raw not in (None, "", []),
        "parse_error": parse_error,
        "url_count": len(urls),
        "image_url_count": len(image_refs),
        "external_or_unmapped_image_refs": unmatched,
        "dead_reference_note": "unmatched refs need manual/HTTP validation; shared footer images may be valid" if unmatched else None,
        "parsed_type": type(parsed).__name__ if parsed is not None else None,
    }


def _head_status(url: str) -> int | str:
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return int(response.status)
    except Exception as exc:
        return getattr(exc, "code", f"ERR:{type(exc).__name__}")


def _definitely_dead(status: int | str) -> bool:
    """Only promote conclusive missing responses; auth/rate/network errors need review."""
    return isinstance(status, int) and status in (404, 410)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def audit(pid: int, shop: int, no_ocr: bool = False, force: bool = False) -> dict[str, Any]:
    # Deliberately lazy: importing this module for tests does not log in to the site.
    from site_client import Site

    audit_started = time.perf_counter()
    site = Site()
    site.call("/api/admin/shops/current", {"shopId": shop}, method="PUT")
    product = site.product(pid)

    outdir = ROOT / "work" / f"pp_{pid}"
    imgdir = outdir / "audit_images"
    imgdir.mkdir(parents=True, exist_ok=True)
    snapshot_path = outdir / "audit_product.json"
    snapshot_path.write_text(json.dumps(product, ensure_ascii=False, indent=2), encoding="utf-8")
    previous_metrics = _read_json(outdir / "run_metrics.json") or {}

    refs = _image_urls(product)
    engine = None

    def ocr_engine() -> Any:
        nonlocal engine
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR()
        return engine

    metrics: dict[str, Any] = {
        "schema": METRICS_SCHEMA,
        "workflow_version": WORKFLOW_VERSION,
        "pid": pid,
        "shop": shop,
        "image_occurrences": len(refs),
        "downloads": {"cache_hits": 0, "network_fetches": 0},
        "evidence": {"cache_hits": 0, "cache_misses": 0, "writes": 0},
        "ocr": {"enabled": not no_ocr, "image_executions": 0, "cache_reuses": 0},
    }
    if isinstance(previous_metrics.get("executor"), dict):
        metrics["executor"] = previous_metrics["executor"]
    raw_images: list[dict[str, Any]] = []
    compact_images: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    all_hits: list[dict[str, Any]] = []
    border_hits: list[dict[str, Any]] = []
    residual_hits: list[dict[str, Any]] = []
    main_hashes: list[tuple[int, str, str]] = []
    classifiers: set[str] = set()
    title_context = "%s %s" % (product.get("titleEn") or "", product.get("title") or "")
    unique_content_hashes: set[str] = set()

    for ref in refs:
        url_digest = hashlib.sha1(ref["url"].encode("utf-8")).hexdigest()[:10]
        path = imgdir / f"{ref['kind']}_{ref['index']:02d}_{url_digest}.bin"
        rec = dict(ref)
        rec["file"] = _relative(path)
        try:
            needs_download = force or not path.exists() or path.stat().st_size == 0
            if needs_download:
                site.download(ref["url"], str(path))
                metrics["downloads"]["network_fetches"] += 1
            else:
                metrics["downloads"]["cache_hits"] += 1
            rec["bytes"] = path.stat().st_size
            content_hash = _sha256(path)
            rec["content_sha256"] = content_hash
            unique_content_hashes.add(content_hash)
            cache_path = EVIDENCE_CACHE / content_hash[:2] / f"{content_hash}.json"
            evidence = _read_json(cache_path)
            valid_evidence = bool(evidence and evidence.get("schema") == EVIDENCE_SCHEMA
                                  and evidence.get("sha256") == content_hash)
            image: np.ndarray | None = None
            evidence_dirty = False
            if valid_evidence:
                metrics["evidence"]["cache_hits"] += 1
            else:
                metrics["evidence"]["cache_misses"] += 1
                image = _decode(path)
                if image is None:
                    raise ValueError("cv2.imdecode returned None")
                h, w = image.shape[:2]
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                evidence = {
                    "schema": EVIDENCE_SCHEMA,
                    "sha256": content_hash,
                    "bytes": rec["bytes"],
                    "width": int(w),
                    "height": int(h),
                    "short": int(min(w, h)),
                    "ratio": round(w / h, 4),
                    "phash": _phash(gray),
                    "borders": border_candidates(gray),
                    "residual": residual_stats(gray),
                }
                evidence_dirty = True

            assert evidence is not None
            ocr_cache_valid = ("ocr" in evidence and
                               evidence.get("ocr_fingerprint") == OCR_EXTRACTOR_FINGERPRINT)
            if not no_ocr and not ocr_cache_valid:
                if image is None:
                    image = _decode(path)
                    if image is None:
                        raise ValueError("cv2.imdecode returned None")
                items, hits, classifier = run_ocr(ocr_engine(), image, title_text=title_context)
                evidence["ocr"] = items
                evidence["ocr_fingerprint"] = OCR_EXTRACTOR_FINGERPRINT
                evidence_dirty = True
                metrics["ocr"]["image_executions"] += 1
            elif not no_ocr:
                items, hits, classifier = classify_cached_ocr(evidence.get("ocr") or [], title_text=title_context)
                metrics["ocr"]["cache_reuses"] += 1
            else:
                items, hits, classifier = [], [], "disabled"

            if evidence_dirty:
                _atomic_json(cache_path, evidence)
                metrics["evidence"]["writes"] += 1

            rec.update({key: evidence[key] for key in ("width", "height", "short", "ratio", "borders", "residual")})
            if not no_ocr:
                classifiers.add(classifier)
                rec["ocr"] = items
                for hit in hits:
                    all_hits.append({"image": rec["file"], "kind": ref["kind"],
                                     "index": ref["index"], **hit})
            if ref["kind"] == "main":
                main_hashes.append((ref["index"], str(evidence["phash"]), rec["file"]))
            if rec["short"] < 800:
                anomalies.append({"type": "short_side_lt_800", "image": rec["file"],
                                  "kind": ref["kind"], "index": ref["index"], "value": rec["short"]})
            if rec["borders"]:
                border_hits.append({"image": rec["file"], "kind": ref["kind"],
                                    "index": ref["index"], "bands": rec["borders"]})
            if rec["residual"]["candidate"]:
                residual_hits.append({"image": rec["file"], "kind": ref["kind"],
                                      "index": ref["index"], "stats": rec["residual"]})
            compact_images.append({key: rec[key] for key in
                                   ("kind", "index", "source", "file", "width", "height", "short", "ratio")})
        except Exception as exc:  # continue so one bad image does not hide the product audit
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            anomalies.append({"type": "image_error", "kind": ref["kind"], "index": ref["index"],
                              "image": rec["file"], "error": rec["error"]})
        raw_images.append(rec)

    duplicates: list[dict[str, Any]] = []
    for pos, (idx_a, hash_a, file_a) in enumerate(main_hashes):
        for idx_b, hash_b, file_b in main_hashes[pos + 1:]:
            distance = _ham(hash_a, hash_b)
            if distance <= DUPLICATE_DISTANCE:
                duplicates.append({"a": idx_a, "b": idx_b, "distance": distance,
                                   "files": [file_a, file_b]})

    counts = {kind: sum(1 for ref in refs if ref["kind"] == kind) for kind in ("main", "detail", "sku")}
    if counts["main"] > 6:
        anomalies.append({"type": "main_count_gt_6", "value": counts["main"]})
    if counts["detail"] == 0:
        anomalies.append({"type": "no_detail_images"})

    title = title_checks(product, shop)
    anomalies.extend({"type": name} for name in title["anomalies"])
    desc = description_checks(product, (ref["url"] for ref in refs))
    if desc["parse_error"]:
        anomalies.append({"type": "description_parse_error", "error": desc["parse_error"]})
    unmapped = desc["external_or_unmapped_image_refs"]
    if unmapped:
        statuses = [{"url": url, "status": _head_status(url)} for url in unmapped[:40]]
        dead = [row for row in statuses if _definitely_dead(row["status"])]
        uncertain = [row for row in statuses
                     if not _definitely_dead(row["status"])
                     and not (isinstance(row["status"], int) and 200 <= row["status"] < 400)]
        desc["unmapped_status"] = statuses
        desc["dead_refs"] = dead
        desc["uncertain_refs"] = uncertain
        if dead:
            anomalies.append({"type": "description_dead_refs", "count": len(dead)})
    pool_summary: dict[str, Any] = {}
    for kind in ("main", "detail", "sku"):
        rows = [row for row in compact_images if row["kind"] == kind]
        pool_summary[kind] = {
            "count": len(rows),
            "min_short": min((row["short"] for row in rows), default=None),
            "max_short": max((row["short"] for row in rows), default=None),
        }
    identity = _json_obj(product.get("identityJson"))
    invariants = {
        "status": product.get("status"),
        "weight": product.get("weight"),
        "price": product.get("price"),
        "brand": str(product.get("brand") or product.get("brandId") or "") or None,
        "logoCode": identity.get("logoCode", ""),
        "modelCode": identity.get("modelCode"),
        "titleTranslationZh_present": bool(str(product.get("titleTranslationZh") or "").strip()),
    }
    deep = bool(anomalies or all_hits or duplicates or border_hits or residual_hits)
    flags = {
        "schema": "audit-one/v1",
        "workflow_version": WORKFLOW_VERSION,
        "pid": pid,
        "shop": shop,
        "read_only_product": True,
        "summary": {
            "suggested_mode": "deep" if deep else "fast",
            "counts": counts,
            "image_errors": sum(1 for item in raw_images if item.get("error")),
            "ocr_enabled": not no_ocr,
            "ocr_hit_count": len(all_hits),
            "duplicate_pair_count": len(duplicates),
            "border_candidate_count": len(border_hits),
            "residual_candidate_count": len(residual_hits),
            "anomaly_count": len(anomalies),
        },
        "image_summary": pool_summary,
        "anomalies": anomalies,
        "ocr_hits": all_hits,
        "duplicates": duplicates,
        "border_candidates": border_hits,
        "residual_candidates": residual_hits,
        "product_checks": {
            "invariants": invariants,
            "title_identity_brand": title,
            "description": desc,
        },
        "evidence": {
            "context": _relative(outdir / "audit_context.md"),
            "product_snapshot": _relative(snapshot_path),
            "raw": _relative(outdir / "audit_raw.json"),
            "metrics": _relative(outdir / "run_metrics.json"),
            "image_dir": _relative(imgdir),
        },
    }
    raw = {
        "schema": "audit-one-raw/v1",
        "workflow_version": WORKFLOW_VERSION,
        "pid": pid,
        "shop": shop,
        "classifier": sorted(classifiers),
        "images": raw_images,
    }
    metrics["elapsed_seconds"] = round(time.perf_counter() - audit_started, 3)
    metrics["unique_content_digests"] = len(unique_content_hashes)
    metrics["classifier_executions"] = len(raw_images) if not no_ocr else 0
    metrics["image_errors"] = sum(1 for item in raw_images if item.get("error"))
    metrics["budget"] = {
        "full_resolution_views": {"value": None, "limit": 12, "source": "agent_updates_required"},
        "temporary_scripts": {"value": None, "limit": 1, "source": "agent_updates_required"},
        "model_requests": {"value": None, "target_max": 45, "source": "external-session-ledger"},
    }
    previous_budget = previous_metrics.get("budget", {})
    if isinstance(previous_budget, dict):
        for name, row in metrics["budget"].items():
            old_row = previous_budget.get(name)
            if isinstance(old_row, dict) and "value" in old_row:
                row["value"] = old_row["value"]
    (outdir / "audit_raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    flags_path = outdir / "audit_flags.json"
    flags_path.write_text(json.dumps(flags, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "run_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "audit_context.md").write_text(_render_context(flags), encoding="utf-8")
    return flags


def _render_context(flags: dict[str, Any], max_items: int = 12) -> str:
    """Render the smallest model-facing view; detailed evidence remains in flags/raw."""
    summary = flags["summary"]
    counts = summary["counts"]
    checks = flags["product_checks"]
    inv = checks["invariants"]
    title = checks["title_identity_brand"]
    lines = [
        f"# 商品 {flags['pid']} 只读预审",
        f"- 流程：{flags.get('workflow_version')}；模式：{summary['suggested_mode']}；店铺：{flags['shop']}；状态：{inv.get('status')}",
        f"- 图片：main {counts['main']} / detail {counts['detail']} / sku {counts['sku']}；读取错误 {summary['image_errors']}",
        f"- 命中：OCR {summary['ocr_hit_count']} / 重复 {summary['duplicate_pair_count']} / 边框 {summary['border_candidate_count']} / 残差 {summary['residual_candidate_count']} / 字段异常 {summary['anomaly_count']}",
        f"- 标题：{title.get('length')} 字；前缀={title.get('prefix_ok')}；编号双格式={title.get('dual_format_ok')}",
        f"- 字段：brand={inv.get('brand')}；modelCode={inv.get('modelCode')}；logoCode={inv.get('logoCode')}；weight={inv.get('weight')}；回译={inv.get('titleTranslationZh_present')}",
    ]
    issues: list[str] = []
    for row in flags["anomalies"]:
        issues.append(f"字段 {row.get('type')}: {json.dumps(row, ensure_ascii=False, separators=(',', ':'))}")
    for row in flags["ocr_hits"]:
        issues.append(f"OCR {row.get('kind')}[{row.get('index')}]: {row.get('text')!r}")
    for row in flags["duplicates"]:
        issues.append(f"重复 main[{row.get('a')}]~main[{row.get('b')}]：hamming={row.get('distance')}")
    for row in flags["border_candidates"]:
        bands = ",".join(str(item.get("side")) for item in row.get("bands", []))
        issues.append(f"边框 {row.get('kind')}[{row.get('index')}]：{bands}")
    for row in flags["residual_candidates"]:
        issues.append(f"残差 {row.get('kind')}[{row.get('index')}]")
    lines.append("- 问题：无；按 fast 路径只看拼版。" if not issues else "## 需处理/目视复核")
    lines.extend(f"- {item}" for item in issues[:max_items])
    if len(issues) > max_items:
        lines.append(f"- 另有 {len(issues) - max_items} 项；按需读取 audit_flags.json。")
    lines.extend([
        "## 证据路由",
        "- 默认只读本文件；出现问题再读 audit_flags.json；机器明细只在必要时读 audit_raw.json。",
        "- 资源账本：run_metrics.json；只记录摘要，不把原始日志贴入上下文。",
    ])
    return "\n".join(lines) + "\n"


def _print_summary(flags: dict[str, Any], elapsed: float) -> None:
    summary = flags["summary"]
    counts = summary["counts"]
    print(f"PID {flags['pid']} shop {flags['shop']} read-only pre-audit")
    print(f"images: main={counts['main']} detail={counts['detail']} sku={counts['sku']} errors={summary['image_errors']}")
    print(f"hits: ocr={summary['ocr_hit_count']} duplicates={summary['duplicate_pair_count']} "
          f"borders={summary['border_candidate_count']} residual={summary['residual_candidate_count']}")
    print(f"anomalies={summary['anomaly_count']} suggested_mode={summary['suggested_mode']} elapsed={elapsed:.1f}s")
    print(f"context: work/pp_{flags['pid']}/audit_context.md")
    print(f"flags:   work/pp_{flags['pid']}/audit_flags.json")
    print(f"raw:     work/pp_{flags['pid']}/audit_raw.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only pre-audit for one live product")
    parser.add_argument("pid", type=int)
    parser.add_argument("--shop", type=int, default=7)
    parser.add_argument("--no-ocr", action="store_true", help="skip RapidOCR passes")
    parser.add_argument("--force", action="store_true", help="redownload cached images")
    args = parser.parse_args(argv)
    if args.shop <= 0:
        parser.error("--shop must be a positive shop id")
    started = time.time()
    try:
        flags = audit(args.pid, args.shop, no_ocr=args.no_ocr, force=args.force)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    _print_summary(flags, time.time() - started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
