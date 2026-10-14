import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


# --------------------------------------------------
# Default settings
# --------------------------------------------------

DEFAULT_FEATURE_ACTIVITY_CUTOFF = (2**1.58) / 1.4826

DEFAULT_FEATURE_TYPES = (
    "AreaShape",
    "Granularity",
    "Intensity",
    "RadialDistribution",
    "Texture",
)

DEFAULT_CHANNEL_DEFINITIONS = {
    "ER": ("ER",),
    "Hoechst": ("Hoechst",),
    "Mito": ("Mito",),
    "Ph_golgi": ("Ph_golgi",),
    "Syto": ("Syto",),
}

DEFAULT_MORPHOLOGY_PREFIXES = (
    "Cells_",
    "Cytoplasm_",
    "Nuclei_",
)


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def contains_token(feature_name, token):
    """Check whether a complete token occurs in a feature name."""

    padded_feature = f"_{str(feature_name).casefold()}_"
    padded_token = f"_{str(token).casefold()}_"

    return padded_token in padded_feature


def build_feature_catalog(
    df,
    feature_types=DEFAULT_FEATURE_TYPES,
    channel_definitions=DEFAULT_CHANNEL_DEFINITIONS,
    morphology_prefixes=DEFAULT_MORPHOLOGY_PREFIXES,
):
    """Create a catalog assigning each morphological feature to a channel."""

    morphological_features = [
        column
        for column in df.columns
        if column.startswith(morphology_prefixes)
    ]

    if not morphological_features:
        raise ValueError(
            "No morphological features were found in the dataframe."
        )

    feature_catalog = pd.DataFrame(
        {"Feature": morphological_features}
    )

    def identify_feature_type(feature_name):
        matching_types = [
            feature_type
            for feature_type in feature_types
            if contains_token(feature_name, feature_type)
        ]

        if len(matching_types) == 1:
            return matching_types[0]

        return pd.NA

    def identify_channel(row):
        if row["Feature_Type"] == "AreaShape":
            return "AreaShape"

        matching_channels = [
            channel_name
            for channel_name, tokens in channel_definitions.items()
            if any(
                contains_token(row["Feature"], token)
                for token in tokens
            )
        ]

        if len(matching_channels) == 1:
            return matching_channels[0]

        return pd.NA

    feature_catalog["Feature_Type"] = (
        feature_catalog["Feature"]
        .apply(identify_feature_type)
    )

    feature_catalog = (
        feature_catalog
        .dropna(subset=["Feature_Type"])
        .copy()
    )

    feature_catalog["Channel"] = feature_catalog.apply(
        identify_channel,
        axis=1,
    )

    unassigned_features = feature_catalog.loc[
        feature_catalog["Channel"].isna(),
        ["Feature", "Feature_Type"],
    ]

    if not unassigned_features.empty:
        raise ValueError(
            f"{len(unassigned_features)} features could not be assigned "
            "to a channel.\n\n"
            f"{unassigned_features.to_string(index=False)}"
        )

    return feature_catalog


def calculate_changed_channels(
    df,
    well_id,
    feature_catalog,
    channel_order,
    well_column="Well_Id",
    feature_activity_cutoff=DEFAULT_FEATURE_ACTIVITY_CUTOFF,
):
    """Calculate the relative changed-feature contribution by channel."""

    selected_profile = df.loc[
        df[well_column].astype(str).eq(str(well_id))
    ]

    if len(selected_profile) != 1:
        raise ValueError(
            f"Expected exactly one profile for {well_id}, "
            f"but found {len(selected_profile)}."
        )

    feature_details = feature_catalog.copy()

    feature_names = feature_details["Feature"].tolist()

    feature_details["Value"] = pd.to_numeric(
        selected_profile[feature_names].iloc[0],
        errors="coerce",
    ).to_numpy()

    feature_details["Changed"] = (
        feature_details["Value"]
        .abs()
        .gt(feature_activity_cutoff)
    )

    channel_summary = (
        feature_details
        .groupby("Channel", observed=False)
        .agg(
            Total_Features=("Feature", "size"),
            Changed_Features=("Changed", "sum"),
        )
        .reindex(channel_order, fill_value=0)
        .reset_index()
    )

    channel_summary["Changed_Features"] = (
        channel_summary["Changed_Features"].astype(int)
    )

    total_changed = int(
        channel_summary["Changed_Features"].sum()
    )

    if total_changed > 0:
        channel_summary["Changed (Rel) [%]"] = (
            channel_summary["Changed_Features"]
            .div(total_changed)
            .mul(100)
        )
    else:
        channel_summary["Changed (Rel) [%]"] = 0.0

    channel_summary["Well_Id"] = str(well_id)
    feature_details["Well_Id"] = str(well_id)

    return channel_summary, feature_details


# --------------------------------------------------
# Main reusable function
# --------------------------------------------------

def plot_changed_channels_by_well(
    df,
    well_ids,
    well_column="Well_Id",
    feature_activity_cutoff=DEFAULT_FEATURE_ACTIVITY_CUTOFF,
    feature_types=DEFAULT_FEATURE_TYPES,
    channel_definitions=DEFAULT_CHANNEL_DEFINITIONS,
    morphology_prefixes=DEFAULT_MORPHOLOGY_PREFIXES,
    color="#4C78A8",
    common_y_axis=True,
    save=False,
    output_dir="changed_channel_plots",
    show=True,
    dpi=300,
):
    """
    Plot the relative contribution of changed features by channel.

    Parameters
    ----------
    df : pandas.DataFrame
        Dataframe containing metadata and morphological features.
    well_ids : str, int, or iterable
        One Well_Id or a list of Well_Id values.
    well_column : str
        Name of the column containing the well identifier.
    feature_activity_cutoff : float
        Absolute normalized feature value used to define a changed feature.
    color : str
        Bar color.
    common_y_axis : bool
        Use the same y-axis range for all selected wells.
    save : bool
        Save each plot as a PNG file.
    output_dir : str or pathlib.Path
        Directory used when save=True.
    show : bool
        Display plots in the notebook.
    dpi : int
        PNG resolution.

    Returns
    -------
    combined_summary : pandas.DataFrame
        Channel summaries for all selected wells.
    results : dict
        Summary, feature details, figure, axes, and PNG path per well.
    feature_catalog : pandas.DataFrame
        Feature-to-channel assignments.
    """

    if well_column not in df.columns:
        raise KeyError(
            f"Column {well_column!r} was not found in the dataframe."
        )

    if pd.api.types.is_scalar(well_ids):
        well_ids = [well_ids]
    else:
        well_ids = list(well_ids)

    if not well_ids:
        raise ValueError("No Well_Id values were provided.")

    feature_catalog = build_feature_catalog(
        df=df,
        feature_types=feature_types,
        channel_definitions=channel_definitions,
        morphology_prefixes=morphology_prefixes,
    )

    channel_order = [
        "AreaShape",
        *channel_definitions.keys(),
    ]

    calculated_results = {}

    for well_id in well_ids:
        print(well_id)
        channel_summary, feature_details = (
            calculate_changed_channels(
                df=df,
                well_id=well_id,
                feature_catalog=feature_catalog,
                channel_order=channel_order,
                well_column=well_column,
                feature_activity_cutoff=feature_activity_cutoff,
            )
        )

        calculated_results[str(well_id)] = {
            "summary": channel_summary,
            "feature_details": feature_details,
        }

    combined_summary = pd.concat(
        [
            result["summary"]
            for result in calculated_results.values()
        ],
        ignore_index=True,
    )

    if common_y_axis:
        maximum_percentage = combined_summary[
            "Changed (Rel) [%]"
        ].max()

        common_y_limit = max(
            10,
            maximum_percentage * 1.20,
        )
    else:
        common_y_limit = None

    output_path = None

    if save:
        output_path = Path(output_dir)
        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

    sns.set_theme(style="whitegrid")

    for well_id, result in calculated_results.items():
        channel_summary = result["summary"]

        if common_y_limit is None:
            plot_y_limit = max(
                10,
                channel_summary["Changed (Rel) [%]"].max() * 1.20,
            )
        else:
            plot_y_limit = common_y_limit

        fig, ax = plt.subplots(
            figsize=(9, 6),
        )

        sns.barplot(
            data=channel_summary,
            x="Channel",
            y="Changed (Rel) [%]",
            order=channel_order,
            color=color,
            errorbar=None,
            ax=ax,
        )

        for container in ax.containers:
            ax.bar_label(
                container,
                fmt="%.1f%%",
                padding=4,
                fontsize=11,
            )

        total_changed = int(
            channel_summary["Changed_Features"].sum()
        )

        ax.set_title(
            f"Changed channels\n{well_id}",
            fontsize=16,
            fontweight="bold",
        )

        ax.text(
            0.99,
            0.97,
            f"Changed features: {total_changed}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=10,
            color="#444444",
        )

        ax.set_xlabel(
            "Channel",
            fontsize=13,
        )

        ax.set_ylabel(
            "Changed (Rel) [%]",
            fontsize=13,
        )

        ax.set_ylim(
            0,
            plot_y_limit,
        )

        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)

        fig.tight_layout()

        png_path = None

        if save:
            safe_well_id = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "_",
                well_id,
            )

            png_path = (
                output_path
                / f"{safe_well_id}_changed_channels.png"
            )

            fig.savefig(
                png_path,
                dpi=dpi,
                bbox_inches="tight",
            )

        result["figure"] = fig
        result["axes"] = ax
        result["png_path"] = png_path

        if show:
            plt.show()
        else:
            plt.close(fig)

    return combined_summary, calculated_results, feature_catalog