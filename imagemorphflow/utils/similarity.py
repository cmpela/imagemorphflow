"""Build a reusable profile-similarity database.

The main entry point is :func:`build_similarity_database`. It accepts a
well-level profile dataframe and returns one row per target/similar-profile
relationship. Plate metadata is optional, so the same function can be used for
single-plate, cross-plate, and plate-independent assays.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


DEFAULT_FEATURE_PREFIXES = (
    "Cells_",
    "Cytoplasm_",
    "Nuclei_",
)


def select_profile_features(
    profile_df: pd.DataFrame,
    feature_prefixes: Sequence[str] = DEFAULT_FEATURE_PREFIXES,
) -> List[str]:
    """Return morphology columns whose names start with a known prefix."""
    feature_prefixes = tuple(feature_prefixes)
    profile_features = [
        column
        for column in profile_df.columns
        if column.startswith(feature_prefixes)
    ]

    if not profile_features:
        raise ValueError(
            "No profile features were found. Expected columns beginning with: "
            f"{feature_prefixes}"
        )

    return profile_features


def _required_columns(
    compound_id_column: str,
    well_id_column: str,
    is_ref_column: Optional[str],
    plate_column: Optional[str],
) -> List[str]:
    columns = [compound_id_column, well_id_column]

    if is_ref_column is not None:
        columns.append(is_ref_column)

    if plate_column is not None:
        columns.append(plate_column)

    return columns


def _validate_columns(
    profile_df: pd.DataFrame,
    columns: Sequence[str],
) -> None:
    missing_columns = [
        column for column in columns if column not in profile_df.columns
    ]

    if missing_columns:
        raise KeyError(
            f"Columns missing from the profile dataframe: {missing_columns}"
        )


def _validate_identifiers(
    profile_df: pd.DataFrame,
    compound_id_column: str,
    well_id_column: str,
) -> None:
    for column in [compound_id_column, well_id_column]:
        missing_mask = (
            profile_df[column].isna()
            | profile_df[column].astype("string").str.strip().eq("")
        )
        if missing_mask.any():
            raise ValueError(
                f"Column {column!r} contains {int(missing_mask.sum())} "
                "missing or empty identifiers."
            )


def _as_reference_mask(values: pd.Series) -> np.ndarray:
    """Convert common boolean, numeric, and text reference flags to bool."""
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).to_numpy(dtype=bool)

    if pd.api.types.is_numeric_dtype(values):
        numeric_values = pd.to_numeric(values, errors="coerce").fillna(0)
        return numeric_values.ne(0).to_numpy(dtype=bool)

    true_values = {"1", "true", "t", "yes", "y"}
    normalized = (
        values
        .astype("string")
        .str.strip()
        .str.casefold()
    )
    return normalized.isin(true_values).to_numpy(dtype=bool)


def _select_rows(
    profile_df: pd.DataFrame,
    query: Optional[str],
    label: str,
) -> np.ndarray:
    if query is None:
        return np.arange(len(profile_df), dtype=int)

    try:
        selected_index = profile_df.query(query).index
    except Exception as error:
        raise ValueError(
            f"Could not apply {label}_query={query!r}."
        ) from error

    selected_positions = profile_df.index.get_indexer(selected_index)
    selected_positions = selected_positions[selected_positions >= 0]

    if len(selected_positions) == 0:
        raise ValueError(f"The {label} query selected no rows: {query!r}")

    return selected_positions.astype(int, copy=False)


def _prepare_profile_matrix(
    profile_df: pd.DataFrame,
    profile_features: Sequence[str],
    clip_value: Optional[float],
    missing_value_strategy: str,
) -> Tuple[np.ndarray, np.ndarray]:
    """Create row-centered unit vectors for vectorized Pearson correlation."""
    feature_df = profile_df.loc[:, profile_features].apply(
        pd.to_numeric,
        errors="coerce",
    )
    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)

    if missing_value_strategy == "error":
        missing_count = int(feature_df.isna().sum().sum())
        if missing_count:
            raise ValueError(
                f"The profile matrix contains {missing_count} non-finite values. "
                "Use missing_value_strategy='feature_median' to impute them."
            )
    elif missing_value_strategy == "feature_median":
        all_missing_features = feature_df.columns[
            feature_df.isna().all(axis=0)
        ].tolist()
        if all_missing_features:
            raise ValueError(
                "These profile features contain no finite values: "
                f"{all_missing_features[:10]}"
            )
        feature_df = feature_df.fillna(feature_df.median(axis=0))
    else:
        raise ValueError(
            "missing_value_strategy must be 'error' or 'feature_median'."
        )

    profile_matrix = feature_df.to_numpy(dtype=float)

    if clip_value is not None:
        if clip_value <= 0:
            raise ValueError("clip_value must be greater than zero or None.")
        profile_matrix = np.clip(
            profile_matrix,
            -float(clip_value),
            float(clip_value),
        )

    centered_matrix = profile_matrix - profile_matrix.mean(
        axis=1,
        keepdims=True,
    )
    row_norms = np.linalg.norm(centered_matrix, axis=1)
    valid_profile_mask = np.isfinite(row_norms) & (row_norms > 0)

    normalized_matrix = np.zeros_like(centered_matrix, dtype=float)
    normalized_matrix[valid_profile_mask] = (
        centered_matrix[valid_profile_mask]
        / row_norms[valid_profile_mask, None]
    )

    return normalized_matrix, valid_profile_mask


def _validate_profile_identity(
    profile_df: pd.DataFrame,
    well_id_column: str,
    plate_column: Optional[str],
) -> None:
    identity_columns = [well_id_column]
    if plate_column is not None:
        identity_columns.insert(0, plate_column)

    duplicated_mask = profile_df.duplicated(
        subset=identity_columns,
        keep=False,
    )

    if duplicated_mask.any():
        examples = (
            profile_df.loc[duplicated_mask, identity_columns]
            .head(10)
            .to_dict(orient="records")
        )
        raise ValueError(
            "Profile rows are not uniquely identified by "
            f"{identity_columns}. Examples: {examples}"
        )


def build_similarity_database(
    profile_df: pd.DataFrame,
    *,
    compound_id_column: str = "COMPOUND_ID",
    well_id_column: str = "Well_Id",
    is_ref_column: Optional[str] = "Is_Ref",
    plate_column: Optional[str] = "Plate",
    feature_prefixes: Sequence[str] = DEFAULT_FEATURE_PREFIXES,
    similarity_cutoff: float = 0.85,
    clip_value: Optional[float] = 25.0,
    missing_value_strategy: str = "error",
    compare_to_references_only: bool = False,
    target_query: Optional[str] = None,
    candidate_query: Optional[str] = None,
    include_self: bool = False,
    exclude_same_compound: bool = False,
    top_n: Optional[int] = None,
    chunk_size: int = 512,
    validate_unique_profiles: bool = True,
    generate_heatmaps: bool = False,
    heatmap_output_dir: Optional[str] = None,
    heatmap_row_height: float = 0.55,
    heatmap_font_scale: float = 1.25,
    heatmap_dpi: int = 200,
    heatmap_color_limit: float = 15.0,
) -> pd.DataFrame:
    """Calculate a reusable, database-style biosimilarity table.

    Biosimilarity is the Pearson correlation between two clipped profiles.
    Calculations are vectorized and processed in target chunks to avoid keeping
    the complete all-versus-all similarity matrix in memory.

    Parameters
    ----------
    profile_df:
        One row per profile. The dataframe may represent one or many plates.
    compound_id_column, well_id_column, is_ref_column, plate_column:
        Input metadata column names. Set ``is_ref_column=None`` or
        ``plate_column=None`` when that metadata is unavailable. If the default
        plate column is absent, plate metadata is automatically omitted.
    feature_prefixes:
        Prefixes used to identify profile features.
    similarity_cutoff:
        Keep pairs with Pearson biosimilarity greater than or equal to this
        value.
    clip_value:
        Symmetric profile-value limit. Use ``None`` to disable clipping.
    missing_value_strategy:
        ``"error"`` stops on non-finite values. ``"feature_median"`` imputes
        them using the median of each feature.
    compare_to_references_only:
        If true, candidate profiles are restricted to rows where ``Is_Ref`` is
        true. Target profiles are not restricted.
    target_query, candidate_query:
        Optional pandas-query expressions. Examples include
        ``"Plate == 'Plate_A'"`` and ``"WellType != 'Control'"``.
    include_self:
        Include a profile's correlation with itself.
    exclude_same_compound:
        Exclude every candidate having the same compound ID as the target,
        including candidates from other wells or plates.
    top_n:
        Keep only the top N hits per target after applying the cutoff.
    chunk_size:
        Number of target profiles processed at once.
    validate_unique_profiles:
        Require ``Well_Id`` or ``Plate + Well_Id`` to identify one row.
    generate_heatmaps:
        Generate one PNG per target profile. The PNG contains the target and
        every retained similar profile. Use ``False`` to create only the
        similarity dataframe/Parquet.
    heatmap_output_dir:
        Root directory for PNG files. Heatmaps are always organized as
        ``output_dir / Target_Plate / Target_Well_Id.png``.
    heatmap_row_height:
        Physical height in inches assigned to every heatmap row. Keeping this
        value fixed prevents single-hit heatmaps from having taller rows than
        heatmaps containing many hits.
    heatmap_font_scale:
        Multiplier applied to heatmap labels and titles.
    heatmap_dpi:
        Resolution of the generated PNG files.
    heatmap_color_limit:
        Symmetric color-scale limit used for every heatmap. For example, 15
        fixes all colorbars to the interval from -15 to 15.

    Returns
    -------
    pandas.DataFrame
        A directed similarity table. ``Is_Ref`` describes the target profile;
        ``Similar_Is_Ref`` describes the matched candidate. Plate columns are
        present only when plate metadata is available.
    """
    if profile_df.empty:
        raise ValueError("profile_df is empty.")
    if not -1.0 <= similarity_cutoff <= 1.0:
        raise ValueError("similarity_cutoff must be between -1 and 1.")
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")
    if top_n is not None and top_n < 1:
        raise ValueError("top_n must be at least 1 or None.")
    if generate_heatmaps and heatmap_output_dir is None:
        raise ValueError(
            "heatmap_output_dir is required when generate_heatmaps=True."
        )

    profile_df = profile_df.reset_index(drop=True).copy()

    if plate_column is not None and plate_column not in profile_df.columns:
        plate_column = None

    if generate_heatmaps and plate_column is None:
        raise ValueError(
            "Heatmap generation requires a valid plate_column because PNGs "
            "are always organized in one subdirectory per target plate."
        )

    required_columns = _required_columns(
        compound_id_column=compound_id_column,
        well_id_column=well_id_column,
        is_ref_column=is_ref_column,
        plate_column=plate_column,
    )
    _validate_columns(profile_df, required_columns)
    _validate_identifiers(
        profile_df,
        compound_id_column=compound_id_column,
        well_id_column=well_id_column,
    )

    if compare_to_references_only and is_ref_column is None:
        raise ValueError(
            "compare_to_references_only=True requires an is_ref_column."
        )

    if validate_unique_profiles:
        _validate_profile_identity(
            profile_df,
            well_id_column=well_id_column,
            plate_column=plate_column,
        )

    profile_features = select_profile_features(
        profile_df,
        feature_prefixes=feature_prefixes,
    )
    normalized_matrix, valid_profile_mask = _prepare_profile_matrix(
        profile_df,
        profile_features=profile_features,
        clip_value=clip_value,
        missing_value_strategy=missing_value_strategy,
    )

    target_positions = _select_rows(
        profile_df,
        query=target_query,
        label="target",
    )
    candidate_positions = _select_rows(
        profile_df,
        query=candidate_query,
        label="candidate",
    )

    if compare_to_references_only:
        reference_mask = _as_reference_mask(profile_df[is_ref_column])
        candidate_positions = candidate_positions[
            reference_mask[candidate_positions]
        ]

    target_positions = target_positions[valid_profile_mask[target_positions]]
    candidate_positions = candidate_positions[
        valid_profile_mask[candidate_positions]
    ]

    if len(target_positions) == 0:
        raise ValueError("No target rows have a valid, non-constant profile.")
    if len(candidate_positions) == 0:
        raise ValueError("No candidate rows have a valid, non-constant profile.")

    compound_values = profile_df[compound_id_column].astype("string").to_numpy()
    well_values = profile_df[well_id_column].astype("string").to_numpy()
    plate_values = (
        profile_df[plate_column].astype("string").to_numpy()
        if plate_column is not None
        else None
    )
    reference_values = (
        profile_df[is_ref_column].to_numpy()
        if is_ref_column is not None
        else np.full(len(profile_df), pd.NA, dtype=object)
    )

    result_frames = []

    for chunk_start in range(0, len(target_positions), chunk_size):
        chunk_targets = target_positions[
            chunk_start : chunk_start + chunk_size
        ]
        similarity_matrix = (
            normalized_matrix[chunk_targets]
            @ normalized_matrix[candidate_positions].T
        )
        similarity_matrix = np.clip(similarity_matrix, -1.0, 1.0)

        for local_target_index, target_position in enumerate(chunk_targets):
            similarities = similarity_matrix[local_target_index]
            keep_mask = similarities >= similarity_cutoff

            if not include_self:
                keep_mask &= candidate_positions != target_position

            if exclude_same_compound:
                keep_mask &= (
                    compound_values[candidate_positions]
                    != compound_values[target_position]
                )

            hit_positions = candidate_positions[keep_mask]
            hit_similarities = similarities[keep_mask]

            if len(hit_positions) == 0:
                continue

            hit_frame = pd.DataFrame(
                {
                    "Target_Compound_Id": compound_values[target_position],
                    "Target_Well_Id": well_values[target_position],
                    "Is_Ref": reference_values[target_position],
                    "Similar_Well_Id": well_values[hit_positions],
                    "Similar_Compound_Id": compound_values[hit_positions],
                    "Similar_Is_Ref": reference_values[hit_positions],
                    "Biosimilarity": hit_similarities,
                }
            )

            if plate_values is not None:
                hit_frame.insert(
                    2,
                    "Target_Plate",
                    plate_values[target_position],
                )
                hit_frame.insert(
                    6,
                    "Similar_Plate",
                    plate_values[hit_positions],
                )

            sort_columns = [
                "Biosimilarity",
                "Similar_Compound_Id",
                "Similar_Well_Id",
            ]
            ascending = [False, True, True]
            if "Similar_Plate" in hit_frame.columns:
                sort_columns.append("Similar_Plate")
                ascending.append(True)

            hit_frame = hit_frame.sort_values(
                sort_columns,
                ascending=ascending,
                kind="stable",
            )

            if top_n is not None:
                hit_frame = hit_frame.head(top_n)

            hit_frame.insert(
                len(hit_frame.columns) - 1,
                "Rank",
                np.arange(1, len(hit_frame) + 1),
            )
            result_frames.append(hit_frame)

    output_columns = [
        "Target_Compound_Id",
        "Target_Well_Id",
    ]
    if plate_column is not None:
        output_columns.append("Target_Plate")
    output_columns.extend(
        [
            "Is_Ref",
            "Similar_Well_Id",
            "Similar_Compound_Id",
        ]
    )
    if plate_column is not None:
        output_columns.append("Similar_Plate")
    output_columns.extend(
        [
            "Similar_Is_Ref",
            "Rank",
            "Biosimilarity",
        ]
    )

    if not result_frames:
        similarity_df = pd.DataFrame(columns=output_columns)
    else:
        similarity_df = pd.concat(result_frames, ignore_index=True)
        similarity_df = similarity_df.loc[:, output_columns]

        target_sort_columns = ["Target_Compound_Id"]
        if "Target_Plate" in similarity_df.columns:
            target_sort_columns.append("Target_Plate")
        target_sort_columns.extend(["Target_Well_Id", "Rank"])

        similarity_df = similarity_df.sort_values(
            target_sort_columns,
            kind="stable",
        ).reset_index(drop=True)

    if generate_heatmaps:
        generate_similarity_heatmaps(
            profile_df=profile_df,
            similarity_df=similarity_df,
            output_dir=heatmap_output_dir,
            target_positions=target_positions,
            compound_id_column=compound_id_column,
            well_id_column=well_id_column,
            plate_column=plate_column,
            feature_prefixes=feature_prefixes,
            similarity_cutoff=similarity_cutoff,
            clip_value=clip_value,
            missing_value_strategy=missing_value_strategy,
            row_height=heatmap_row_height,
            font_scale=heatmap_font_scale,
            dpi=heatmap_dpi,
            color_limit=heatmap_color_limit,
        )

    return similarity_df


def _safe_filename(value: object) -> str:
    """Return a filesystem-safe filename component."""
    safe_value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return safe_value or "profile"


def generate_similarity_heatmaps(
    profile_df: pd.DataFrame,
    similarity_df: pd.DataFrame,
    output_dir: str,
    *,
    target_positions: Optional[Sequence[int]] = None,
    compound_id_column: str = "COMPOUND_ID",
    well_id_column: str = "Well_Id",
    plate_column: Optional[str] = "Plate",
    feature_prefixes: Sequence[str] = DEFAULT_FEATURE_PREFIXES,
    similarity_cutoff: float = 0.85,
    clip_value: Optional[float] = 25.0,
    missing_value_strategy: str = "error",
    row_height: float = 0.55,
    font_scale: float = 1.25,
    dpi: int = 200,
    color_limit: float = 15.0,
) -> List[Path]:
    """Generate one fixed-row-height feature heatmap per target profile.

    Targets without any hit above the cutoff still receive a PNG containing
    their own profile. Matplotlib and seaborn are imported only when this
    function is called, so they are not required when heatmap generation is
    disabled.
    """
    if row_height <= 0:
        raise ValueError("row_height must be greater than zero.")
    if font_scale <= 0:
        raise ValueError("font_scale must be greater than zero.")
    if dpi < 1:
        raise ValueError("dpi must be at least 1.")
    if color_limit <= 0:
        raise ValueError("color_limit must be greater than zero.")

    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as error:
        raise ImportError(
            "Heatmap generation requires matplotlib and seaborn."
        ) from error

    profile_df = profile_df.reset_index(drop=True).copy()
    if plate_column is None or plate_column not in profile_df.columns:
        raise ValueError(
            "Heatmap generation requires a valid plate_column because PNGs "
            "are always organized in one subdirectory per target plate."
        )

    _validate_columns(
        profile_df,
        [compound_id_column, well_id_column]
        + ([plate_column] if plate_column is not None else []),
    )

    feature_groups = {
        prefix.rstrip("_"): [
            column
            for column in profile_df.columns
            if column.startswith(prefix)
        ]
        for prefix in feature_prefixes
    }
    profile_features = [
        feature
        for group_features in feature_groups.values()
        for feature in group_features
    ]
    if not profile_features:
        raise ValueError(
            "No profile features were found for heatmap generation."
        )

    feature_df = profile_df.loc[:, profile_features].apply(
        pd.to_numeric,
        errors="coerce",
    )
    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)

    if missing_value_strategy == "error":
        missing_count = int(feature_df.isna().sum().sum())
        if missing_count:
            raise ValueError(
                f"The heatmap matrix contains {missing_count} non-finite "
                "values. Use missing_value_strategy='feature_median' to "
                "impute them."
            )
    elif missing_value_strategy == "feature_median":
        feature_df = feature_df.fillna(feature_df.median(axis=0))
        if feature_df.isna().any().any():
            raise ValueError(
                "At least one heatmap feature contains no finite values."
            )
    else:
        raise ValueError(
            "missing_value_strategy must be 'error' or 'feature_median'."
        )

    if clip_value is not None:
        feature_df = feature_df.clip(
            lower=-float(clip_value),
            upper=float(clip_value),
        )

    if target_positions is None:
        target_positions = np.arange(len(profile_df), dtype=int)
    else:
        target_positions = np.asarray(target_positions, dtype=int)

    if np.any(target_positions < 0) or np.any(target_positions >= len(profile_df)):
        raise IndexError("target_positions contains an invalid row position.")

    compound_values = profile_df[compound_id_column].astype("string").to_numpy()
    well_values = profile_df[well_id_column].astype("string").to_numpy()
    plate_values = profile_df[plate_column].astype("string").to_numpy()

    def profile_key(position: int) -> Tuple[str, ...]:
        return (
            str(plate_values[position]),
            str(well_values[position]),
        )

    position_by_key = {
        profile_key(position): position
        for position in range(len(profile_df))
    }
    if len(position_by_key) != len(profile_df):
        raise ValueError(
            "Heatmaps require profiles to be unique by Well_Id or by "
            "Plate + Well_Id."
        )

    output_root = Path(output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []

    group_centers = []
    group_labels = []
    boundary_positions = [0]
    current_position = 0

    for group_name, group_features in feature_groups.items():
        if not group_features:
            continue
        group_start = current_position
        current_position += len(group_features)
        group_centers.append((group_start + current_position) / 2)
        group_labels.append(group_name)
        boundary_positions.append(current_position)

    base_font_size = 10.0 * font_scale

    for target_position in target_positions:
        target_position = int(target_position)
        target_compound = str(compound_values[target_position])
        target_well = str(well_values[target_position])
        target_plate = str(plate_values[target_position])

        target_hits = similarity_df.loc[
            similarity_df["Target_Well_Id"].astype(str).eq(target_well)
        ].copy()
        target_hits = target_hits.loc[
            target_hits["Target_Plate"].astype(str).eq(target_plate)
        ]
        if "Rank" in target_hits.columns:
            target_hits = target_hits.sort_values("Rank", kind="stable")

        selected_positions = [target_position]
        row_labels = [
            f"{target_compound} | {target_plate} | {target_well} | target"
        ]

        for hit in target_hits.itertuples(index=False):
            similar_well = str(hit.Similar_Well_Id)
            similar_plate = str(hit.Similar_Plate)
            hit_key = (similar_plate, similar_well)

            if hit_key not in position_by_key:
                raise KeyError(
                    "A similar profile from similarity_df was not found in "
                    f"profile_df: {hit_key}"
                )

            hit_position = position_by_key[hit_key]
            if hit_position == target_position:
                continue

            selected_positions.append(hit_position)
            row_labels.append(
                f"{hit.Similar_Compound_Id} | {similar_plate} | "
                f"{similar_well} | "
                f"{float(hit.Biosimilarity):.1%}"
            )

        heatmap_df = feature_df.iloc[selected_positions].copy()
        heatmap_df.index = row_labels
        target_only = len(heatmap_df) == 1

        figure_width = max(
            16.0,
            min(30.0, len(profile_features) * 0.055),
        )

        # These margins are physical inches. Therefore the heatmap axis has
        # exactly row_height inches per row regardless of the number of hits.
        top_margin = 0.85
        bottom_margin = 0.95
        plot_height = row_height * len(heatmap_df)
        figure_height = top_margin + plot_height + bottom_margin

        with sns.axes_style("white"):
            fig, ax = plt.subplots(
                figsize=(figure_width, figure_height),
            )
            fig.subplots_adjust(
                left=min(0.25, 3.6 / figure_width),
                right=1.0 - min(0.06, 1.0 / figure_width),
                bottom=bottom_margin / figure_height,
                top=1.0 - top_margin / figure_height,
            )

            heatmap = sns.heatmap(
                heatmap_df,
                ax=ax,
                cmap="RdBu_r",
                center=0,
                vmin=-color_limit,
                vmax=color_limit,
                xticklabels=False,
                yticklabels=not target_only,
                linewidths=0,
                rasterized=True,
                cbar_kws={
                    "label": "Value",
                    "aspect": 25,
                    "pad": 0.025,
                    "ticks": [-color_limit, 0, color_limit],
                },
            )

            for boundary in boundary_positions[1:-1]:
                ax.axvline(
                    boundary,
                    color="#262626",
                    linewidth=1.4,
                    alpha=0.9,
                )

            ax.set_xticks(group_centers)
            ax.set_xticklabels(
                group_labels,
                rotation=0,
                fontsize=base_font_size * 1.05,
                fontweight="semibold",
            )
            ax.tick_params(axis="x", length=0, pad=22)

            boundary_axis = ax.secondary_xaxis("bottom")
            boundary_axis.set_xticks(boundary_positions)
            boundary_axis.set_xticklabels(
                [
                    "1",
                    *[
                        str(position + 1)
                        for position in boundary_positions[1:-1]
                    ],
                    str(len(profile_features)),
                ],
                fontsize=base_font_size * 0.85,
                color="#4a4a4a",
            )
            boundary_axis.tick_params(
                axis="x",
                length=3,
                pad=3,
                colors="#4a4a4a",
            )
            boundary_axis.spines["bottom"].set_visible(False)

            ax.set_title(
                f"Profiles with biosimilarity ≥ {similarity_cutoff:.0%} to "
                f"{target_compound} | {target_plate} | {target_well}",
                fontsize=base_font_size * 1.2,
                fontweight="semibold",
                pad=14,
            )
            ax.set_xlabel("")
            ax.set_ylabel(
                "" if target_only else "Profiles",
                fontsize=base_font_size,
            )
            ax.tick_params(
                axis="y",
                labelsize=base_font_size,
                length=0,
                labelrotation=0,
            )

            ytick_labels = ax.get_yticklabels()
            if ytick_labels:
                ytick_labels[0].set_fontweight("bold")
                ytick_labels[0].set_color("#111111")

            colorbar = heatmap.collections[0].colorbar
            colorbar.ax.tick_params(labelsize=base_font_size * 0.85)
            colorbar.set_label(
                "Value",
                fontsize=base_font_size * 0.9,
            )

            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_linewidth(0.7)
                spine.set_color("#555555")

            target_output_dir = output_root / _safe_filename(target_plate)
            target_output_dir.mkdir(parents=True, exist_ok=True)

            output_path = target_output_dir / f"{_safe_filename(target_well)}.png"
            fig.savefig(
                output_path,
                dpi=dpi,
                bbox_inches="tight",
                facecolor="white",
            )
            plt.close(fig)

        saved_paths.append(output_path.resolve())

    return saved_paths


def save_similarity_database(
    similarity_df: pd.DataFrame,
    output_path: str,
) -> Path:
    """Save a similarity dataframe as Parquet and return its resolved path."""
    output_path = Path(output_path).expanduser()
    if output_path.suffix.casefold() != ".parquet":
        raise ValueError("The output path must end with '.parquet'.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        similarity_df.to_parquet(output_path, index=False)
    except ImportError as error:
        raise ImportError(
            "Saving Parquet requires either 'pyarrow' or 'fastparquet'. "
            "Install one of them in the active Python environment."
        ) from error
    return output_path.resolve()


def _read_profile_table(input_path: str) -> pd.DataFrame:
    input_path = Path(input_path).expanduser()
    suffix = input_path.suffix.casefold()

    if suffix == ".parquet":
        return pd.read_parquet(input_path)
    if suffix == ".tsv":
        return pd.read_csv(input_path, sep="\t")
    if suffix == ".csv":
        return pd.read_csv(input_path)

    raise ValueError("Input must be a .tsv, .csv, or .parquet file.")


def _parse_optional_column(value: str) -> Optional[str]:
    if value.strip().casefold() in {"none", "null", ""}:
        return None
    return value


def main() -> None:
    """Run the similarity calculation from the command line."""
    parser = argparse.ArgumentParser(
        description="Build a database-style profile-similarity Parquet file."
    )
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    parser.add_argument("--compound-id-column", default="COMPOUND_ID")
    parser.add_argument("--well-id-column", default="Well_Id")
    parser.add_argument("--is-ref-column", default="Is_Ref")
    parser.add_argument("--plate-column", default="Plate")
    parser.add_argument("--similarity-cutoff", type=float, default=0.85)
    parser.add_argument("--clip-value", type=float, default=25.0)
    parser.add_argument(
        "--missing-value-strategy",
        choices=["error", "feature_median"],
        default="error",
    )
    parser.add_argument("--compare-to-references-only", action="store_true")
    parser.add_argument("--target-query")
    parser.add_argument("--candidate-query")
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--exclude-same-compound", action="store_true")
    parser.add_argument("--top-n", type=int)
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--generate-heatmaps", action="store_true")
    parser.add_argument("--heatmap-output-dir")
    parser.add_argument("--heatmap-row-height", type=float, default=0.55)
    parser.add_argument("--heatmap-font-scale", type=float, default=1.25)
    parser.add_argument("--heatmap-dpi", type=int, default=200)
    parser.add_argument("--heatmap-color-limit", type=float, default=15.0)
    args = parser.parse_args()

    profile_df = _read_profile_table(args.input_path)
    similarity_df = build_similarity_database(
        profile_df,
        compound_id_column=args.compound_id_column,
        well_id_column=args.well_id_column,
        is_ref_column=_parse_optional_column(args.is_ref_column),
        plate_column=_parse_optional_column(args.plate_column),
        similarity_cutoff=args.similarity_cutoff,
        clip_value=args.clip_value,
        missing_value_strategy=args.missing_value_strategy,
        compare_to_references_only=args.compare_to_references_only,
        target_query=args.target_query,
        candidate_query=args.candidate_query,
        include_self=args.include_self,
        exclude_same_compound=args.exclude_same_compound,
        top_n=args.top_n,
        chunk_size=args.chunk_size,
        generate_heatmaps=args.generate_heatmaps,
        heatmap_output_dir=args.heatmap_output_dir,
        heatmap_row_height=args.heatmap_row_height,
        heatmap_font_scale=args.heatmap_font_scale,
        heatmap_dpi=args.heatmap_dpi,
        heatmap_color_limit=args.heatmap_color_limit,
    )
    saved_path = save_similarity_database(
        similarity_df,
        args.output_path,
    )

    print(f"Profile rows: {len(profile_df)}")
    print(f"Similarity pairs: {len(similarity_df)}")
    print(f"Similarity database saved to: {saved_path}")
    if args.generate_heatmaps:
        print(f"Heatmaps saved under: {Path(args.heatmap_output_dir).expanduser()}")


if __name__ == "__main__":
    main()
