import time
import csv
import re
import random
import os
from datetime import datetime
import requests
import pandas as pd
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9"
}

# Nouvelles catégories avec moins de valeurs manquantes
BASE_URLS = {
    "Monitor": "https://www.newegg.com/p/pl?d=monitor",
    "GPU": "https://www.newegg.com/p/pl?d=graphics+card",
    "SSD": "https://www.newegg.com/p/pl?d=ssd",
    "Laptop": "https://www.newegg.com/p/pl?d=laptop"
}

MAX_PAGES = 20
CSV_FILE = "newegg_products.csv"
results = []

# =========================
# FONCTION POUR EXTRAIRE LA MARQUE
# =========================
def extract_brand(item):
    features = item.find("ul", class_="item-features")
    if not features:
        return "Unknown"
    for li in features.find_all("li"):
        if "Brand:" in li.get_text():
            return li.get_text().replace("Brand:", "").strip()
    return "Unknown"

# =========================
# CHARGER LES DONNÉES EXISTANTES (SI PRÉSENTES)
# =========================
if os.path.exists(CSV_FILE):
    df_existing = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    print(f"📂 {len(df_existing)} produits existants trouvés dans '{CSV_FILE}'")
else:
    df_existing = pd.DataFrame()
    print(f"📂 Aucun fichier existant trouvé. Nouveau fichier sera créé.")

# =========================
# SCRAPING
# =========================
for category, base_url in BASE_URLS.items():
    print(f"\n🔎 Catégorie : {category}")

    for page in range(1, MAX_PAGES + 1):
        url = f"{base_url}&page={page}"
        print(f"📄 Page {page}/{MAX_PAGES}")

        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print("⛔ Erreur HTTP", response.status_code)
            break

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.find_all("div", class_="item-cell")

        if not items:
            print("🚫 Plus de produits sur cette page")
            break

        print(f"➡️ {len(items)} produits détectés")

        for item in items:
            try:
                # ----- Nom du produit -----
                title_tag = item.find("a", class_="item-title")
                name = title_tag.get_text(strip=True) if title_tag else "Unknown"

                # ----- Prix -----
                price_tag = item.find("li", class_="price-current")
                if price_tag:
                    strong = price_tag.find("strong")
                    sup = price_tag.find("sup")
                    if strong and sup:
                        price = strong.get_text() + sup.get_text()
                    else:
                        price = None
                else:
                    price = None

                # ----- Rating -----
                # Nombre de votes
                rating_num_tag = item.find("span", class_="item-rating-num")
                rating_count = rating_num_tag.get_text(strip=True).replace("(", "").replace(")", "") if rating_num_tag else None

                # Note moyenne
                rating_avg_tag = item.find("i", class_="rating")
                rating_avg = None
                if rating_avg_tag and rating_avg_tag.has_attr("aria-label"):
                    match = re.search(r"rated ([0-9.]+) out of 5", rating_avg_tag["aria-label"])
                    if match:
                        rating_avg = float(match.group(1))

                # ----- Brand -----
                brand = extract_brand(item)

                # ----- Ajout au résultat -----
                results.append({
                    "category": category,
                    "product_name": name,
                    "brand": brand,
                    "price": price,
                    "rating_avg": rating_avg,
                    "rating_count": rating_count,
                    "scrape_date": datetime.now().strftime("%Y-%m-%d")
                })

            except Exception as e:
                print("⚠️ Erreur produit :", e)

        # Pause aléatoire pour éviter d'être bloqué
        time.sleep(random.uniform(1.5, 3))

# =========================
# COMBINER AVEC LES DONNÉES EXISTANTES
# =========================
df_new = pd.DataFrame(results)

if not df_existing.empty:
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
else:
    df_combined = df_new

# =========================
# SUPPRIMER LES DUPLIQUÉS
# =========================
df_combined.drop_duplicates(subset=["category", "product_name", "brand", "price"], keep="last", inplace=True)

# =========================
# EXPORT CSV
# =========================
df_combined.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
print(f"\n🎉 Terminé ! {len(df_combined)} produits sauvegardés dans '{CSV_FILE}'")
# =========================
# FIN DU SCRIPT
# =========================
