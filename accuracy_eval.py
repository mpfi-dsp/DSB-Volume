import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from scipy.stats import skewtest

GROUND_TRUTH_PATH = "data/cell1_roi5_ground_truth_smoothed.csv"
DSB_PATH = "data/cell1_roi5_automatic.csv"


def load_data(gt_path: str, dsb_path: str):
    """Load ground truth and DSB dataframes."""
    gt = pd.read_csv(gt_path)
    dsb = pd.read_csv(dsb_path)
    return gt, dsb


def find_nearest_neighbors(gt_pts: np.ndarray, dsb_pts: np.ndarray):
    """
    For each point in dsb_pts, find the index and distance of the nearest point in gt_pts.
    Returns:
        indices: int array of shape (n_dsb,)
        distances: float array of same shape
    """
    n = dsb_pts.shape[0]
    indices = np.empty(n, dtype=int)
    distances = np.empty(n, dtype=float)

    for i, pt in enumerate(dsb_pts):
        deltas = gt_pts - pt
        dist2 = np.einsum("ij,ij->i", deltas, deltas)
        j = np.argmin(dist2)
        indices[i] = j
        distances[i] = np.sqrt(dist2[j])

    return indices, distances


def merge_ground_truth(gt: pd.DataFrame, dsb: pd.DataFrame, max_dist: float = 500.0):
    """Match each DSB spine to the nearest GT spine and merge volumes/C.O.M., filtering out outliers."""
    # Column names
    dsb_coords = ["Head Centroid X (nm)", "Head Centroid Y (nm)", "Head Centroid Z (nm)"]
    gt_coords = ["com_x", "com_y", "com_z"]

    gt_pts = gt[gt_coords].to_numpy(dtype=float)
    dsb_pts = dsb[dsb_coords].to_numpy(dtype=float)

    idxs, dists = find_nearest_neighbors(gt_pts, dsb_pts)

    # Build merged columns
    merged = dsb.copy()
    merged["GT_name"] = gt.loc[idxs, "name"].values
    merged["GT_volume"] = gt.loc[idxs, "volume"].values
    merged[["GT_com_x", "GT_com_y", "GT_com_z"]] = gt_pts[idxs]
    merged["distance_nm"] = dists

    # Filter out matches farther than threshold
    merged = merged[merged["distance_nm"] < max_dist].reset_index(drop=True)

    # Volume differences
    merged["volume_diff"] = merged["Head Volume (μm³)"] - merged["GT_volume"]
    merged["volume_percent_diff"] = (
        merged["volume_diff"] / merged["Head Volume (μm³)"] * 100
    )

    return merged


def plot_histogram(data: pd.Series, title: str, x_label: str, bins: int = 50, filename=None):
    mean = data.mean()
    median = data.median()
    skew, stat = skewtest(data.to_numpy())

    plt.figure()
    plt.hist(data, bins=bins)
    plt.title(title)
    plt.xlabel(x_label)
    plt.axvline(mean, color="r", linestyle="--", label="Mean")
    plt.axvline(median, color="y", linestyle="--", label="Median")
    plt.text(0.05, 0.95, f"skew = {skew:.2f}\np = {stat:.4f}", transform=plt.gca().transAxes, va="top", fontsize=12)
    ax = plt.gca()  # Get current axes
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))  # Integer y-axis
    plt.ylabel("Count")
    plt.legend()
    if filename is not None:
        plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.show()


def plot_scatter_with_identity(x: pd.Series, y: pd.Series, xlabel: str, ylabel: str, title: str, filename=None):
    plt.figure()
    plt.scatter(x, y, alpha=0.7)
    mn, mx = min(x.min(), y.min()), max(x.max(), y.max())
    plt.plot([mn, mx], [mn, mx], linestyle="--", color="red")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    if filename is not None:
        plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.show()


def plot_bland_altman(title: str, x: pd.Series, y: pd.Series, labels=None, filename=None):
    """
    Creates a Bland–Altman plot comparing x & y.
    If labels is provided, it's a sequence of text labels for each point.
    """
    mean_vals = (x + y) / 2
    diffs = x - y

    mean_diff = np.mean(diffs)
    stdev_diff = np.std(diffs)
    loa_lower = mean_diff - 1.96 * stdev_diff
    loa_upper = mean_diff + 1.96 * stdev_diff

    plt.figure()
    plt.scatter(mean_vals, diffs, alpha=0.7)

    # Annotate points if labels are given
    for i, txt in enumerate(labels):
        plt.text(mean_vals[i], diffs[i], txt, fontsize=6, ha="left", va="bottom")

    plt.axhspan(loa_lower, loa_upper, color="red", alpha=0.1, label="Limits of Agreement")
    plt.axhline(mean_diff, color="black", linestyle="--", label="Mean of Agreement")

    plt.axhline(0, color="gray", label="Zero")
    plt.title(title)
    plt.xlabel("Mean Volume (μm³)")
    plt.ylabel("Volume Difference (DSB - GT) (μm³)")
    plt.legend()
    if filename is not None:
        plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.show()


def main():
    gt_df, dsb_df = load_data(GROUND_TRUTH_PATH, DSB_PATH)
    merged = merge_ground_truth(gt_df, dsb_df)

    automatic = "automatic" in DSB_PATH.lower()
    beheading_type = "Automatic" if automatic else "Semi-Automatic"

    # Histograms
    plot_histogram(
        merged["volume_percent_diff"],
        title=f"Volume % Difference ({beheading_type} DSB vs GT)",
        x_label="Percent Difference (%)",
        filename=f"figs/{beheading_type.lower()}_hist_percent.png",
        bins=15
    )
    plot_histogram(
        merged["volume_diff"],
        title=f"Volume Difference ({beheading_type} DSB – GT) μm³",
        filename=f"figs/{beheading_type.lower()}_hist_diff.png",
        x_label="Difference (μm³)",
        bins=15
    )

    # Scatter DSB vs GT
    plot_scatter_with_identity(
        merged["GT_volume"],
        merged["Head Volume (μm³)"],
        xlabel="Ground Truth Volume (μm³)",
        ylabel="DSB Volume (μm³)",
        filename=f"figs/{beheading_type.lower()}_identity.png",
        title=f"{beheading_type} DSB vs Ground Truth Head Volume"
    )

    # Bland–Altman
    plot_bland_altman(
        f"Bland-Altman Plot of {beheading_type} DSB Accuracy",
        merged["Head Volume (μm³)"],
        merged["GT_volume"],
        filename=f"figs/{beheading_type.lower()}_bland_altman.png",
        labels=[
            # f"{row.GT_name}, idx {row['Head Index']}"
            # for _, row in merged.iterrows()
        ]
    )


if __name__ == "__main__":
    main()
