import argparse
import os
from datetime import date

import pandas as pd
import matplotlib.pyplot as plt


DEFAULT_CSV = "prices_history.csv"


# ---------------------------
# Helpers: nettoyage/robustesse
# ---------------------------

def _require_columns(df: pd.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans le CSV: {sorted(missing)}")


def load_and_clean(csv_path: str) -> pd.DataFrame:
    """
    Charge prices_history.csv et nettoie:
      - dates -> datetime UTC
      - prix -> numeric
      - url / nom -> non vides
      - colonnes dérivées: scrape_date (jour), has_price, has_url
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Fichier introuvable: {csv_path}")

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    required = {"category", "scrape_datetime_utc", "product_url", "product_name", "price_value"}
    _require_columns(df, required)

    # Date/heure UTC
    df["scrape_datetime_utc"] = pd.to_datetime(df["scrape_datetime_utc"], errors="coerce", utc=True)

    # Date (jour) dérivée
    df["scrape_date"] = df["scrape_datetime_utc"].dt.date

    # Prix: numeric
    df["price_value"] = pd.to_numeric(df["price_value"], errors="coerce")

    # Rating: numeric (si colonnes présentes)
    if "rating_avg" in df.columns:
        df["rating_avg"] = pd.to_numeric(df["rating_avg"], errors="coerce")
    if "rating_count" in df.columns:
        df["rating_count"] = pd.to_numeric(df["rating_count"], errors="coerce")

    # Normaliser champs texte (évite NaN qui casse certaines opérations)
    for col in ["product_url", "product_name", "brand", "availability", "category"]:
        if col in df.columns:
            df[col] = df[col].astype("string").fillna("").str.strip()

    # Flags utiles
    df["has_url"] = df["product_url"].str.len() > 0
    df["has_price"] = df["price_value"].notna() & (df["price_value"] > 0)

    # Supprimer les lignes inutilisables pour le tracking (pas de date ou pas d'URL)
    df = df.dropna(subset=["scrape_datetime_utc", "scrape_date"])
    df = df[df["has_url"]]

    # Garder le prix si valide (sinon on ne peut pas analyser les prix)
    df = df[df["has_price"]]

    # (Option) dédoublonnage strict exact: même produit_url même timestamp -> garder last
    df = df.sort_values(["product_url", "scrape_datetime_utc"])
    df = df.drop_duplicates(subset=["product_url", "scrape_datetime_utc"], keep="last")

    return df


def available_categories(df: pd.DataFrame) -> list[str]:
    cats = sorted([c for c in df["category"].unique().tolist() if c])
    return cats


def filter_df(df: pd.DataFrame, category: str, start: str | None, end: str | None) -> pd.DataFrame:
    d = df[df["category"] == category].copy()

    if d.empty:
        raise ValueError(f"Aucune donnée pour la catégorie '{category}'. Catégories dispo: {available_categories(df)}")

    if start:
        start_d = pd.to_datetime(start).date()
        d = d[d["scrape_date"] >= start_d]

    if end:
        end_d = pd.to_datetime(end).date()
        d = d[d["scrape_date"] <= end_d]

    if d.empty:
        raise ValueError("Aucune donnée après filtrage par dates.")

    return d


# ---------------------------
# Stats journalières
# ---------------------------

def compute_daily_stats(d: pd.DataFrame) -> pd.DataFrame:
    """
    Stats par jour pour une catégorie:
      - avg, median, min, max
      - nombre de produits distincts
      - nombre d'observations
      - moyenne mobile 7 jours (sur avg)
    """
    daily = (
        d.groupby("scrape_date")
         .agg(
            avg_price=("price_value", "mean"),
            median_price=("price_value", "median"),
            min_price=("price_value", "min"),
            max_price=("price_value", "max"),
            products_count=("product_url", "nunique"),
            observations=("price_value", "count"),
         )
         .reset_index()
         .sort_values("scrape_date")
    )

    daily["avg_price_ma7"] = daily["avg_price"].rolling(window=7, min_periods=1).mean()
    return daily


def plot_daily(daily: pd.DataFrame, category: str, out_png: str | None) -> None:
    x = pd.to_datetime(daily["scrape_date"])

    plt.figure()
    plt.plot(x, daily["avg_price"], label="Prix moyen (jour)")
    plt.plot(x, daily["avg_price_ma7"], label="Moyenne mobile 7 jours")
    plt.title(f"Prix moyen — {category}")
    plt.xlabel("Date")
    plt.ylabel("Prix")
    plt.legend()
    plt.xticks(rotation=30)
    plt.tight_layout()

    if out_png:
        plt.savefig(out_png, dpi=160)
        print(f"✅ Graphique sauvegardé: {out_png}")
    else:
        plt.show()


# ---------------------------
# Top baisses (produits)
# ---------------------------

def compute_top_drops(d: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Calcule les plus fortes baisses entre la 1ère et la dernière observation de chaque produit_url
    dans la période filtrée.
    Si on n'a qu'une seule date de collecte, retourne vide (normal).
    """
    if d["scrape_date"].nunique() < 2:
        return pd.DataFrame(columns=[
            "product_name", "product_url",
            "scrape_date_first", "price_first",
            "scrape_date_last", "price_last",
            "drop_abs", "drop_pct"
        ])

    # Trier pour prendre first/last correctement
    d = d.sort_values(["product_url", "scrape_datetime_utc"])

    first = (
        d.groupby("product_url", as_index=False)
         .first()[["product_url", "product_name", "scrape_date", "price_value"]]
         .rename(columns={
            "scrape_date": "scrape_date_first",
            "price_value": "price_first",
         })
    )

    last = (
        d.groupby("product_url", as_index=False)
         .last()[["product_url", "scrape_date", "price_value"]]
         .rename(columns={
            "scrape_date": "scrape_date_last",
            "price_value": "price_last",
         })
    )

    merged = first.merge(last, on="product_url", how="inner")

    merged["drop_abs"] = merged["price_first"] - merged["price_last"]
    merged["drop_pct"] = (merged["drop_abs"] / merged["price_first"]) * 100

    out = merged[[
        "product_name",
        "product_url",
        "scrape_date_first",
        "price_first",
        "scrape_date_last",
        "price_last",
        "drop_abs",
        "drop_pct",
    ]].copy()

    # Garder uniquement les baisses strictes
    out = out[out["drop_abs"] > 0].sort_values("drop_pct", ascending=False).head(top_n)

    return out


# ---------------------------
# Main CLI
# ---------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyse Price Tracker (Newegg) à partir de prices_history.csv")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Chemin vers prices_history.csv")
    parser.add_argument("--category", required=True, help="Catégorie (ex: GPU, SSD, Monitor, Laptop)")
    parser.add_argument("--start", default=None, help="Date début (YYYY-MM-DD) optionnelle")
    parser.add_argument("--end", default=None, help="Date fin (YYYY-MM-DD) optionnelle")
    parser.add_argument("--top", type=int, default=10, help="Top N baisses")
    parser.add_argument("--out", default=None, help="Nom PNG pour sauvegarder le graphe (sinon affiche)")

    # Exports (optionnels)
    parser.add_argument("--export", action="store_true", help="Exporter daily_stats et top_drops en CSV")

    args = parser.parse_args()

    df = load_and_clean(args.csv)
    d = filter_df(df, args.category, args.start, args.end)

    # 1) Stats journalières
    daily = compute_daily_stats(d)
    print("\n=== Statistiques journalières (aperçu) ===")
    print(daily.tail(15).to_string(index=False))

    # 2) Graphique
    plot_daily(daily, args.category, args.out)

    # 3) Top baisses
    drops = compute_top_drops(d, top_n=args.top)
    print("\n=== Top baisses (produits) ===")
    if drops.empty:
        print("Aucune baisse détectée (souvent normal si tu n'as qu'une seule date de collecte).")
    else:
        print(drops.to_string(index=False))

    # 4) Exports
    if args.export:
        safe_cat = args.category.lower().replace(" ", "_")
        daily_out = f"daily_stats_{safe_cat}.csv"
        drops_out = f"top_drops_{safe_cat}.csv"

        daily.to_csv(daily_out, index=False, encoding="utf-8-sig")
        drops.to_csv(drops_out, index=False, encoding="utf-8-sig")

        print(f"\n✅ Export OK: {daily_out}")
        print(f"✅ Export OK: {drops_out}")


if __name__ == "__main__":
    main()
