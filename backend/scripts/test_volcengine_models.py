#!/usr/bin/env python3
"""批量测试火山方舟已接入模型的连通性。"""
from __future__ import annotations

import json
import sys
import time

from app.core import llm
from app.core.llm_models import VOLCENGINE_MODELS

# 方舟模型连通性测试清单（model 字段与 llm_models.VOLCENGINE_MODELS 对齐）
TARGET_MODELS = [
    ("Doubao-Seed-2.1-pro", "doubao-seed-2-1-pro-260628"),
    ("Doubao-Seed-2.1-turbo", "doubao-seed-2-1-turbo-260628"),
    ("Doubao-Seed-Evolving", "doubao-seed-evolving"),
    ("Doubao-Seed-2.0-pro", "doubao-seed-2-0-pro-260215"),
    ("Doubao-Seed-2.0-lite", "doubao-seed-2-0-lite-260215"),
    ("DeepSeek-V4-pro", "deepseek-v4-pro"),
    ("DeepSeek-V4-flash", "deepseek-v4-flash"),
]


def main() -> None:
    print("火山方舟模型连通性测试\n")
    results: list[dict] = []
    for label, model_id in TARGET_MODELS:
        res = llm.test_connection(provider="volcengine", model=model_id)
        row = {"label": label, "model": model_id, **res}
        results.append(row)
        status = "OK" if res.get("ok") else "FAIL"
        print(f"[{status}] {label} ({model_id})")
        if res.get("ok"):
            print(f"       回复: {str(res.get('reply', ''))[:80]}")
            print(f"       耗时: {res.get('duration_ms')}ms")
        else:
            print(f"       错误: {str(res.get('message', ''))[:240]}")
        print()

    ok = [r for r in results if r.get("ok")]
    print("=" * 60)
    print(f"成功 {len(ok)} / {len(TARGET_MODELS)}")
    catalog_ids = {m["id"] for m in VOLCENGINE_MODELS}
    missing = [mid for _, mid in TARGET_MODELS if mid not in catalog_ids]
    if missing:
        print("警告: 以下 model 未写入 llm_models 目录:", missing)

    if len(ok) < len(TARGET_MODELS):
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
