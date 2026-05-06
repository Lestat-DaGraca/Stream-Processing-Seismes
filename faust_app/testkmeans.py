"""
Benchmark K-Means — trois axes :

1. VITESSE vs N_CLUSTERS (2 → 100)
   KMeans sklearn complet sur tout le CSV pour chaque k.

2. STREAMING : ajout séisme par séisme
   - KMeans complet recalculé à chaque ajout (sklearn)
   - KMeans incrémental custom (kmeans.py)
   Pour chaque ajout :
     • temps d'exécution des deux algos
     • % de déplacement des centroïdes vs itération précédente
     • ARI entre les deux algos (est-ce qu'ils donnent les mêmes clusters ?)

3. JUSTIFICATION DES SEUILS
   Grille tiny × big → ARI moyen + speedup moyen
   Pour choisir empiriquement THRESHOLD_TINY_MOVE et THRESHOLD_BIG_MOVE.
"""

import os
import sys
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from kmeans import (
    do_full_clustering,
    incremental_kmeans_update,
    kmeans_state,
    KMeansState,
)
import kmeans as kmeans_module


def load_csv(csv_path: str) -> tuple[np.ndarray, list[dict]]:
    """Charge le CSV et retourne coords numpy + liste de dicts pour ton algo."""
    df = pd.read_csv(csv_path).dropna(subset=["latitude", "longitude", "mag"])
    coords = df[["latitude", "longitude"]].values
    earthquakes = [
        {
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "magnitude": float(row["mag"]),
            "place": str(row.get("place", f"quake_{i}")),
        }
        for i, row in df.iterrows()
    ]
    return coords, earthquakes


def centroid_drift_pct(prev: np.ndarray, curr: np.ndarray) -> float:
    """
    % de déplacement moyen des centroïdes entre deux itérations.
    Normalisé par la distance médiane centroïde → barycentre (pour être interprétable).
    Retourne nan si les shapes diffèrent.
    """
    if prev is None or curr is None or prev.shape != curr.shape:
        return float("nan")
    dists = np.linalg.norm(curr - prev, axis=1)
    ref = np.median(np.linalg.norm(prev - prev.mean(axis=0), axis=1))
    if ref < 1e-10:
        return 0.0
    return round(float(np.mean(dists) / ref) * 100, 3)


def reset_custom_state(n_clusters: int):
    """Réinitialise l'état global de ton algo entre deux runs."""
    kmeans_state.centroids = None
    kmeans_state.assignments = []
    kmeans_state.n_clusters = n_clusters
    kmeans_state.last_full_clustering = None
    kmeans_state.earthquakes_snapshot = []



def benchmark_speed_vs_k(csv_path: str, k_min: int = 2, k_max: int = 100, n_init: int = 10) -> pd.DataFrame:
    """
    Mesure le temps sklearn KMeans sur le CSV entier pour chaque k.
    """
    print("=" * 60)
    print(f"PARTIE 1 — Vitesse vs n_clusters ({k_min} → {k_max})")
    print("=" * 60)

    coords, _ = load_csv(csv_path)
    print(f"   Dataset : {len(coords)} points\n")

    results = []
    for k in range(k_min, k_max + 1):
        if k > len(coords):
            break
        start = time.perf_counter()
        km = KMeans(n_clusters=k, n_init=n_init, random_state=42)
        km.fit(coords)
        elapsed = time.perf_counter() - start

        results.append({
            "k": k,
            "execution_time_sec": round(elapsed, 4),
            "inertia": round(km.inertia_, 2),
            "n_iter": km.n_iter_,
        })
        print(f"   k={k:3d} | {elapsed:.4f}s | inertie={km.inertia_:.1f} | iters={km.n_iter_}")

    return pd.DataFrame(results)


def plot_speed_vs_k(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))
    fig.suptitle("KMeans — Vitesse & qualité selon n_clusters (2→100)", fontsize=13, fontweight="bold")

    axes[0].plot(df["k"], df["execution_time_sec"], color="steelblue", linewidth=1.5)
    axes[0].set_xlabel("n_clusters (k)")
    axes[0].set_ylabel("Temps (sec)")
    axes[0].set_title("Temps d'exécution")
    axes[0].grid(alpha=0.3)

    axes[1].plot(df["k"], df["inertia"], color="tomato", linewidth=1.5)
    axes[1].set_xlabel("n_clusters (k)")
    axes[1].set_ylabel("Inertie")
    axes[1].set_title("Méthode du coude (k optimal)")
    axes[1].grid(alpha=0.3)

    axes[2].plot(df["k"], df["n_iter"], color="mediumseagreen", linewidth=1.5)
    axes[2].set_xlabel("n_clusters (k)")
    axes[2].set_ylabel("Itérations")
    axes[2].set_title("Nb d'itérations jusqu'à convergence")
    axes[2].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("kmeans_speed_vs_k.png", dpi=150)
    plt.show()
    print("📊 kmeans_speed_vs_k.png sauvegardé")



def benchmark_streaming(
    csv_path: str,
    n_clusters: int = 5,
    warm_up: int = 50,
    n_init_full: int = 5,
) -> pd.DataFrame:
    """
    Simule l'arrivée des séismes un par un après warm_up points d'initialisation.

    À chaque ajout on mesure :
      - temps KMeans complet sklearn
      - temps algo incrémental custom
      - drift % centroïdes (avant/après) pour chacun
      - ARI entre les labels des deux algos (concordance)
    """
    print("=" * 60)
    print(f"PARTIE 2 — Streaming (k={n_clusters}, warm_up={warm_up})")
    print("=" * 60)

    coords, earthquakes = load_csv(csv_path)
    n_total = len(coords)

    if warm_up >= n_total:
        raise ValueError(f"warm_up ({warm_up}) doit être < nb de points ({n_total})")

    print(f"   Dataset : {n_total} points | streaming de {warm_up} → {n_total}\n")


    # sklearn
    km_full = KMeans(n_clusters=n_clusters, n_init=n_init_full, random_state=42)
    km_full.fit(coords[:warm_up])
    prev_centers_full = km_full.cluster_centers_.copy()

    # custom : on force un clustering complet initial via do_full_clustering
    reset_custom_state(n_clusters)
    do_full_clustering(earthquakes[:warm_up], k=n_clusters)
    prev_centers_inc = kmeans_state.centroids.copy()

    records = []

    for i in range(warm_up, n_total):
        new_eq = earthquakes[i]
        batch = coords[: i + 1]

        t0 = time.perf_counter()
        km_full = KMeans(n_clusters=n_clusters, n_init=n_init_full, random_state=42)
        km_full.fit(batch)
        time_full = time.perf_counter() - t0

        centers_full = km_full.cluster_centers_
        labels_full  = km_full.labels_

        t0 = time.perf_counter()
        update_info = incremental_kmeans_update(new_eq)
        time_inc = time.perf_counter() - t0

        centers_inc = kmeans_state.centroids.copy()
        labels_inc  = np.array(kmeans_state.assignments)

        drift_full = centroid_drift_pct(prev_centers_full, centers_full)
        drift_inc  = centroid_drift_pct(prev_centers_inc,  centers_inc)

        min_len = min(len(labels_full), len(labels_inc))
        ari = adjusted_rand_score(labels_full[:min_len], labels_inc[:min_len])

        propagation = update_info["propagation_type"] if update_info else "none"
        shift_raw   = update_info["centroid_shift"]   if update_info else 0.0

        records.append({
            "n_points":           i + 1,
            "time_full_sec":      round(time_full, 5),
            "time_inc_sec":       round(time_inc,  5),
            "drift_full_pct":     drift_full,
            "drift_inc_pct":      drift_inc,
            "ari":                round(ari, 4),
            "propagation_type":   propagation,
            "centroid_shift_raw": round(shift_raw, 4),
        })

        prev_centers_full = centers_full.copy()
        prev_centers_inc  = centers_inc.copy()

        if (i - warm_up) % 200 == 0 or i == warm_up:
            print(
                f"   +{i+1:5d} pts | "
                f"full={time_full:.4f}s  inc={time_inc:.5f}s | "
                f"drift_full={drift_full:.1f}%  drift_inc={drift_inc:.1f}% | "
                f"ARI={ari:.3f} | prop={propagation}"
            )

    return pd.DataFrame(records)


def plot_streaming(df: pd.DataFrame, n_clusters: int):
    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(
        f"Streaming KMeans (k={n_clusters}) — Recalcul complet vs Incrémental custom",
        fontsize=13, fontweight="bold",
    )
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.5, wspace=0.35)
    x = df["n_points"]

    # 1. Temps d'exécution
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(x, df["time_full_sec"], label="Recalcul complet", color="steelblue", linewidth=1)
    ax1.plot(x, df["time_inc_sec"],  label="Incrémental custom", color="tomato",  linewidth=1)
    ax1.set_xlabel("Nb séismes vus")
    ax1.set_ylabel("Temps (sec)")
    ax1.set_title("Temps d'exécution par ajout")
    ax1.legend()
    ax1.grid(alpha=0.3)

    # 2. Speedup
    ax2 = fig.add_subplot(gs[0, 1])
    speedup = df["time_full_sec"] / df["time_inc_sec"].replace(0, np.nan)
    ax2.plot(x, speedup, color="mediumseagreen", linewidth=1)
    ax2.axhline(1, linestyle="--", color="gray", linewidth=0.8, label="x1 (égalité)")
    ax2.set_xlabel("Nb séismes vus")
    ax2.set_ylabel("Speedup (x fois)")
    ax2.set_title("Accélération incrémental vs complet")
    ax2.legend()
    ax2.grid(alpha=0.3)

    # 3. Drift des centroïdes
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.plot(x, df["drift_full_pct"], label="Recalcul complet", color="steelblue", linewidth=1)
    ax3.plot(x, df["drift_inc_pct"],  label="Incrémental custom", color="tomato",  linewidth=1)
    ax3.set_xlabel("Nb séismes vus")
    ax3.set_ylabel("Déplacement (%)")
    ax3.set_title("% déplacement des centroïdes à chaque ajout")
    ax3.legend()
    ax3.grid(alpha=0.3)

    # 4. ARI
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.plot(x, df["ari"], color="darkorchid", linewidth=1)
    ax4.axhline(1.0, linestyle="--", color="gray",   linewidth=0.8, label="ARI=1 (identiques)")
    ax4.axhline(0.8, linestyle=":",  color="orange",  linewidth=0.8, label="ARI=0.8 (seuil bon)")
    ax4.set_ylim(-0.1, 1.05)
    ax4.set_xlabel("Nb séismes vus")
    ax4.set_ylabel("ARI")
    ax4.set_title("Concordance des clusters entre les deux algos\n(ARI proche de 1 = clusters identiques)")
    ax4.legend()
    ax4.grid(alpha=0.3)

    # 5. Type de propagation
    ax5 = fig.add_subplot(gs[2, 0])
    prop_map = {"none": 0, "cluster_only": 1, "full_propagation": 2}
    prop_numeric = df["propagation_type"].map(prop_map).fillna(-1)
    colors_prop = prop_numeric.map({0: "lightgray", 1: "steelblue", 2: "tomato"})
    ax5.bar(x, prop_numeric, color=colors_prop, width=1)
    ax5.set_yticks([0, 1, 2])
    ax5.set_yticklabels(["none", "cluster_only", "full_propagation"])
    ax5.set_xlabel("Nb séismes vus")
    ax5.set_title("Type de propagation déclenché (algo custom)")
    ax5.grid(alpha=0.3, axis="x")

    # 6. Shift brut centroïde
    ax6 = fig.add_subplot(gs[2, 1])
    ax6.plot(x, df["centroid_shift_raw"], color="darkorange", linewidth=1)
    ax6.axhline(kmeans_module.THRESHOLD_TINY_MOVE, linestyle="--", color="lightgray",
                linewidth=0.8, label=f"seuil tiny ({kmeans_module.THRESHOLD_TINY_MOVE})")
    ax6.axhline(kmeans_module.THRESHOLD_BIG_MOVE,  linestyle="--", color="tomato",
                linewidth=0.8, label=f"seuil big ({kmeans_module.THRESHOLD_BIG_MOVE})")
    ax6.set_xlabel("Nb séismes vus")
    ax6.set_ylabel("Shift ratio")
    ax6.set_title("Shift brut centroïde (distance/norme)\navec seuils de propagation")
    ax6.legend()
    ax6.grid(alpha=0.3)

    plt.savefig("kmeans_streaming.png", dpi=150)
    plt.show()
    print("📊 kmeans_streaming.png sauvegardé")


def print_streaming_summary(df: pd.DataFrame):
    print("\n=== RÉSUMÉ STREAMING ===")
    print(f"  Points streamés          : {df['n_points'].min()} → {df['n_points'].max()}")
    print(f"  Temps moyen complet      : {df['time_full_sec'].mean():.4f}s")
    print(f"  Temps moyen incrémental  : {df['time_inc_sec'].mean():.5f}s")
    speedup = df["time_full_sec"].mean() / df["time_inc_sec"].replace(0, np.nan).mean()
    print(f"  Speedup moyen            : x{speedup:.1f}")
    print(f"  Drift moyen complet      : {df['drift_full_pct'].mean():.2f}%")
    print(f"  Drift moyen incrémental  : {df['drift_inc_pct'].mean():.2f}%")
    print(f"  ARI moyen                : {df['ari'].mean():.3f}")
    print(f"  ARI médian               : {df['ari'].median():.3f}")
    pct_close = (df["ari"] > 0.8).mean() * 100
    print(f"  % ajouts avec ARI > 0.8  : {pct_close:.1f}%  (clusters quasi-identiques)")

    prop_counts = df["propagation_type"].value_counts(normalize=True) * 100
    print("\n  Répartition propagations (algo custom) :")
    for p, pct in prop_counts.items():
        print(f"    {p:20s} : {pct:.1f}%")



def benchmark_thresholds(
    csv_path: str,
    n_clusters: int = 5,
    warm_up: int = 50,
    n_init_full: int = 5,
    tiny_values: list = None,
    big_values:  list = None,
) -> pd.DataFrame:
    """
    Pour chaque combinaison (THRESHOLD_TINY_MOVE, THRESHOLD_BIG_MOVE) :
      - rejoue le streaming complet
      - calcule ARI moyen, speedup moyen, répartition des propagations
    Permet de choisir les seuils de façon empirique.
    """
    if tiny_values is None:
        tiny_values = [0.001, 0.005, 0.01, 0.02, 0.05, 0.10]
    if big_values is None:
        big_values  = [0.05, 0.10, 0.20, 0.30, 0.50]

    # Sauvegarder les seuils d'origine pour les restaurer à la fin
    original_tiny = kmeans_module.THRESHOLD_TINY_MOVE
    original_big  = kmeans_module.THRESHOLD_BIG_MOVE

    print("=" * 60)
    print("PARTIE 3 — Justification des seuils (grille tiny × big)")
    print(f"           {len(tiny_values)} valeurs tiny × {len(big_values)} valeurs big")
    print("=" * 60)

    coords, earthquakes = load_csv(csv_path)
    n_total = len(coords)

    results = []

    for tiny in tiny_values:
        for big in big_values:
            if big <= tiny:
                continue
            kmeans_module.THRESHOLD_TINY_MOVE = tiny
            kmeans_module.THRESHOLD_BIG_MOVE  = big
            reset_custom_state(n_clusters)
            do_full_clustering(earthquakes[:warm_up], k=n_clusters)

            aris       = []
            times_inc  = []
            times_full = []
            prop_counts = {"none": 0, "cluster_only": 0, "full_propagation": 0}

            for i in range(warm_up, n_total):
                new_eq = earthquakes[i]
                batch  = coords[: i + 1]


                t0 = time.perf_counter()
                km_full = KMeans(n_clusters=n_clusters, n_init=n_init_full, random_state=42)
                km_full.fit(batch)
                times_full.append(time.perf_counter() - t0)
                labels_full = km_full.labels_

                t0 = time.perf_counter()
                info = incremental_kmeans_update(new_eq)
                times_inc.append(time.perf_counter() - t0)

                labels_inc = np.array(kmeans_state.assignments)
                min_len    = min(len(labels_full), len(labels_inc))
                aris.append(adjusted_rand_score(labels_full[:min_len], labels_inc[:min_len]))

                prop = info["propagation_type"] if info else "none"
                prop_counts[prop] = prop_counts.get(prop, 0) + 1

            n_steps     = n_total - warm_up
            avg_ari     = round(float(np.mean(aris)), 4)
            avg_speedup = round(
                float(np.mean(times_full)) / max(float(np.mean(times_inc)), 1e-9), 2
            )
            pct_none    = round(prop_counts["none"]             / n_steps * 100, 1)
            pct_cluster = round(prop_counts["cluster_only"]     / n_steps * 100, 1)
            pct_full    = round(prop_counts["full_propagation"] / n_steps * 100, 1)

            results.append({
                "tiny":         tiny,
                "big":          big,
                "ari_mean":     avg_ari,
                "speedup_mean": avg_speedup,
                "pct_none":     pct_none,
                "pct_cluster":  pct_cluster,
                "pct_full":     pct_full,
            })

            print(
                f"   tiny={tiny:.3f}  big={big:.2f} | "
                f"ARI={avg_ari:.3f}  speedup=x{avg_speedup:.1f} | "
                f"none={pct_none}%  cluster={pct_cluster}%  full={pct_full}%"
            )

    kmeans_module.THRESHOLD_TINY_MOVE = original_tiny
    kmeans_module.THRESHOLD_BIG_MOVE  = original_big

    return pd.DataFrame(results)


def plot_thresholds(df: pd.DataFrame):
    """
    3 graphes :
      1. ARI moyen en fonction de tiny (une courbe par valeur de big)
      2. Speedup moyen en fonction de tiny
      3. Heatmap ARI (tiny × big)
    """
    big_vals  = sorted(df["big"].unique())
    tiny_vals = sorted(df["tiny"].unique())
    colors    = plt.cm.tab10(np.linspace(0, 1, len(big_vals)))

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        "Justification des seuils — Impact sur ARI et vitesse",
        fontsize=13, fontweight="bold"
    )


    ax = axes[0]
    for color, big in zip(colors, big_vals):
        sub = df[df["big"] == big].sort_values("tiny")
        ax.plot(sub["tiny"], sub["ari_mean"], marker="o", label=f"big={big}",
                color=color, linewidth=1.5)
    ax.axhline(0.90, linestyle="--", color="orange", linewidth=0.8, label="ARI=0.90")
    ax.axhline(0.95, linestyle="--", color="green",  linewidth=0.8, label="ARI=0.95")
    ax.set_xlabel("THRESHOLD_TINY_MOVE")
    ax.set_ylabel("ARI moyen")
    ax.set_title("ARI moyen vs seuil tiny\n(une courbe par seuil big)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)


    ax = axes[1]
    for color, big in zip(colors, big_vals):
        sub = df[df["big"] == big].sort_values("tiny")
        ax.plot(sub["tiny"], sub["speedup_mean"], marker="o", label=f"big={big}",
                color=color, linewidth=1.5)
    ax.axhline(1, linestyle="--", color="gray", linewidth=0.8, label="x1 (égalité)")
    ax.set_xlabel("THRESHOLD_TINY_MOVE")
    ax.set_ylabel("Speedup moyen (x fois)")
    ax.set_title("Speedup vs seuil tiny\n(plus haut = incrémental plus rapide)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    ax = axes[2]
    pivot = df.pivot(index="big", columns="tiny", values="ari_mean")
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=0.7, vmax=1.0)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([str(v) for v in pivot.columns], fontsize=7, rotation=45)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(v) for v in pivot.index], fontsize=7)
    ax.set_xlabel("THRESHOLD_TINY_MOVE")
    ax.set_ylabel("THRESHOLD_BIG_MOVE")
    ax.set_title("Heatmap ARI moyen\n(vert = proche sklearn, rouge = diverge)")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=6,
                        color="black" if val > 0.85 else "white")

    plt.tight_layout()
    plt.savefig("kmeans_thresholds.png", dpi=150)
    plt.show()
    print("📊 kmeans_thresholds.png sauvegardé")


def print_threshold_recommendation(df: pd.DataFrame):
    print("\n=== RECOMMANDATION SEUILS ===")

    best_ari = df.loc[df["ari_mean"].idxmax()]
    print(f"  Meilleur ARI             : tiny={best_ari['tiny']}  big={best_ari['big']} "
          f"→ ARI={best_ari['ari_mean']}  speedup=x{best_ari['speedup_mean']}")

    good = df[df["ari_mean"] >= 0.90]
    if not good.empty:
        best_tradeoff = good.loc[good["speedup_mean"].idxmax()]
        print(f"  Meilleur compromis       : tiny={best_tradeoff['tiny']}  big={best_tradeoff['big']} "
              f"→ ARI={best_tradeoff['ari_mean']}  speedup=x{best_tradeoff['speedup_mean']}")
    else:
        print("  Aucune combinaison n'atteint ARI≥0.90 — recalcul périodique recommandé.")

if __name__ == "__main__":

    CSV_PATH = "../producers/data/all_month.csv"
    K_STREAM = 5    # k utilisé pour les benchmarks streaming et seuils
    WARM_UP  = 50   # nb de points pour initialiser les deux algos


    df_speed = benchmark_speed_vs_k(CSV_PATH, k_min=2, k_max=100)
    plot_speed_vs_k(df_speed)
    df_speed.to_csv("results_speed_vs_k.csv", index=False)
    print("💾 results_speed_vs_k.csv sauvegardé\n")


    df_stream = benchmark_streaming(CSV_PATH, n_clusters=K_STREAM, warm_up=WARM_UP)
    print_streaming_summary(df_stream)
    plot_streaming(df_stream, n_clusters=K_STREAM)
    df_stream.to_csv("results_streaming.csv", index=False)
    print("💾 results_streaming.csv sauvegardé\n")


    df_thresh = benchmark_thresholds(
        CSV_PATH,
        n_clusters=K_STREAM,
        warm_up=WARM_UP,
        tiny_values=[0.001, 0.005, 0.01, 0.02, 0.05, 0.10],
        big_values =[0.05,  0.10,  0.20, 0.30, 0.50],
    )
    print_threshold_recommendation(df_thresh)
    plot_thresholds(df_thresh)
    df_thresh.to_csv("results_thresholds.csv", index=False)
    print("💾 results_thresholds.csv sauvegardé")