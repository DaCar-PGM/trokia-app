import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
# Si tu n'utilises pas encore gspread / Google Sheets, tu peux commenter ces imports
# import gspread
# from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import re
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import statistics
import random

# =========================
#  CONFIGURATION STREAMLIT
# =========================

st.set_page_config(
    page_title="Trokia v19.0 : Argus & Troc",
    page_icon="💎",
    layout="wide"
)

# Liste de User-Agents pour limiter les blocages
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# =========================
#  1. MOTEUR IA (GEMINI)
# =========================

@st.cache_resource(show_spinner=False)
def obtenir_meilleur_modele():
    """
    Choisit le meilleur modèle Gemini disponible avec generateContent.
    Utilise la clé stockée dans st.secrets["GEMINI_API_KEY"].
    """
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except KeyError:
        st.error("⚠️ GEMINI_API_KEY manquant dans st.secrets.")
        return "gemini-1.5-flash"

    try:
        genai.configure(api_key=api_key)
        models = [
            m.name
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        for candidate in ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]:
            if candidate in models:
                return candidate
        if models:
            return models[0]
        return "gemini-1.5-flash"
    except Exception:
        return "gemini-1.5-flash"


def analyser_objet_expert(image_pil: Image.Image) -> dict:
    """
    Analyse l'image avec Gemini pour extraire :
    - NOM
    - CAT (catégorie)
    - MAT (matériaux)
    Retourne un dict avec des valeurs par défaut en cas de problème.
    """
    default_res = {
        "nom": "Objet Inconnu",
        "cat": "AUTRE",
        "mat": "N/A",
        "etat": "3",
        "score": "5",
    }

    try:
        model_name = obtenir_meilleur_modele()
        model = genai.GenerativeModel(model_name)

        prompt = (
            "En tant qu'expert produits d'occasion, analyse cette image. "
            "Identifie la marque et le modèle exacts si possible. "
            "Sois précis sur les matériaux. "
            "Réponds dans le format STRICT suivant : "
            "NOM: ... | CAT: ... | MAT: ... | ETAT: ... | SCORE: ..."
        )

        response = model.generate_content([prompt, image_pil])
        t = (response.text or "").strip()

        res = default_res.copy()
        if "NOM:" in t:
            res["nom"] = t.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in t:
            res["cat"] = t.split("CAT:")[1].split("|")[0].strip()
        if "MAT:" in t:
            res["mat"] = t.split("MAT:")[1].split("|")[0].strip()
        if "ETAT:" in t:
            res["etat"] = t.split("ETAT:")[1].split("|")[0].strip()
        if "SCORE:" in t:
            res["score"] = t.split("SCORE:")[1].split("|")[0].strip()

        return res
    except Exception as e:
        st.warning(f"⚠️ Analyse image impossible : {str(e)[:80]}")
        return default_res


# =========================
#  2. MOTEUR DE PRIX
# =========================

def clean_price(val_str: str):
    """
    Nettoie une chaîne et renvoie un float ou None.
    Gère '299', '299,00', '299.00', '299 €', etc.
    """
    if not val_str:
        return None

    # Enlève tout sauf les chiffres, les points et les virgules
    val_str = re.sub(r"[^\d,\.]", "", val_str)

    if not val_str:
        return None

    # Unifier virgule en point
    val_str = val_str.replace(",", ".")

    try:
        return float(val_str)
    except ValueError:
        return None


def scan_global_cote(nom: str):
    """
    Cherche des prix de vente pour `nom` :
    - eBay ventes terminées
    - résultats textuels via DuckDuckGo (Leboncoin, Vinted, etc.)
    Retourne (cote_médiane, liquidité_texte, url_ebay).
    """
    prices = []

    try:
        clean_name = re.sub(r"[^\w\s]", " ", nom).strip()
        if not clean_name:
            return 0, "Nom vide", ""

        query = clean_name.replace(" ", "+")
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Connection": "keep-alive",
        }

        # ---------- 2.1 eBay ventes terminées ----------
        url_ebay = (
            "https://www.ebay.fr/sch/i.html"
            f"?_nkw={query}&LH_Sold=1&LH_Complete=1&rt=nc"
        )

        try:
            r = requests.get(url_ebay, headers=headers, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            selectors = [
                ".s-item__price",
                ".s-item__detail--primary span",
                ".s-item__detail span",
            ]

            ebay_prices_raw = []
            for sel in selectors:
                for tag in soup.select(sel):
                    txt = tag.get_text(strip=True)
                    if "€" in txt or "eur" in txt.lower():
                        ebay_prices_raw.append(txt)

            for txt in ebay_prices_raw:
                p = clean_price(txt)
                if p and 1 < p < 10000:
                    prices.append(p)

        except Exception as e:
            st.info(f"ℹ️ eBay non exploitable: {str(e)[:80]}")

        # ---------- 2.2 DuckDuckGo (Leboncoin / Vinted) ----------
        try:
            ddg_query = f"\"{clean_name}\" prix vendu site:leboncoin.fr OR site:vinted.fr"

            ddg_prices_raw = []
            with DDGS() as ddgs:
                for res in ddgs.text(ddg_query, max_results=20):
                    body = (res.get("body") or "").lower()
                    title = (res.get("title") or "").lower()
                    # Regex prix : capte 123, 123.45, 123,45, 1 234,00, etc.
                    pattern = r"(\d{1,4}[\s\.,]?\d{0,2})\s?(?:€|eur|euros?)"
                    matches = re.findall(pattern, body) + re.findall(pattern, title)
                    ddg_prices_raw.extend(matches)

            for txt in ddg_prices_raw:
                p = clean_price(txt)
                if p and 1 < p < 10000:
                    prices.append(p)

        except Exception as e:
            st.info(f"ℹ️ DuckDuckGo non exploitable: {str(e)[:80]}")

        # ---------- 2.3 Calcul de la cote ----------
        if not prices:
            return 0, "Aucune donnée de prix fiable trouvée", url_ebay

        cote = statistics.median(prices)
        nb = len(prices)

        if nb > 20:
            liq = "🔥 Très élevée"
        elif nb > 10:
            liq = "🔥 Élevée"
        elif nb >= 3:
            liq = "Moyenne"
        else:
            liq = "❄️ Faible"

        return round(cote, 2), liq, url_ebay

    except Exception as e:
        return 0, f"Erreur globale: {str(e)[:80]}", ""


def get_thumbnail(query: str) -> str:
    """
    Récupère une miniature via DuckDuckGo Images.
    Fallback: placeholder.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(keywords=query, region="fr-fr", max_results=1))
            if results:
                return results[0].get("image", "https://via.placeholder.com/150")
            return "https://via.placeholder.com/150"
    except Exception:
        return "https://via.placeholder.com/150"


# =========================
#  3. GESTION D'ÉTAT
# =========================

if "objet_a" not in st.session_state:
    st.session_state.objet_a = None

if "last_scan" not in st.session_state:
    st.session_state.last_scan = None


def reset_all():
    st.session_state.objet_a = None
    st.session_state.last_scan = None
    st.rerun()


# =========================
#  4. INTERFACE STREAMLIT
# =========================

st.title("💎 Trokia : L'Argus Universel")

if st.button("🔄 Remise à zéro complète", use_container_width=True):
    reset_all()

tab_photo, tab_manuel, tab_troc = st.tabs(
    ["📸 Scan Photo", "⌨️ Clavier / EAN", "⚖️ Balance d'Échange"]
)

# ---------- Onglet 1 : Scan Photo ----------
with tab_photo:
    col_l, col_r = st.columns([1, 2])

    with col_l:
        f = st.camera_input("Scanner un produit")
        if not f:
            f = st.file_uploader("Ou importer une image", type=["jpg", "jpeg", "png"])

    if f is not None:
        with st.spinner("Analyse de l'image et recherche de prix..."):
            image_pil = Image.open(f)
            data = analyser_objet_expert(image_pil)
            cote, liq, url_ebay = scan_global_cote(data["nom"])
            thumb = get_thumbnail(data["nom"])

            st.session_state.last_scan = {
                "nom": data["nom"],
                "prix": cote,
                "img": thumb,
                "mat": data["mat"],
            }

        with col_r:
            st.header(data["nom"])
            st.write(f"Catégorie : {data['cat']} | Matériaux : {data['mat']}")
            st.write(f"État (IA) : {data['etat']} / 5 | Score : {data['score']} / 5")

            if cote > 0:
                st.metric("Valeur estimée", f"{cote:.0f} €", delta=f"Liquidité : {liq}")
                st.caption(f"Source principale : eBay ventes terminées. URL : {url_ebay}")
            else:
                st.error("⚠️ Impossible d'estimer un prix fiable avec les sources actuelles.")

            if st.button("⚖️ Ajouter au TROC (Slot A)", key="add_photo"):
                st.session_state.objet_a = st.session_state.last_scan
                st.success("✅ Objet ajouté comme référence pour le troc (Slot A).")

# ---------- Onglet 2 : Saisie manuelle ----------
with tab_manuel:
    with st.form("manual_form"):
        q_in = st.text_input(
            "Saisir nom ou Code-Barre",
            placeholder="Ex: iPhone 11 64 Go",
        )
        btn_search = st.form_submit_button("🔎 Estimer la valeur")

    if btn_search and q_in:
        with st.spinner("Recherche de prix sur le web..."):
            cote, liq, url_ebay = scan_global_cote(q_in)
            img = get_thumbnail(q_in)

            st.session_state.last_scan = {
                "nom": q_in,
                "prix": cote,
                "img": img,
                "mat": "Manuel",
            }

        c1, c2 = st.columns([1, 2])
        c1.image(img, width=150)
        with c2:
            st.subheader(q_in)
            if cote > 0:
                st.metric("Valeur marché", f"{cote:.0f} €", delta=liq)
                st.caption(f"Source principale : eBay + autres sites. URL eBay : {url_ebay}")
            else:
                st.error("Aucun prix exploitable trouvé pour cette recherche.")

            if st.button("⚖️ Ajouter au TROC (Slot A)", key="add_manual"):
                st.session_state.objet_a = st.session_state.last_scan
                st.success("✅ Objet mémorisé comme Slot A.")

# ---------- Onglet 3 : Balance d'Échange ----------
with tab_troc:
    if st.session_state.objet_a:
        obj_a = st.session_state.objet_a

        col_a, col_vs, col_b = st.columns([2, 1, 2])

        with col_a:
            st.image(obj_a["img"], width=150)
            st.subheader(obj_a["nom"])
            st.title(f"{obj_a['prix']:.0f} €")

        with col_vs:
            st.title("🆚")

        with col_b:
            if (
                st.session_state.last_scan
                and st.session_state.last_scan["nom"] != obj_a["nom"]
            ):
                obj_b = st.session_state.last_scan
                st.image(obj_b["img"], width=150)
                st.subheader(obj_b["nom"])
                st.title(f"{obj_b['prix']:.0f} €")

                diff = obj_a["prix"] - obj_b["prix"]

                if diff > 0:
                    st.error(f"L'autre doit rajouter {abs(diff):.0f} € pour un troc équitable.")
                elif diff < 0:
                    st.success(f"Vous avez un avantage de {abs(diff):.0f} € dans cet échange.")
                else:
                    st.info("Échange parfaitement équitable.")
            else:
                st.write("Scannez ou estimez un second objet pour compléter la comparaison.")
    else:
        st.info("Aucun objet dans le Slot A. Ajoutez-en un via l'onglet Photo ou Clavier.")
