# 📊 Commandes CLI – Analyse Price Tracker (Newegg)

Ce document regroupe les **commandes CLI simples** pour exécuter les analyses du projet.

---

## 🔹 Analyse par catégorie (commande de base)

```bash
python analysis.py --category GPU
```

Exemples :
```bash
python analysis.py --category SSD
python analysis.py --category Monitor
python analysis.py --category Laptop
```

➡️ Affiche :
- statistiques journalières
- graphique du prix moyen
- top baisses (si disponibles)

---

## 📈 Analyse + sauvegarde du graphique

```bash
python analysis.py --category GPU --out gpu_prices.png
```

Exemples :
```bash
python analysis.py --category SSD --out ssd_prices.png
python analysis.py --category Monitor --out monitor_prices.png
```

➡️ Le graphique est sauvegardé au format PNG.

---

## 📅 Analyse sur une période précise

```bash
python analysis.py --category GPU --start 2026-01-01 --end 2026-01-22
```

➡️ Analyse uniquement les données entre deux dates.

---

## 📉 Top produits avec baisse de prix

```bash
python analysis.py --category GPU --top 10
```

Exemples :
```bash
python analysis.py --category GPU --top 15
python analysis.py --category SSD --top 5
```

➡️ Affiche les produits ayant subi les plus fortes baisses.

---

## 💾 Export des résultats (CSV)

```bash
python analysis.py --category GPU --export
```

➡️ Génère :
- `daily_stats_gpu.csv`
- `top_drops_gpu.csv`

---

## 📦 Export + graphique + top baisses

```bash
python analysis.py --category GPU --out gpu.png --top 10 --export
```

➡️ Commande complète pour présentation finale.

---

## 🔍 Vérifier les catégories disponibles

```bash
python -c "import pandas as pd; df=pd.read_csv('prices_history.csv'); print(df['category'].unique())"
```

---

## 🧠 Résumé pédagogique (à expliquer)

- `--category` : choisir la catégorie analysée (obligatoire)
- `--out` : sauvegarder le graphique
- `--start / --end` : limiter la période d’analyse
- `--top` : nombre de produits avec baisse de prix
- `--export` : exporter les résultats en CSV

---

✅ Ces commandes rendent le projet **reproductible, clair et professionnel**.
