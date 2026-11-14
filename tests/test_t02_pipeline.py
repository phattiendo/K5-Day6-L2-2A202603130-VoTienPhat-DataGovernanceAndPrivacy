from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from src import main as runner


def test_t02_poc_end_to_end_and_human_override(tmp_path: Path) -> None:
    """Success case: full 5-step pipeline + human review override + audit log."""
    rc = runner.main(
        [
            "--track", "t02",
            "--input", "fixtures/t02_raw_qc",
            "--output", str(tmp_path),
            "--offline",
            "--seed", "42",
        ]
    )
    assert rc == 0

    pred_file = tmp_path / "ranked_review.csv"
    queue_file = tmp_path / "review_queue.csv"
    decision_file = tmp_path / "decision.json"
    assert pred_file.exists() and queue_file.exists() and decision_file.exists()

    pred = pd.read_csv(pred_file)
    assert list(pred.columns[:2]) == ["image_id", "score"]
    assert len(pred) == 96
    assert pred["score"].is_monotonic_decreasing

    # Simulate human reviewer overriding top-1 item to KEEP
    q = pd.read_csv(queue_file, dtype=str).fillna("")
    top_id = str(q.loc[0, "item_id"])
    q.loc[0, "reviewer"] = "Vo Tien Phat"
    q.loc[0, "reviewer_decision"] = "edit"
    q.loc[0, "override_value"] = "KEEP"
    q.loc[0, "review_note"] = "Clean night scene verified manually"
    q.to_csv(tmp_path / "review_queue_reviewed.csv", index=False)

    rc2 = runner.main(
        [
            "--track", "t02",
            "--input", "fixtures/t02_raw_qc",
            "--output", str(tmp_path),
            "--offline",
            "--seed", "42",
        ]
    )
    assert rc2 == 0
    pred_after = pd.read_csv(pred_file)
    assert pred_after.loc[pred_after["image_id"] == top_id, "pred_action"].iloc[0] == "KEEP"
    assert (tmp_path / "audit_log.jsonl").exists()


def test_t02_provenance_tamper_fails_loudly(tmp_path: Path) -> None:
    """Failure/edge case: tampered image file violates manifest sha256 and exits non-zero."""
    bad_fixture = tmp_path / "t02_tampered"
    shutil.copytree("fixtures/t02_raw_qc", bad_fixture)
    first_img = next((bad_fixture / "images").glob("*.jpg"))
    arr = np.asarray(Image.open(first_img)).copy()
    arr[0, 0, 0] = (int(arr[0, 0, 0]) + 50) % 256
    Image.fromarray(arr).save(first_img)

    rc = runner.main(
        [
            "--track", "t02",
            "--input", str(bad_fixture),
            "--output", str(tmp_path / "out"),
            "--offline",
            "--seed", "42",
        ]
    )
    assert rc != 0