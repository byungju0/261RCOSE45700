"""포스트 단위 저장 모듈.

output/posts/{site_id}/{post_id}/
    post.json   ← 텍스트 + 이미지 메타데이터
    img_001.jpg ← 사용자 업로드 이미지
    img_002.png
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from crawler.src.crawl4ai_crawler import CrawlResult
from crawler.src.s3_uploader import S3Uploader
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "crawler")
_logger = get_logger(__name__)
_TRUTHY_ENV_VALUES = frozenset({"true", "1", "yes"})
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
# crawl4ai_crawler._download_images writes files as `img_{i:03d}{ext}` where i is
# the index into the original `result.images` list. We parse i back from the name
# to keep metadata aligned even when some downloads fail.
_IMG_INDEX_RE = re.compile(r"^img_(\d+)")


def _is_truthy(env_value: str | None) -> bool:
    if env_value is None:
        return False
    return env_value.strip().lower() in _TRUTHY_ENV_VALUES


def _validate_id(name: str, value: str) -> None:
    if not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(
            f"{name} must match {_SAFE_ID_RE.pattern}; got {value!r}"
        )


def _meta_for_downloaded(src_path: Path, images: list[dict]) -> dict:
    match = _IMG_INDEX_RE.match(src_path.stem)
    if not match:
        return {}
    idx = int(match.group(1))
    if 0 <= idx < len(images):
        return images[idx]
    return {}


@dataclass
class StorageResult:
    local_path: Path
    s3_text_path: str = ""
    s3_image_paths: list[str] = field(default_factory=list)


class PostStorage:
    def __init__(self, base_dir: str = "output/posts") -> None:
        self._base = Path(base_dir)
        if _is_truthy(os.environ.get("ENABLE_S3_UPLOAD")):
            bucket = (os.environ.get("S3_BUCKET_NAME") or "").strip()
            if not bucket:
                raise ValueError("S3_BUCKET_NAME is required when ENABLE_S3_UPLOAD=true")
            self._s3_uploader: S3Uploader | None = S3Uploader(bucket)
        else:
            self._s3_uploader = None

    def save(
        self,
        *,
        site_id: str,
        post_id: str,
        url: str,
        result: CrawlResult,
        correlation_id: str = "",
    ) -> StorageResult:
        """포스트 데이터를 디스크에 저장하고 StorageResult를 반환."""
        _validate_id("site_id", site_id)
        _validate_id("post_id", post_id)

        now = datetime.now(timezone.utc)
        post_dir = self._base / site_id / post_id
        post_dir.mkdir(parents=True, exist_ok=True)

        # downloaded_images를 source-of-truth로 사용. 파일명 인덱스로 result.images 매핑.
        image_records: list[dict] = []
        for src_path in result.downloaded_images:
            if not src_path.exists():
                _logger.warning(
                    "다운로드 이미지 파일 없음 — 스킵: %s", src_path,
                    extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                )
                continue
            dest = post_dir / src_path.name
            dest.write_bytes(src_path.read_bytes())
            src_path.unlink(missing_ok=True)
            meta = _meta_for_downloaded(src_path, result.images)
            image_records.append({
                "filename": dest.name,
                "src": meta.get("src", ""),
                "alt": meta.get("alt", ""),
                "score": meta.get("score", 0),
            })

        post_data = {
            "post_id": post_id,
            "site": site_id,
            "url": url,
            "crawled_at": now.isoformat(),
            "text": result.markdown,
            "images": image_records,
        }
        (post_dir / "post.json").write_text(
            json.dumps(post_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        s3_text_path = ""
        s3_image_paths: list[str] = []
        if self._s3_uploader is not None:
            date_str = now.strftime("%Y-%m-%d")
            s3_text_path = self._s3_uploader.upload_text(
                result.markdown,
                site=site_id,
                date=date_str,
                post_id=post_id,
                correlation_id=correlation_id,
            )
            local_img_paths = [post_dir / r["filename"] for r in image_records]
            s3_image_paths = self._s3_uploader.upload_images(
                local_img_paths,
                site=site_id,
                date=date_str,
                post_id=post_id,
                correlation_id=correlation_id,
            )

        return StorageResult(
            local_path=post_dir,
            s3_text_path=s3_text_path,
            s3_image_paths=s3_image_paths,
        )
