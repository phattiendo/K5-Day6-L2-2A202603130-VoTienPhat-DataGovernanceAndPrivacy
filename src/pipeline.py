"""PoC Pipeline for T02: Context-Aware Multi-Defect Raw QC Triage."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, crop, laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


def _jpeg_blockiness(gray: np.ndarray) -> float:
    """Measure 8x8 DCT block boundary discontinuity vs interior pixel gradients."""
    H, W = gray.shape
    if H < 16 or W < 16:
        return 0.0
    h_diff = np.abs(np.diff(gray, axis=1))
    v_diff = np.abs(np.diff(gray, axis=0))

    h_cols = np.arange(1, W)
    h_bound = h_diff[:, (h_cols % 8 == 0)]
    h_inner = h_diff[:, (h_cols % 8 != 0)]

    v_rows = np.arange(1, H)
    v_bound = v_diff[(v_rows % 8 == 0), :]
    v_inner = v_diff[(v_rows % 8 != 0), :]

    bound_mean = 0.5 * (float(h_bound.mean()) + float(v_bound.mean()))
    inner_mean = 0.5 * (float(h_inner.mean()) + float(v_inner.mean()))
    return max(0.0, (bound_mean - inner_mean) / (inner_mean + 1e-5))


def _extract_raw_features(img: np.ndarray) -> dict[str, float]:
    """Extract sharpness, exposure, ROI glare, and JPEG compression blockiness."""
    H, W = img.shape[:2]
    gray = to_gray(img)
    stats = brightness_stats(img)

    # 1. Sharpness: focus on lower 75% road/vehicle zone (ignore uniform sky)
    road_roi = crop(img, 0, H * 0.25, W, H * 0.75)
    lap_road = laplacian_variance(road_roi)

    # 2. Local glare: center-lower ROI where license plates & headlights appear
    plate_roi = crop(img, W * 0.15, H * 0.35, W * 0.70, H * 0.55)
    plate_stats = brightness_stats(plate_roi)
    g_plate = to_gray(plate_roi)
    roi_sat_235 = float((g_plate > 235).mean())
    roi_peak_ratio = float(plate_stats["p95"] / (stats["mean"] + 10.0))

    # 3. Underexposure (dark): combine dark pixel ratio & low dynamic range
    dark_raw = stats["frac_dark"] + max(0.0, (55.0 - stats["p95"]) / 55.0)

    # 4. JPEG compression artifacts
    blockiness = _jpeg_blockiness(gray)

    return {
        "log_lap": float(np.log1p(lap_road)),
        "dark_raw": float(dark_raw),
        "glare_raw": float(
            2.5 * plate_stats["frac_saturated"]
            + 1.2 * roi_sat_235
            + 0.15 * max(0.0, roi_peak_ratio - 2.0)
        ),
        "blockiness_raw": float(blockiness),
        "mean_luma": float(stats["mean"]),
        "frac_sat": float(plate_stats["frac_saturated"]),
    }


def _robust_z(series: pd.Series, ref: pd.Series, higher_is_worse: bool = True) -> pd.Series:
    """Robust z-score anchored strictly on dev-split reference statistics."""
    med = float(ref.median())
    mad = float((ref - med).abs().median())
    scale = max(1.4826 * mad, float(ref.std()) * 0.5, 1e-4)
    z = (series - med) / scale
    return z if higher_is_worse else -z


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(
            actor="pipeline",
            action="provenance_problems",
            item_id=str(manifest),
            after=problems[:20],
        )
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    images_df = pd.read_csv(ctx.input_dir / "images.csv")
    return {
        "manifest": pd.read_csv(manifest) if manifest.exists() else None,
        "images": images_df,
    }


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    images = data["images"].copy()
    dev_split = str(ctx.param("dev_split", "dev"))

    feat_rows = []
    for r in images.itertuples(index=False):
        img = load_rgb(ctx.input_dir / r.path)
        feats = _extract_raw_features(img)
        feats["image_id"] = r.image_id
        feat_rows.append(feats)

    df = images.merge(pd.DataFrame(feat_rows), on="image_id", how="left")
    dev_df = df[df["split"] == dev_split] if "split" in df.columns else df
    if len(dev_df) == 0:
        dev_df = df

    # Slice-aware normalization on dev split:
    # - Sharpness normalized per (camera_id, light) to handle soft optics (cam_B) & night contrast
    # - Exposure normalized per light slice so clean night scenes are not falsely flagged as dark
    z_blur = pd.Series(0.0, index=df.index)
    z_dark = pd.Series(0.0, index=df.index)
    z_glare = pd.Series(0.0, index=df.index)
    z_comp = pd.Series(0.0, index=df.index)

    for (cam, light), idx in df.groupby(["camera_id", "light"]).groups.items():
        ref_cl = dev_df[(dev_df["camera_id"] == cam) & (dev_df["light"] == light)]
        if len(ref_cl) < 3:
            ref_cl = dev_df[dev_df["light"] == light]
        if len(ref_cl) < 3:
            ref_cl = dev_df

        ref_light = dev_df[dev_df["light"] == light]
        if len(ref_light) < 3:
            ref_light = dev_df

        z_blur.loc[idx] = _robust_z(df.loc[idx, "log_lap"], ref_cl["log_lap"], higher_is_worse=False)
        z_dark.loc[idx] = _robust_z(df.loc[idx, "dark_raw"], ref_light["dark_raw"], higher_is_worse=True)
        z_glare.loc[idx] = _robust_z(df.loc[idx, "glare_raw"], ref_light["glare_raw"], higher_is_worse=True)
        z_comp.loc[idx] = _robust_z(df.loc[idx, "blockiness_raw"], ref_cl["blockiness_raw"], higher_is_worse=True)

    # Positive anomaly evidence only (clip healthy side at 0 so clean images stay near 0)
    b_pos = z_blur.clip(lower=0.0)
    d_pos = z_dark.clip(lower=0.0)
    g_pos = z_glare.clip(lower=0.0)
    c_pos = z_comp.clip(lower=0.0)

    # Combine max dominant defect + secondary multi-defect energy
    comp_matrix = np.vstack([b_pos.to_numpy(), d_pos.to_numpy(), g_pos.to_numpy(), c_pos.to_numpy()])
    max_z = comp_matrix.max(axis=0)
    l2_z = np.sqrt((comp_matrix ** 2).sum(axis=0))
    raw_score = 0.75 * max_z + 0.25 * l2_z

    # Smooth mapping to (0, 1) while preserving strict rank order
    df["score"] = (1.0 / (1.0 + np.exp(-(raw_score - 1.5)))).round(6)
    df["slice"] = df["camera_id"].astype(str) + "|" + df["light"].astype(str)

    defect_names = ["blur", "dark", "glare", "compression"]
    top_idx = comp_matrix.argmax(axis=0)
    pred_types = []
    pred_actions = []
    reasons = []
    for i in range(len(df)):
        if max_z[i] < 1.35:
            pred_types.append("none")
            pred_actions.append("KEEP")
            reasons.append(f"clean(max_z={max_z[i]:.2f})")
        else:
            dtype = defect_names[int(top_idx[i])]
            pred_types.append(dtype)
            pred_actions.append("RECAPTURE")
            reasons.append(
                f"{dtype}(z={max_z[i]:.2f}; b={b_pos.iloc[i]:.1f},d={d_pos.iloc[i]:.1f},g={g_pos.iloc[i]:.1f},c={c_pos.iloc[i]:.1f})"
            )

    df["pred_defect_type"] = pred_types
    df["pred_action"] = pred_actions
    df["reason"] = reasons
    return df.sort_values("score", ascending=False, kind="mergesort").reset_index(drop=True)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="pred_action",
        slice_col="slice",
        evidence_col="path" if "path" in scored.columns else None,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    if "path" in scored.columns:
        render_contact_sheet(
            q,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title="T02 PoC — Top-20 Raw QC Review Queue",
        )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if not reviewed_path.exists():
        return scored

    reviewed = load_review_decisions(reviewed_path)
    ctx.stats["n_reviewed"] = len(reviewed)
    out = apply_overrides(
        scored,
        reviewed,
        id_col="image_id",
        value_col="pred_action",
        audit=ctx.audit,
    )
    # Also log approve/escalate/skip decisions for full auditability
    for r in reviewed.itertuples(index=False):
        if r.reviewer_decision not in {"edit", "reject"}:
            ctx.audit.log(
                actor=r.reviewer,
                action=f"review:{r.reviewer_decision}",
                item_id=r.item_id,
                reason=r.review_note,
            )
    return out


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = str(ctx.config.get("owner", "Vo Tien Phat (Data QC Lead)"))
    n_total = len(final)
    n_recapture = int((final["pred_action"] == "RECAPTURE").sum())
    recapture_rate = n_recapture / max(n_total, 1)
    max_rate = float(ctx.param("rework_rate_threshold", 0.25))
    n_reviewed = int(ctx.stats.get("n_reviewed", 0))

    evidence = [str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv"))]
    metrics_snap = {
        "n_total": n_total,
        "n_recapture": n_recapture,
        "recapture_rate": round(recapture_rate, 4),
        "n_reviewed": n_reviewed,
    }

    if n_reviewed == 0:
        return Decision(
            status="HOLD",
            reason_code="AWAITING_HUMAN_QC_REVIEW",
            reason=f"Top-{ctx.param('budget', 20)} review queue generated ({n_recapture}/{n_total} flagged RECAPTURE); awaiting human sign-off.",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snap,
        )

    if recapture_rate > max_rate:
        return Decision(
            status="REWORK",
            reason_code="DEFECT_RATE_ABOVE_THRESHOLD",
            reason=f"Confirmed recapture rate {recapture_rate:.1%} exceeds {max_rate:.1%} threshold; send flagged batch back for recapture.",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snap,
        )

    return Decision(
        status="GO",
        reason_code="QC_TRIAGE_APPROVED",
        reason=f"Human QC completed ({n_reviewed} reviewed); clean batch approved with {n_recapture}/{n_total} items routed to recapture.",
        owner=owner,
        scope=ctx.track,
        evidence=evidence,
        metrics=metrics_snap,
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    out_cols = spec.pred_columns + [
        c for c in ["pred_defect_type", "pred_action", "slice", "reason"] if c in final.columns and c not in spec.pred_columns
    ]
    final[out_cols].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))