# =========================
# 1) IMPORTS
# =========================

import time                      # Permet de faire des pauses entre les requêtes (anti-blocage)
import re                        # Permet d'utiliser des expressions régulières (nettoyage du prix)
import random                    # Permet de générer une pause aléatoire (plus naturel)
import os                        # Permet de vérifier si un fichier existe (historique CSV)
from datetime import datetime, timezone  # Permet de générer une date/heure en UTC (stable)

import requests                  # Librairie HTTP pour télécharger les pages web
import pandas as pd              # Librairie pour manipuler des tableaux (DataFrame) et CSV
from bs4 import BeautifulSoup    # Librairie pour parser le HTML
from requests.adapters import HTTPAdapter  # Pour brancher un système de retries (ré-essais)
from urllib3.util.retry import Retry       # Politique de retries sur erreurs (429, 503...)

# =========================
# 2) CONFIGURATION
# =========================

# En-têtes HTTP : simuler un vrai navigateur pour éviter un blocage simple
HEADERS = {
    "User-Agent": (                               # User-Agent = "identité" de ton navigateur
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",          # Langue demandée (peut influencer la page)
}

# Dictionnaire de catégories à tracker : nom -> URL de recherche Newegg
BASE_URLS = {
    "Monitor": "https://www.newegg.com/p/pl?d=monitor",         # URL base pour les écrans
    "GPU": "https://www.newegg.com/p/pl?d=graphics+card",       # URL base pour les cartes graphiques
    "SSD": "https://www.newegg.com/p/pl?d=ssd",                 # URL base pour les SSD
    "Laptop": "https://www.newegg.com/p/pl?d=laptop",           # URL base pour les laptops
}

# Si tu veux tracker une seule catégorie : écris ex "GPU"
# Si tu veux tracker toutes les catégories : laisse None
CATEGORY_TO_TRACK = None

MAX_PAGES = 20                   # Nombre max de pages à scraper par catégorie

HISTORY_CSV = "prices_history.csv"  # Nom du fichier historique (où on "append" chaque jour)

# Pause aléatoire entre pages (anti anti-bot / anti blocage)
SLEEP_MIN = 1.5                  # Minimum de pause
SLEEP_MAX = 3.0                  # Maximum de pause

# =========================
# 3) OUTILS (UTILS)
# =========================

def build_session() -> requests.Session:
    """Crée une session HTTP avec retries pour éviter l'échec en cas d'erreurs temporaires."""
    session = requests.Session()                 # Une Session réutilise la connexion (plus stable)

    # Définir la politique de ré-essais (retries)
    retries = Retry(
        total=4,                                 # Nombre total de retries max
        backoff_factor=1.0,                      # Attente progressive: 1s, 2s, 4s...
        status_forcelist=(429, 500, 502, 503, 504),  # Codes HTTP qui déclenchent retry
        allowed_methods=("GET",),                # On autorise les retries seulement sur GET
        raise_on_status=False,                   # Ne pas lever exception automatiquement sur status !=200
    )

    adapter = HTTPAdapter(max_retries=retries)   # Adapter = module qui applique retries à requests
    session.mount("https://", adapter)           # Appliquer l'adapter aux URLs https
    session.mount("http://", adapter)            # Appliquer l'adapter aux URLs http
    return session                               # Retourner la session prête


def extract_brand(item) -> str:
    """Essaye d'extraire la marque dans la zone 'item-features' (si existante)."""
    features = item.find("ul", class_="item-features")  # Cherche <ul class="item-features">
    if not features:                                    # Si la liste n’existe pas
        return "Unknown"                                # On ne sait pas la marque

    for li in features.find_all("li"):                  # Parcourt chaque <li>
        txt = li.get_text(" ", strip=True)              # Récupère le texte propre
        if "Brand:" in txt:                             # Si la ligne contient Brand:
            return txt.replace("Brand:", "").strip()    # On nettoie et retourne
    return "Unknown"                                    # Si rien trouvé


def parse_price_float(item) -> float | None:
    """
    Extrait le prix Newegg (souvent format: <strong>199</strong><sup>.99</sup>)
    puis convertit en float.
    """
    price_tag = item.find("li", class_="price-current")  # Cherche la zone de prix
    if not price_tag:                                    # Si pas de prix affiché
        return None                                      # On retourne None

    strong = price_tag.find("strong")                    # Partie entière (ex: 199)
    sup = price_tag.find("sup")                          # Partie décimale (ex: .99)

    if not strong:                                       # Si strong absent
        return None                                      # Impossible d’extraire le prix

    whole = strong.get_text(strip=True).replace(",", "") # Nettoyer la partie entière (enlever virgules)
    frac = ""                                            # Valeur par défaut de la partie décimale

    if sup:                                              # Si la partie décimale existe
        frac = sup.get_text(strip=True)                  # Exemple: ".99"

    price_str = whole + frac                             # Concat: "199" + ".99" => "199.99"
    price_str = price_str.replace("$", "").strip()       # Enlève "$" si présent

    price_str = re.sub(r"[^0-9.]", "", price_str)        # Garder uniquement chiffres et point

    try:
        return float(price_str)                          # Convertir en float
    except ValueError:
        return None                                      # Si conversion impossible


def parse_rating(item) -> tuple[float | None, int | None]:
    """Retourne (rating_avg, rating_count) si disponibles."""
    rating_avg = None                                    # Note moyenne (ex 4.5)
    rating_count = None                                  # Nombre d'avis (ex 123)

    rating_num_tag = item.find("span", class_="item-rating-num")  # Cherche "(123)"
    if rating_num_tag:
        raw = rating_num_tag.get_text(strip=True)        # Texte brut, ex "(123)"
        raw = raw.replace("(", "").replace(")", "").strip()  # Nettoyage => "123"
        if raw.isdigit():                                # Vérifie si c'est bien un nombre
            rating_count = int(raw)                      # Convertit en int

    rating_avg_tag = item.find("i", class_="rating")     # Cherche icône rating
    if rating_avg_tag and rating_avg_tag.has_attr("aria-label"):
        aria = rating_avg_tag["aria-label"]              # Ex: "Rated 4.5 out of 5 eggs"
        m = re.search(r"rated\s+([0-9.]+)\s+out of 5", aria, re.I)  # Regex pour trouver 4.5
        if m:
            try:
                rating_avg = float(m.group(1))           # Convertit "4.5" en float
            except ValueError:
                rating_avg = None                        # Si conversion échoue

    return rating_avg, rating_count                       # Retourner le tuple


def parse_availability(item) -> str:
    """
    Déduit la disponibilité via heuristique:
    - si texte contient 'sold out' => Out of stock
    - si bouton 'Add to cart' => In stock
    - sinon Unknown
    """
    text = item.get_text(" ", strip=True).lower()         # Texte complet de l’item en minuscule

    if "sold out" in text or "out of stock" in text:      # Indices d'indisponibilité
        return "Out of stock"

    btn = item.find("a", class_=re.compile(r"btn", re.I))  # Cherche un bouton (classe contenant 'btn')
    if btn:
        btn_txt = btn.get_text(" ", strip=True).lower()   # Texte du bouton
        if "add to cart" in btn_txt:                      # Si bouton d'achat existe
            return "In stock"

    return "Unknown"                                      # Sinon pas sûr


def now_iso() -> str:
    """Retourne date/heure ISO en UTC (pour historiser les collectes)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")  # ISO : 2026-01-22T...


# =========================
# 4) SCRAPER PRINCIPAL
# =========================

def scrape_category(session: requests.Session, category: str, base_url: str, max_pages: int) -> list[dict]:
    """
    Scrape une catégorie sur plusieurs pages.
    Retourne une liste de dictionnaires (chaque dict = 1 produit au moment de la collecte).
    """
    rows = []                                             # Liste résultat (produits)
    scrape_dt = now_iso()                                 # Date/heure unique pour cette collecte (toutes pages)

    print(f"\n🔎 Catégorie : {category}")                  # Message console

    for page in range(1, max_pages + 1):                  # Boucle pages 1..max_pages
        url = f"{base_url}&page={page}"                   # Construction URL avec paramètre page
        print(f"📄 Page {page}/{max_pages} -> {url}")      # Affichage URL

        try:
            r = session.get(url, headers=HEADERS, timeout=12)  # Téléchargement page
        except requests.RequestException as e:                 # Erreur réseau
            print(f"⛔ Erreur réseau: {e}")                    # Affiche erreur
            break                                              # Stop catégorie

        if r.status_code != 200:                               # Si réponse pas OK
            print(f"⛔ HTTP {r.status_code} (stop catégorie)")  # Affiche code
            break                                              # Stop

        soup = BeautifulSoup(r.text, "html.parser")            # Parse HTML
        items = soup.find_all("div", class_="item-cell")       # Chaque produit est souvent dans item-cell

        if not items:                                          # Si aucun produit trouvé
            print("🚫 Plus de produits sur cette page (stop catégorie).")
            break                                              # Stop

        print(f"➡️ {len(items)} produits détectés")            # Nombre de produits trouvés

        for idx, item in enumerate(items, start=1):            # Parcours produits avec index
            try:
                # ----- Nom + URL (identifiant stable) -----
                title_tag = item.find("a", class_="item-title")  # Lien du produit
                product_name = title_tag.get_text(strip=True) if title_tag else "Unknown"  # Titre
                product_url = title_tag["href"].strip() if title_tag and title_tag.has_attr("href") else None  # URL

                # Rank (position globale dans la catégorie à ce moment)
                rank = (page - 1) * len(items) + idx            # Calcul rang

                # ----- Prix en float -----
                price_value = parse_price_float(item)           # Extrait prix

                # ----- Rating -----
                rating_avg, rating_count = parse_rating(item)   # Extrait note + nb avis

                # ----- Marque -----
                brand = extract_brand(item)                     # Extrait brand

                # ----- Disponibilité -----
                availability = parse_availability(item)          # Déduit stock

                # Ajouter une ligne (dict) au dataset
                rows.append({
                    "category": category,                       # Nom catégorie
                    "scrape_datetime_utc": scrape_dt,           # Date/heure de collecte (UTC)
                    "page": page,                               # Page où on a trouvé le produit
                    "rank": rank,                               # Rang dans la catégorie
                    "product_name": product_name,               # Nom produit
                    "product_url": product_url,                 # URL (clé stable)
                    "brand": brand,                             # Marque
                    "price_value": price_value,                 # Prix float
                    "rating_avg": rating_avg,                   # Note moyenne
                    "rating_count": rating_count,               # Nb avis
                    "availability": availability,               # Stock
                })

            except Exception as e:
                print("⚠️ Erreur produit :", e)                 # Si une extraction plante, on continue

        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))        # Pause aléatoire anti-blocage

    return rows                                                 # Retourne toutes les lignes de la catégorie


# =========================
# 5) HISTORIQUE (APPEND CSV)
# =========================

def load_history(csv_path: str) -> pd.DataFrame:
    """Charge l'historique si le fichier existe, sinon DataFrame vide."""
    if os.path.exists(csv_path):                                # Vérifie l'existence du fichier
        return pd.read_csv(csv_path, encoding="utf-8-sig")      # Lit le CSV en DataFrame
    return pd.DataFrame()                                       # Sinon retourne vide


def save_history_append(csv_path: str, df_new: pd.DataFrame) -> pd.DataFrame:
    """
    Sauvegarde en mode tracker:
    - on APPEND (concat historique + nouvelles lignes)
    - on dédoublonne seulement sur (product_url, scrape_datetime_utc)
      pour éviter doublons exacts sans casser l'historique.
    """
    df_hist = load_history(csv_path)                            # Charge historique existant

    if df_hist.empty:                                           # Si pas d’historique
        df_out = df_new.copy()                                  # On prend juste le nouveau
    else:
        df_out = pd.concat([df_hist, df_new], ignore_index=True) # Sinon concat historique + nouveau

    # Dédoublonnage tracker (ne supprime pas les jours différents)
    if "product_url" in df_out.columns and "scrape_datetime_utc" in df_out.columns:
        df_out.drop_duplicates(                                 # Enlève uniquement doublons exacts
            subset=["product_url", "scrape_datetime_utc"],
            keep="last",
            inplace=True
        )

    df_out.to_csv(csv_path, index=False, encoding="utf-8-sig")  # Écrit le CSV final
    return df_out                                               # Retourne le DataFrame final


# =========================
# 6) POINT D'ENTRÉE
# =========================

if __name__ == "__main__":                                      # Exécuté seulement si on lance ce fichier
    session = build_session()                                   # Crée session HTTP robuste

    targets = BASE_URLS                                         # Par défaut, on track toutes catégories
    if CATEGORY_TO_TRACK:                                       # Si l'utilisateur a choisi une catégorie
        if CATEGORY_TO_TRACK not in BASE_URLS:                  # Vérifie catégorie valide
            raise ValueError(
                f"CATEGORY_TO_TRACK invalide. Choisis parmi: {list(BASE_URLS.keys())}"
            )
        targets = {CATEGORY_TO_TRACK: BASE_URLS[CATEGORY_TO_TRACK]}  # Ne tracker que cette catégorie

    all_rows = []                                               # Contiendra toutes les lignes (toutes catégories)
    for cat, url in targets.items():                            # Parcours des catégories ciblées
        all_rows.extend(scrape_category(session, cat, url, MAX_PAGES))  # Scrape + ajoute

    df_new = pd.DataFrame(all_rows)                             # Convertit en DataFrame pandas

    if df_new.empty:                                            # Si aucun produit scrapé
        print("\n⚠️ Aucun produit scrapé. Rien à sauvegarder.")
        raise SystemExit(0)                                     # Stop

    df_hist = save_history_append(HISTORY_CSV, df_new)           # Append dans l'historique CSV

    print(f"\n✅ Nouvelle collecte: {len(df_new)} lignes")       # Résumé console
    print(f"📦 Historique total: {len(df_hist)} lignes dans '{HISTORY_CSV}'")
