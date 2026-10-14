#!/usr/bin/env python3
"""Generate self-contained compound-level Cell Painting HTML reports."""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import warnings
from collections.abc import Mapping, Sequence
from datetime import date
from html import escape
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd

from .report_templ_summary import (
    DETAILS_TEMPL,
    HTML_EXTRO,
    HTML_INTRO,
    PARM_TABLE_ROW,
    SIMILAR_COMPOUNDS_TABLE_HEADER,
    SIMILAR_COMPOUNDS_TABLE_ROW,
    IMAGES_TABLE,
    mol_img_tag,
    optional_detail_row,
    detail_row,
)


MISSING_STRINGS = {"", "nan", "none", "na", "n/a", "<na>"}

# The first existing column in each tuple is used unless column_map overrides it.
COLUMNS = {
    "plate": ("Plate", "Metadata_Plate", "PLATE"),
    "well_id": ("Well_Id", "Well_ID", "WELL_ID"),
    "well_type": ("WellType", "Well_Type"),
    "smiles": (
        "Smiles",
        "SMILES",
        "Full_Smiles",
        "Full_SMILES",
        "Isomeric_SMILES",
        "Canonical_SMILES",
    ),
    "compound_id": ("COMPOUND_ID", "Compound_Id", "Compound_ID"),
    "is_ref": ("Is_Ref", "IsRef", "Reference", "Ref"),
    "condition": ("Condition",),
    "concentration": ("Conc_uM", "Concentration", "Metadata_Concentration"),
    "induction": ("Induction", "Activity"),
    "trivial_name": ("Trivial_Name",),
    "known_activity": ("Known_Act", "Known_Activity", "MOA", "MoA"),
    "manual_cluster": (
        "Manual_Cluster",
        "Manual_Cluster_Annotation",
        "Cluster_Annotation",
        "Metadata_Cluster_manual_annotation"
    ),
    "producer": ("Producer",),
    "batch_id": ("Batch_Id", "Batch_ID"),
    "supplier_id": ("Supplier_Id", "Supplier_ID", "SUPPLIER_ID"),
    "chiral": ("Chiral",),
    "pure_flag": ("Pure_Flag", "Purity_Flag"),
    "timepoint": ("TP", "Time_Point", "Metadata_Time"),
    # "overactivity": ("OverAct", "Lysosomotropic_Similarity"),
    "relative_cell_count": (
        "Rel_Count_Cells [%]",
        "Rel_Cell_Count",
        "Rel_Count_Cells",
        "Relative_Cell_Count",
        
    ),
    "plate_well": (
        "Well",
        "Metadata_Well",
        "metadata_well",
    ),
}

REQUIRED_REPORT_FIELDS = ("plate", "well_id", "compound_id")
DEFAULT_FEATURE_PREFIXES = ("Cells_", "Cytoplasm_", "Nuclei_")
DEFAULT_CONTROL_LABELS = (
    "control",
    "negative control",
    "negative_control",
    "negcon",
    "dmso",
)


def safe_filename(value: object) -> str:
    """Convert an identifier into a filesystem-safe filename."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")


def _column(df: pd.DataFrame, key: str, required: bool = False) -> str | None:
    """Return the first configured column present in a dataframe."""
    internal_column = f"__report_{key}"
    if internal_column in df.columns:
        return internal_column
    for candidate in COLUMNS[key]:
        if candidate in df.columns:
            return candidate
    if required:
        raise KeyError(
            f"Missing column for '{key}'. Expected one of: {COLUMNS[key]}"
        )
    return None


def resolve_report_columns(
    df: pd.DataFrame,
    column_map: Mapping[str, str | None] | None = None,
    required_fields: Sequence[str] = REQUIRED_REPORT_FIELDS,
) -> dict[str, str | None]:
    """Resolve semantic report fields to concrete dataframe columns.

    ``column_map`` uses semantic keys such as ``compound_id``, ``well_id``,
    ``plate_well``, and ``induction``. A value of ``None`` explicitly disables
    an optional field.
    """
    column_map = dict(column_map or {})
    unknown_fields = sorted(set(column_map) - set(COLUMNS))
    if unknown_fields:
        raise KeyError(
            f"Unknown column_map fields: {unknown_fields}. "
            f"Valid fields are: {sorted(COLUMNS)}"
        )

    resolved: dict[str, str | None] = {}
    for field, aliases in COLUMNS.items():
        if field in column_map:
            selected = column_map[field]
            if selected is not None and selected not in df.columns:
                raise KeyError(
                    f"column_map[{field!r}]={selected!r} is not present in "
                    "the profile dataframe."
                )
            resolved[field] = selected
        else:
            resolved[field] = next(
                (column for column in aliases if column in df.columns),
                None,
            )

    missing_required = [
        field for field in required_fields if resolved.get(field) is None
    ]
    if missing_required:
        expected = {
            field: list(COLUMNS[field]) for field in missing_required
        }
        raise KeyError(
            "Could not resolve required report fields: "
            f"{missing_required}. Expected aliases: {expected}. "
            "Use column_map to provide the actual column names."
        )

    return resolved


def inspect_report_inputs(
    df: pd.DataFrame,
    column_map: Mapping[str, str | None] | None = None,
    feature_prefixes: Sequence[str] = DEFAULT_FEATURE_PREFIXES,
) -> pd.DataFrame:
    """Return a compact schema report before generating any files."""
    resolved = resolve_report_columns(
        df,
        column_map=column_map,
        required_fields=(),
    )
    required = set(REQUIRED_REPORT_FIELDS)
    rows = []
    for field, aliases in COLUMNS.items():
        column = resolved[field]
        rows.append(
            {
                "Field": field,
                "Required": field in required,
                "Resolved_Column": column,
                "Status": "found" if column is not None else "missing",
                "Non_Missing": (
                    int(df[column].notna().sum()) if column is not None else 0
                ),
                "Unique_Values": (
                    int(df[column].nunique(dropna=True))
                    if column is not None
                    else 0
                ),
                "Accepted_Aliases": ", ".join(aliases),
            }
        )

    feature_columns = [
        column
        for column in df.columns
        if column.startswith(tuple(feature_prefixes))
    ]
    rows.append(
        {
            "Field": "profile_features",
            "Required": True,
            "Resolved_Column": f"{len(feature_columns)} columns",
            "Status": "found" if feature_columns else "missing",
            "Non_Missing": np.nan,
            "Unique_Values": np.nan,
            "Accepted_Aliases": ", ".join(feature_prefixes),
        }
    )
    return pd.DataFrame(rows)


def _prepare_report_dataframe(
    df: pd.DataFrame,
    resolved_columns: Mapping[str, str | None],
) -> pd.DataFrame:
    """Create internal semantic columns without modifying the user's frame."""
    prepared = df.copy()
    for field, source_column in resolved_columns.items():
        if source_column is not None:
            prepared[f"__report_{field}"] = prepared[source_column]
    return prepared


def _is_missing(value: object) -> bool:
    """Return whether a scalar should be displayed as missing."""
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() in MISSING_STRINGS


def _text(value):
    """Format a value for HTML display."""
    if _is_missing(value):
        return "—"

    return escape(str(value).strip())


def _number(value: object, decimals: int = 2, default: str = "-") -> str:
    """Format a numeric value without unnecessary trailing zeroes."""
    if _is_missing(value):
        return default
    try:
        formatted = f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return _text(value)
    return formatted.rstrip("0").rstrip(".")


def _value(row: pd.Series, df: pd.DataFrame, key: str) -> object:
    """Read a configured value from a row."""
    column = _column(df, key)
    return None if column is None else row[column]


def resolve_extra_report_fields(
    df: pd.DataFrame,
    extra_report_fields: Mapping[
        str,
        str | Sequence[str] | Mapping[str, object],
    ] | None,
    missing_field_policy: str = "skip",
) -> list[dict[str, object]]:
    """Resolve optional assay-specific fields used in report details.

    The mapping key is the label displayed in the HTML report. Its value can
    be a column name, a sequence of column aliases, or a configuration mapping
    with ``column``/``aliases``, ``format``, ``decimals``, ``scale``,
    ``suffix``, and ``skip_missing``.
    """
    valid_policies = {"skip", "warn", "raise"}
    if missing_field_policy not in valid_policies:
        raise ValueError(
            "missing_field_policy must be one of: "
            f"{sorted(valid_policies)}."
        )

    resolved_fields: list[dict[str, object]] = []

    for label, field_spec in (extra_report_fields or {}).items():
        if isinstance(field_spec, str):
            config: dict[str, object] = {"aliases": (field_spec,)}
        elif isinstance(field_spec, Mapping):
            config = dict(field_spec)
            configured_columns = config.pop(
                "aliases",
                config.pop("column", None),
            )
            if configured_columns is None:
                raise ValueError(
                    f"Extra report field {label!r} must define "
                    "'column' or 'aliases'."
                )
            config["aliases"] = configured_columns
        elif isinstance(field_spec, Sequence):
            config = {"aliases": tuple(field_spec)}
        else:
            raise TypeError(
                f"Invalid configuration for extra report field {label!r}: "
                f"{type(field_spec).__name__}."
            )

        aliases = config["aliases"]
        if isinstance(aliases, str):
            aliases = (aliases,)
        else:
            aliases = tuple(aliases)
        if not aliases or not all(isinstance(column, str) for column in aliases):
            raise ValueError(
                f"Extra report field {label!r} has invalid column aliases."
            )

        selected_column = next(
            (column for column in aliases if column in df.columns),
            None,
        )
        if selected_column is None:
            message = (
                f"No column was found for extra report field {label!r}. "
                f"Expected one of: {list(aliases)}."
            )
            if missing_field_policy == "raise":
                raise KeyError(message)
            if missing_field_policy == "warn":
                warnings.warn(message, stacklevel=2)
            continue

        value_format = str(config.get("format", "text")).casefold()
        if value_format not in {"text", "number", "percent"}:
            raise ValueError(
                f"Unsupported format {value_format!r} for extra report "
                f"field {label!r}."
            )

        resolved_fields.append(
            {
                "label": str(label),
                "column": selected_column,
                "format": value_format,
                "decimals": int(config.get("decimals", 2)),
                "scale": float(config.get("scale", 1.0)),
                "suffix": str(config.get("suffix", "")),
                "skip_missing": bool(config.get("skip_missing", True)),
            }
        )

    return resolved_fields


def _extra_report_rows(
    row: pd.Series,
    resolved_extra_fields: Sequence[Mapping[str, object]],
) -> str:
    """Build HTML rows for optional assay-specific report fields."""
    rows = []

    for field_spec in resolved_extra_fields:
        value = row[str(field_spec["column"])]
        if _is_missing(value) and bool(field_spec["skip_missing"]):
            continue

        value_format = str(field_spec["format"])
        if value_format == "text":
            formatted_value = value
        else:
            try:
                scaled_value = float(value) * float(field_spec["scale"])
            except (TypeError, ValueError):
                formatted_value = value
            else:
                formatted_value = _number(
                    scaled_value,
                    decimals=int(field_spec["decimals"]),
                )
                suffix = str(field_spec["suffix"])
                if value_format == "percent" and not suffix:
                    suffix = "%"
                if formatted_value not in {"-", "—"}:
                    formatted_value = f"{formatted_value}{suffix}"

        rows.append(
            detail_row(
                str(field_spec["label"]),
                formatted_value,
            )
        )

    return "".join(rows)


def _image_data_uri(image_path: Path) -> str:
    """Convert an image file to a base64 data URI."""
    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _heatmap_html(image_path: Path | None, well_id: str) -> str:
    """Return an embedded heatmap or a clear missing-image notice."""
    if image_path is None:
        return '<p class="missing-heatmap">Heatmap generation was disabled.</p>'
    if not image_path.is_file():
        return (
            '<p class="missing-heatmap">Heatmap unavailable: '
            f"{escape(str(image_path))}</p>"
        )
    return (
        '<div class="feature-heatmap">'
        f'<img src="{_image_data_uri(image_path)}" '
        f'alt="Feature heatmap for {escape(well_id)}">'
        "</div>"
    )


def _molecule_html(
    smiles: object,
    cache: dict[str, str],
    size: int,
) -> str:
    """Draw each unique SMILES once and reuse its embedded HTML."""
    key = "" if _is_missing(smiles) else str(smiles).strip()
    if key not in cache:
        cache[key] = mol_img_tag(key or None, size=size)
    return cache[key]


def _single_profile(
    df: pd.DataFrame,
    plate: object,
    well_id: object,
) -> pd.Series:
    """Retrieve exactly one profile using Plate and Well_Id."""
    plate_column = _column(df, "plate", required=True)
    well_column = _column(df, "well_id", required=True)
    matches = df.loc[
        df[plate_column].astype(str).eq(str(plate))
        & df[well_column].astype(str).eq(str(well_id))
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one row for Plate={plate!r}, Well_Id={well_id!r}; "
            f"found {len(matches)}."
        )
    return matches.iloc[0]


def _format_similarity(value):
    """Format similarity consistently as a percentage."""
    if _is_missing(value):
        return "n/a"

    try:
        value = float(value)
    except (TypeError, ValueError):
        return _text(value)

    # Convert correlations stored between -1 and 1 to percentages
    if -1.0 <= value <= 1.0:
        value *= 100

    return f"{value:.1f}%"


def _similar_compounds_table(
    df,
    similarities,
    molecule_cache,
    current_report_path,
    report_root,
    similarity_cutoff,
):
    """Build the similar-compound table in saved rank order."""
    if similarities.empty:
        return (
            '<p class="no-similar">'
            f"No compounds reached {similarity_cutoff:.0%} biosimilarity."
            "</p>"
        )

    similarity_column = next(
        (
            column
            for column in (
                "Similarity",
                "Profile_Similarity",
                "Pearson",
                "Correlation",
                "Biosimilarity"
            )
            if column in similarities.columns
        ),
        None,
    )

    if similarity_column is None:
        raise KeyError(
            "No similarity column was found. "
            f"Available columns: {similarities.columns.tolist()}"
        )

    sort_columns = (
        ["Rank"]
        if "Rank" in similarities.columns
        else [similarity_column]
    )
    ascending = "Rank" in similarities.columns

    sorted_similarities = similarities.sort_values(
        sort_columns,
        ascending=ascending,
    )

    rows = []

    for _, similarity in sorted_similarities.iterrows():
        similar_well_id = str(
            similarity["Similar_Well_Id"]
        )
        similar_plate = str(
            similarity["Similar_Plate"]
        )
        similarity_value = similarity[
            similarity_column
        ]

        candidate_row = _single_profile(
            df,
            similar_plate,
            similar_well_id,
        )

        similar_report_path = (
            Path(report_root)
            / safe_filename(similar_plate)
            / f"{safe_filename(similar_well_id)}.html"
        )

        report_link = os.path.relpath(
            similar_report_path,
            start=Path(current_report_path).parent,
        )

        row_values = {
            "mol_img": _molecule_html(
                _value(candidate_row, df, "smiles"),
                molecule_cache,
                size=130,
            ),
            "Well_Id": _text(similar_well_id),
            "Activity": _number(
                _value(candidate_row, df, "induction"),
                decimals=1,
            ),
            "Similarity": _format_similarity(
                similarity_value
            ),
            "Trivial_Name": _text(
                _value(candidate_row, df, "trivial_name")
            ),
            "Known_Act": _text(
                _value(candidate_row, df, "known_activity")
            ),
            "Report_Link": escape(
                report_link,
                quote=True,
            ),
        }

        rows.append(
            Template(
                SIMILAR_COMPOUNDS_TABLE_ROW
            ).substitute(row_values)
        )

    return (
        '<div class="similar-table-wrap">'
        '<table class="similar-table">'
        f"{SIMILAR_COMPOUNDS_TABLE_HEADER}"
        f"{''.join(rows)}"
        "</table>"
        "</div>"
    )


def _parameter_table(row: pd.Series, profile_features: list[str]) -> str:
    """Build the feature-value table in the supplied feature order."""
    rows = []
    for index, feature in enumerate(profile_features, start=1):
        values = {
            "idx": index,
            "Parameter": escape(feature),
            "Value": _number(row[feature], decimals=4),
        }
        rows.append(Template(PARM_TABLE_ROW).substitute(values))
    return "".join(rows)


def _normalise_well(well):
    """Normalise plate wells to formats such as A01 or P24."""
    match = re.fullmatch(
        r"([A-Pa-p])0?(\d{1,2})",
        str(well).strip(),
    )

    if match is None:
        raise ValueError(
            f"Invalid Metadata_Well value: {well!r}"
        )

    row = match.group(1).upper()
    column = int(match.group(2))

    return f"{row}{column:02d}"


def _control_well(compound_well, control_column=11):
    """Return a control well from the same row and configured column."""
    compound_well = _normalise_well(compound_well)
    row = compound_well[0]

    return f"{row}{int(control_column):02d}"


def _representative_image_html(image_path, alt_text):
    """Embed a representative image directly into the HTML report."""
    image_path = Path(image_path)

    if not image_path.is_file():
        return (
            '<div class="missing-image">'
            "Image not available"
            "</div>"
        )

    mime_type = (
        mimetypes.guess_type(image_path.name)[0]
        or "image/jpeg"
    )

    encoded_image = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    return (
        f'<img src="data:{mime_type};base64,{encoded_image}" '
        f'alt="{escape(str(alt_text), quote=True)}" '
        'loading="lazy">'
    )


def _representative_images_table(
    plate,
    compound_well,
    control_well,
    image_root,
):
    """Build the compound-versus-control representative-image table."""
    plate = str(plate).strip()
    compound_well = _normalise_well(compound_well)
    control_well = _normalise_well(control_well)

    image_directory = (
        Path(image_root)
        / safe_filename(plate)
        / "images"
    )

    # Display order:
    # Mitochondria, AGP, RNA, ER, Nuclei.
    channel_order = {
        1: 5,
        2: 4,
        3: 3,
        4: 2,
        5: 1,
    }

    values = {}

    for display_position, wavelength in channel_order.items():
        compound_path = (
            image_directory
            / f"{compound_well}_w{wavelength}.jpg"
        )

        control_path = (
            image_directory
            / f"{control_well}_w{wavelength}.jpg"
        )

        values[f"Img_{display_position}_Cpd"] = (
            _representative_image_html(
                compound_path,
                (
                    f"{plate}, compound well "
                    f"{compound_well}, w{wavelength}"
                ),
            )
        )

        values[f"Img_{display_position}_Ctrl"] = (
            _representative_image_html(
                control_path,
                (
                    f"{plate}, control well "
                    f"{control_well}, w{wavelength}"
                ),
            )
        )

    return Template(IMAGES_TABLE).substitute(values)

def _report_values(
    df,
    row,
    plate,
    well_id,
    control_well,
    similarities,
    heatmap_path,
    profile_features,
    molecule_cache,
    current_report_path,
    report_root,
    representative_image_root,
    include_representative_images,
    similarity_cutoff,
    resolved_extra_fields,
):
    """Collect every placeholder required by the detailed template."""
    condition = _value(row, df, "condition")
    manual_cluster = _value(row, df, "manual_cluster")
    trivial_name = _value(row, df, "trivial_name")
    known_activity = _value(row, df, "known_activity")
    plate_well = _value(row, df, "plate_well")

    if include_representative_images:
        images_description = (
            "<p>"
            f"Representative images from compound well "
            f"{_text(plate_well)} and negative-control well "
            f"{_text(control_well)} on the selected plate."
            "</p>"
        )
        images_html = _representative_images_table(
            plate=plate,
            compound_well=plate_well,
            control_well=control_well,
            image_root=representative_image_root,
        )
    else:
        images_description = (
            '<p class="missing-image">Representative images were disabled.</p>'
        )
        images_html = ""

    return {
        "mol_img": _molecule_html(
            _value(row, df, "smiles"), molecule_cache, size=300
        ),
        "Compound_Id": _text(_value(row, df, "compound_id")),
        "Well_Id": _text(well_id),
        "Condition_Row": optional_detail_row(
            "Condition / Plate",
            str(plate) if _is_missing(condition) else f"{condition} / {plate}",
        ),
        "Manual_Cluster_Row": optional_detail_row(
            "Manual Cluster Annotation (based on U2OS)", manual_cluster
        ),
        "Trivial_Name_Row": detail_row("Trivial Name", trivial_name),
        "Known_Act_Row": detail_row("Known Activity", known_activity),
        "Extra_Report_Rows": _extra_report_rows(
            row,
            resolved_extra_fields,
        ),
        "Producer": _text(_value(row, df, "producer")),
        "Batch_Id": _text(_value(row, df, "batch_id")),
        "Supplier_Id": _text(_value(row, df, "supplier_id")),
        "Chiral": _text(_value(row, df, "chiral")),
        "Pure_Flag": _text(_value(row, df, "pure_flag")),
        "Conc_uM": _number(_value(row, df, "concentration"), decimals=3),
        "TP": _number(_value(row, df, "timepoint"), decimals=2),
        "Activity": _number(_value(row, df, "induction"), decimals=2),
        # "OverAct": _number(_value(row, df, "overactivity"), decimals=2),
        "Rel_Cell_Count": _number(
            _value(row, df, "relative_cell_count"), decimals=2
        ),
        "Reference": _text(_value(row, df, "is_ref")),
        "Top_N": len(similarities),
        "Heatmap": _heatmap_html(heatmap_path, well_id),
        "Images_Description": images_description,
        "Images": images_html,
        "Parm_Table": _parameter_table(row, profile_features),
        "Date": date.today().isoformat(),
        "Similar_Compounds_Table": _similar_compounds_table(
            df=df,
            similarities=similarities,
            molecule_cache=molecule_cache,
            current_report_path=current_report_path,
            report_root=report_root,
            similarity_cutoff=similarity_cutoff,
        ),
    }


REPORT_CSS = """
<style>
.feature-heatmap { width: 100%; overflow-x: auto; margin: 12px 0 24px; }
.feature-heatmap img { display: block; max-width: 100%; height: auto; margin: auto; }
.similar-table-wrap { width: 100%; overflow-x: auto; }
.similar-table { border-collapse: collapse; width: 100%; }
.similar-table th, .similar-table td { padding: 6px 8px; vertical-align: middle; }
.similar-table .molecule-image { width: 130px; height: 130px; object-fit: contain; }
.mol-unavailable, .missing-heatmap, .no-similar { color: #666; font-style: italic; }
</style>
"""


def generate_compound_reports(
    df: pd.DataFrame,
    similarity_parquet: str | Path | pd.DataFrame,
    heatmap_root: str | Path | None,
    report_root: str | Path,
    profile_features: list[str] | None = None,
    column_map: Mapping[str, str | None] | None = None,
    feature_prefixes: Sequence[str] = DEFAULT_FEATURE_PREFIXES,
    target_query: str | None = None,
    control_labels: Sequence[str] = DEFAULT_CONTROL_LABELS,
    negative_control_wells: Mapping[str, str] | None = None,
    control_well_column: int | None = None,
    representative_image_root: str | Path | None = None,
    include_representative_images: bool = True,
    similarity_cutoff: float = 0.85,
    overwrite: bool = True,
    extra_report_fields: Mapping[
        str,
        str | Sequence[str] | Mapping[str, object],
    ] | None = None,
    missing_field_policy: str = "skip",
) -> pd.DataFrame:
    """Generate one self-contained HTML report per target profile and plate.

    Column names are auto-detected from ``COLUMNS`` and can be overridden with
    ``column_map``. Heatmaps and reports are organized as
    ``root / safe_filename(Plate) / safe_filename(Well_Id).extension``.

    When representative images are enabled, ``plate_well`` must resolve to a
    physical well such as ``A01``. Controls can be supplied per plate through
    ``negative_control_wells``. For plates not in that mapping, a control can
    be inferred from the compound row only when ``control_well_column`` is set.
    """
    if not 0 <= similarity_cutoff <= 1:
        raise ValueError("similarity_cutoff must be between 0 and 1.")

    required_fields = list(REQUIRED_REPORT_FIELDS)
    if include_representative_images:
        required_fields.append("plate_well")
        if representative_image_root is None:
            raise ValueError(
                "representative_image_root is required when "
                "include_representative_images=True."
            )

    resolved_columns = resolve_report_columns(
        df,
        column_map=column_map,
        required_fields=required_fields,
    )
    resolved_extra_fields = resolve_extra_report_fields(
        df,
        extra_report_fields=extra_report_fields,
        missing_field_policy=missing_field_policy,
    )
    if resolved_extra_fields and "$Extra_Report_Rows" not in DETAILS_TEMPL:
        raise ValueError(
            "extra_report_fields were provided, but DETAILS_TEMPL does not "
            "contain the $Extra_Report_Rows placeholder. Add it inside the "
            "report details table where the optional rows should appear."
        )
    prepared_df = _prepare_report_dataframe(df, resolved_columns)
    plate_column = _column(prepared_df, "plate", required=True)
    well_column = _column(prepared_df, "well_id", required=True)
    well_type_column = _column(prepared_df, "well_type")

    missing_identifiers = (
        prepared_df[[plate_column, well_column]]
        .isna()
        .any(axis=1)
    )
    if missing_identifiers.any():
        raise ValueError(
            f"{int(missing_identifiers.sum())} rows have a missing Plate or "
            "Well_Id."
        )

    duplicated_profiles = prepared_df.duplicated(
        subset=[plate_column, well_column],
        keep=False,
    )
    if duplicated_profiles.any():
        examples = (
            prepared_df.loc[duplicated_profiles, [plate_column, well_column]]
            .head(10)
            .to_dict(orient="records")
        )
        raise ValueError(
            "Profiles must be unique by Plate + Well_Id. Duplicate examples: "
            f"{examples}"
        )

    required_similarity_columns = {
        "Target_Plate",
        "Similar_Plate",
        "Target_Well_Id",
        "Similar_Well_Id",
        "Biosimilarity",
    }
    if isinstance(similarity_parquet, pd.DataFrame):
        similarity_df = similarity_parquet.copy()
    else:
        similarity_df = pd.read_parquet(similarity_parquet)

    missing_similarity_columns = required_similarity_columns - set(similarity_df.columns)
    if missing_similarity_columns:
        raise KeyError(
            "Similarity parquet is missing columns: "
            f"{sorted(missing_similarity_columns)}"
        )

    if "Rank" not in similarity_df.columns:
        similarity_df = similarity_df.sort_values(
            "Biosimilarity",
            ascending=False,
            kind="stable",
        )
        similarity_df["Rank"] = (
            similarity_df
            .groupby(["Target_Plate", "Target_Well_Id"], sort=False)
            .cumcount()
            .add(1)
        )

    if profile_features is None:
        profile_features = [
            column
            for column in df.columns
            if column.startswith(tuple(feature_prefixes))
        ]
    if not profile_features:
        raise ValueError("No Cell Painting profile features were selected.")
    missing_features = sorted(set(profile_features) - set(df.columns))
    if missing_features:
        raise KeyError(f"Profile features missing from dataframe: {missing_features}")

    heatmap_root = None if heatmap_root is None else Path(heatmap_root)
    report_root = Path(report_root)
    representative_image_root = (
        None
        if representative_image_root is None
        else Path(representative_image_root)
    )
    molecule_cache: dict[str, str] = {}
    records = []

    if target_query is not None:
        try:
            targets = prepared_df.query(target_query).copy()
        except Exception as error:
            raise ValueError(
                f"Could not apply target_query={target_query!r}."
            ) from error
    elif well_type_column is not None:
        normalized_control_labels = {
            str(label).strip().casefold() for label in control_labels
        }
        is_control = (
            prepared_df[well_type_column]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
            .isin(normalized_control_labels)
        )
        targets = prepared_df.loc[~is_control].copy()
    else:
        targets = prepared_df.copy()

    if targets.empty:
        raise ValueError("No target profiles were selected for report generation.")

    control_wells_by_plate = {
        str(plate).strip(): _normalise_well(control_well)
        for plate, control_well in (negative_control_wells or {}).items()
    }

    for plate, plate_df in targets.groupby(plate_column, sort=False):
        plate_output = report_root / safe_filename(plate)
        plate_output.mkdir(parents=True, exist_ok=True)

        for well_id in plate_df[well_column].dropna().astype(str).unique():
            output_path = plate_output / f"{safe_filename(well_id)}.html"
            if output_path.exists() and not overwrite:
                records.append(
                    {"Plate": plate, "Well_Id": well_id, "Report": output_path, "Status": "skipped"}
                )
                continue

            row = _single_profile(prepared_df, plate, well_id)
            similarities = similarity_df.loc[
                similarity_df["Target_Plate"].astype(str).eq(str(plate))
                & similarity_df["Target_Well_Id"].astype(str).eq(well_id)
            ].sort_values("Rank")

            heatmap_path = None
            if heatmap_root is not None:
                heatmap_path = (
                    heatmap_root
                    / safe_filename(plate)
                    / f"{safe_filename(well_id)}.png"
                )

            control_well = None
            if include_representative_images:
                plate_key = str(plate).strip()
                control_well = control_wells_by_plate.get(plate_key)
                if control_well is None:
                    if control_well_column is None:
                        raise KeyError(
                            "No negative-control well was defined for plate "
                            f"{plate_key!r}. Supply negative_control_wells or "
                            "set control_well_column to infer a control in the "
                            "same row as each compound."
                        )
                    control_well = _control_well(
                        _value(row, prepared_df, "plate_well"),
                        control_column=control_well_column,
                    )

            values = _report_values(
                df=prepared_df,
                row=row,
                plate=plate,
                well_id=well_id,
                control_well=control_well,
                similarities=similarities,
                heatmap_path=heatmap_path,
                profile_features=profile_features,
                molecule_cache=molecule_cache,
                current_report_path=output_path,
                report_root=report_root,
                representative_image_root=representative_image_root,
                include_representative_images=include_representative_images,
                similarity_cutoff=similarity_cutoff,
                resolved_extra_fields=resolved_extra_fields,
            )
            body = Template(DETAILS_TEMPL).substitute(values)
            intro = Template(HTML_INTRO).substitute(
                title=f"Cell Painting report - {well_id}"
            )
            output_path.write_text(
                f"{intro}{REPORT_CSS}{body}{HTML_EXTRO}",
                encoding="utf-8",
            )
            records.append(
                {
                    "Plate": plate,
                    "Well_Id": well_id,
                    "Report": output_path.resolve(),
                    "Status": "created",
                    "Similar_Profiles": len(similarities),
                    "Heatmap_Found": bool(
                        heatmap_path is not None and heatmap_path.is_file()
                    ),
                }
            )

    return pd.DataFrame(records)


def _boolean_flag(series):
    """Convert common boolean representations to a boolean series."""
    numeric = pd.to_numeric(series, errors="coerce")

    text = (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
    )

    return (
        numeric.eq(1)
        | text.isin(
            {
                "true",
                "yes",
                "toxic",
                "tox",
            }
        )
    )


def _optional_text_column(frame, column, default=""):
    """Return a text column or a default-valued series."""
    if column is None or column not in frame.columns:
        return pd.Series(
            default,
            index=frame.index,
            dtype="object",
        )

    return (
        frame[column]
        .fillna(default)
        .astype(str)
        .str.strip()
    )


def _optional_numeric_column(frame, column):
    """Return a numeric column or a NaN-valued series."""
    if column is None or column not in frame.columns:
        return pd.Series(
            np.nan,
            index=frame.index,
            dtype=float,
        )

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    )


def generate_plate_pca_previews(
    df,
    report_root,
    plate_column,
    well_id_column,
    induction_column,
    relative_cell_count_column=None,
    cluster_column=None,
    toxicity_column=None,
    compound_id_column=None,
    trivial_name_column=None,
    metadata_well_column=None,
    well_type_column=None,
    profile_features=None,
    active_cutoff=5.0,
    output_name="pca_preview.html",
):
    """Generate one interactive PCA preview for each plate."""
    try:
        import plotly.graph_objects as go
        from plotly.colors import qualitative
        from sklearn.decomposition import PCA
        from sklearn.impute import SimpleImputer
    except ImportError as error:
        raise ImportError(
            "PCA preview generation requires plotly and scikit-learn. The "
            "compound HTML reports can be generated without them."
        ) from error

    report_root = Path(report_root)

    if profile_features is None:
        profile_features = [
            column
            for column in df.columns
            if column.startswith(
                (
                    "Cells_",
                    "Cytoplasm_",
                    "Nuclei_",
                )
            )
        ]

    if not profile_features:
        raise ValueError(
            "No morphological profile features were found."
        )

    # Keep cluster colors consistent between plates.
    all_clusters = _optional_text_column(
        df,
        cluster_column,
    )
    all_clusters = sorted(
        cluster
        for cluster in all_clusters.unique()
        if cluster
    )

    palette = (
        qualitative.Safe
        + qualitative.D3
        + qualitative.Bold
        + qualitative.Set3
    )

    cluster_colors = {
        cluster: palette[index % len(palette)]
        for index, cluster in enumerate(all_clusters)
    }

    manifest = []

    for plate in df[plate_column].dropna().unique():
        plate_frame = df.loc[
            df[plate_column].astype(str).eq(str(plate))
        ].copy()

        # Controls do not have clickable compound reports.
        if (
            well_type_column is not None
            and well_type_column in plate_frame.columns
        ):
            is_control = (
                plate_frame[well_type_column]
                .fillna("")
                .astype(str)
                .str.casefold()
                .eq("control")
            )

            plate_frame = plate_frame.loc[
                ~is_control
            ].copy()

        if len(plate_frame) < 3:
            continue

        induction = _optional_numeric_column(
            plate_frame,
            induction_column,
        ).fillna(0.0)

        plate_frame["_induction"] = induction
        plate_frame["_active"] = induction.ge(active_cutoff)

        if (
            toxicity_column is not None
            and toxicity_column in plate_frame.columns
        ):
            plate_frame["_toxic"] = _boolean_flag(
                plate_frame[toxicity_column]
            )
        else:
            plate_frame["_toxic"] = False

        fit_mask = (
            plate_frame["_active"]
            & ~plate_frame["_toxic"]
        )

        if fit_mask.sum() < 3:
            raise ValueError(
                f"Plate {plate!r} has only {fit_mask.sum()} "
                "active non-toxic compounds available for PCA fitting."
            )

        feature_matrix = (
            plate_frame[profile_features]
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
        )

        fit_feature_matrix = feature_matrix.loc[fit_mask]

        # Features must be usable among the compounds defining the PCA.
        valid_features = [
            column
            for column in fit_feature_matrix.columns
            if (
                fit_feature_matrix[column].notna().any()
                and fit_feature_matrix[column].nunique(
                    dropna=True
                ) > 1
            )
        ]

        if len(valid_features) < 2:
            raise ValueError(
                f"Plate {plate!r} has fewer than two usable "
                "features among active non-toxic compounds."
            )

        feature_matrix = feature_matrix[valid_features]
        fit_feature_matrix = fit_feature_matrix[valid_features]

        # Fit imputation only on compounds used to define the PCA.
        imputer = SimpleImputer(strategy="median")

        fit_matrix = imputer.fit_transform(
            fit_feature_matrix
        )
        matrix = imputer.transform(
            feature_matrix
        )

        pca = PCA(n_components=2)
        pca.fit(fit_matrix)

        # Project every compound onto the PCA defined by active,
        # non-toxic compounds.
        coordinates = pca.transform(matrix)

        plate_frame["PC1"] = coordinates[:, 0]
        plate_frame["PC2"] = coordinates[:, 1]

        clusters = _optional_text_column(
            plate_frame,
            cluster_column,
        )

        plate_frame["_cluster"] = clusters

        if (
            toxicity_column is not None
            and toxicity_column in plate_frame.columns
        ):
            plate_frame["_toxic"] = _boolean_flag(
                plate_frame[toxicity_column]
            )
        else:
            plate_frame["_toxic"] = False

        plate_frame["_display_group"] = np.where(
            ~plate_frame["_active"],
            "Inactive",
            np.where(
                plate_frame["_cluster"].eq(""),
                "Active (unassigned)",
                plate_frame["_cluster"],
            ),
        )

        # Marker area increases with induction but remains bounded.
        maximum_induction = max(
            float(induction.max()),
            active_cutoff,
            1.0,
        )

        plate_frame["_marker_size"] = (
            8
            + 20
            * np.sqrt(
                induction.clip(lower=0)
                / maximum_induction
            )
        )

        compound_ids = _optional_text_column(
            plate_frame,
            compound_id_column,
        )
        trivial_names = _optional_text_column(
            plate_frame,
            trivial_name_column,
        )
        metadata_wells = _optional_text_column(
            plate_frame,
            metadata_well_column,
        )
        cell_counts = _optional_numeric_column(
            plate_frame,
            relative_cell_count_column,
        )

        plate_frame["_compound_id"] = compound_ids
        plate_frame["_trivial_name"] = trivial_names
        plate_frame["_metadata_well"] = metadata_wells
        plate_frame["_cell_count"] = cell_counts

        plate_frame["_report_link"] = (
            plate_frame[well_id_column]
            .astype(str)
            .map(
                lambda value: (
                    f"{safe_filename(value)}.html"
                )
            )
        )

        group_order = [
            "Inactive",
            "Active (unassigned)",
            *all_clusters,
        ]

        group_colors = {
            "Inactive": "#B8C0C8",
            "Active (unassigned)": "#3A7CA5",
            **cluster_colors,
        }

        figure = go.Figure()

        for group in group_order:
            group_frame = plate_frame.loc[
                plate_frame["_display_group"].eq(group)
            ].copy()

            if group_frame.empty:
                continue

            hover_names = group_frame[
                "_trivial_name"
            ].where(
                group_frame["_trivial_name"].ne(""),
                group_frame["_compound_id"],
            )

            customdata = np.column_stack(
                [
                    group_frame["_compound_id"],
                    group_frame[well_id_column].astype(str),
                    group_frame["_metadata_well"],
                    hover_names,
                    group_frame["_induction"].map(
                        lambda value: f"{value:.2f}%"
                    ),
                    group_frame["_cell_count"].map(
                        lambda value: (
                            "n/a"
                            if pd.isna(value)
                            else f"{value:.2f}"
                        )
                    ),
                    group_frame["_cluster"].replace(
                        "",
                        "Unassigned",
                    ),
                    group_frame["_report_link"],
                ]
            )

            figure.add_trace(
                go.Scatter(
                    x=group_frame["PC1"],
                    y=group_frame["PC2"],
                    mode="markers",
                    name=group,
                    customdata=customdata,
                    marker={
                        "size": group_frame[
                            "_marker_size"
                        ],
                        "color": group_colors.get(
                            group,
                            "#3A7CA5",
                        ),
                        "opacity": 0.85,
                        "line": {
                            "color": np.where(
                                group_frame["_toxic"],
                                "#D62828",
                                "#FFFFFF",
                            ),
                            "width": np.where(
                                group_frame["_toxic"],
                                3.0,
                                0.7,
                            ),
                        },
                    },
                    hovertemplate=(
                        "<b>%{customdata[3]}</b><br>"
                        "Compound ID: %{customdata[0]}<br>"
                        "Well ID: %{customdata[1]}<br>"
                        "Plate well: %{customdata[2]}<br>"
                        "Induction: %{customdata[4]}<br>"
                        "Relative cell count: %{customdata[5]}<br>"
                        "U2OS cluster: %{customdata[6]}"
                        "<extra>Click to open report</extra>"
                    ),
                )
            )

        # Add a legend-only toxicity marker.
        figure.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name="Toxic",
                marker={
                    "size": 13,
                    "color": "#FFFFFF",
                    "line": {
                        "color": "#D62828",
                        "width": 3,
                    },
                },
                hoverinfo="skip",
            )
        )

        explained_variance = (
            pca.explained_variance_ratio_ * 100
        )

        figure.update_layout(
            title={
                "text": (
                    f"Phenotypic PCA — {plate}"
                ),
                "x": 0.02,
                "xanchor": "left",
            },
            xaxis_title=(
                f"PC1 ({explained_variance[0]:.1f}%)"
            ),
            yaxis_title=(
                f"PC2 ({explained_variance[1]:.1f}%)"
            ),
            template="plotly_white",
            height=760,
            margin={
                "l": 70,
                "r": 40,
                "t": 90,
                "b": 70,
            },
            legend={
                "title": {
                    "text": "Activity / U2OS cluster"
                },
                "itemsizing": "constant",
            },
            hoverlabel={
                "bgcolor": "white",
                "font_size": 13,
            },
        )

        figure.update_xaxes(
            showgrid=True,
            gridcolor="#E8ECEF",
            zeroline=False,
        )
        figure.update_yaxes(
            showgrid=True,
            gridcolor="#E8ECEF",
            zeroline=False,
            scaleanchor="x",
            scaleratio=1,
        )

        plate_directory = (
            report_root / str(plate)
        )
        plate_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            plate_directory / output_name
        )

        click_script = """
        document.getElementById('{plot_id}').on(
            'plotly_click',
            function(eventData) {
                const point = eventData.points[0];
                const reportLink = point.customdata[7];

                if (reportLink) {
                    window.open(
                        reportLink,
                        '_blank',
                        'noopener,noreferrer'
                    );
                }
            }
        );
        """

        figure.write_html(
            output_path,
            full_html=True,
            include_plotlyjs=True,
            config={
                "displaylogo": False,
                "responsive": True,
            },
            post_script=click_script,
        )

        manifest.append(
            {
                "Plate": plate,
                "PCA_HTML": output_path,
                "Compounds": len(plate_frame),
                "Features": len(valid_features),
                "PC1_Variance_Percent": explained_variance[0],
                "PC2_Variance_Percent": explained_variance[1],
            }
        )

    return pd.DataFrame(manifest)
