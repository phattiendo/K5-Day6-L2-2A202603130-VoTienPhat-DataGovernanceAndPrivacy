"""T02 Baseline: Single global Laplacian variance score (no camera/light normalization, no ROI)."""
from __future__ import annotations

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import laplacian_variance, load_rgb
from .common.manifest import verify_manifest
from .common.review import make_review_queue, write_review_queue
from .metrics.tracks import get_track


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    manifest = ctx.input_dir / "manifest.csv"
    if manifest.exists():
        problems = verify_manifest(manifest)
        if problems and ctx.config.get("strict_provenance", True):
            raise ValueError(f"Provenance check failed: {problems[:3]}")

    images = pd.read_csv(ctx.input_dir / "images.csv")
    rows = []
    for r in images.itertuples(index=False):
        img = load_rgb(ctx.input_dir / r.path)
        lap = laplacian_variance(img)
        # Global inverse sharpness: lower Laplacian variance -> higher defect suspicion score
        score = float(1.0 / (1.0 + lap))
        rows.append(
            {
                "image_id": r.image_id,
                "path": r.path,
                "slice": f"{r.camera_id}|{r.light}",
                "laplacian": lap,
                "score": score,
                "pred_defect_type": "blur" if lap < 120.0 else "none",
                "pred_action": "RECAPTURE" if lap < 120.0 else "KEEP",
                "reason": f"global_laplacian={lap:.1f}",
            }
        )

    df = pd.DataFrame(rows)
    ctx.stats["n_items"] = len(df)
    budget = int(ctx.param("budget", 20))

    q = make_review_queue(
        df,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="pred_action",
        slice_col="slice",
        evidence_col="path",
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(
        q,
        ctx.out("contact_sheet.html"),
        image_root=ctx.input_dir,
        title="T02 Baseline (Global Laplacian) — Review Queue",
    )

    ranked = df.sort_values("score", ascending=False, kind="mergesort")
    ranked[["image_id", "score", "pred_defect_type", "pred_action"]].to_csv(
        ctx.out(spec.pred_file), index=False
    )

    write_decision(
        Decision(
            status="HOLD",
            reason_code="BASELINE_GLOBAL_LAPLACIAN",
            reason="Global Laplacian baseline ignores night/camera domain shift and local glare; do not release.",
            owner=ctx.config.get("owner", "Vo Tien Phat"),
            scope=ctx.track,
            evidence=[str(ctx.out(spec.pred_file))],
        ),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )