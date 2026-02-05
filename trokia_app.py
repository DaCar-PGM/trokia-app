import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import re
from serpapi import GoogleSearch
import statistics

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v18.4 : Arbitrage Pro", page_icon="⚖️", layout="wide")

# --- 1. IA EN CASCADE (30 MODÈLES) ---
def analyser_image_multi_cascade(images_pil_list):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        ready_imgs = []
        for img in images_pil_list:
            temp = img.copy()
            temp.thumbnail((800, 800))
            ready_imgs.append(temp)
        
        # Liste exhaustive
        CANDIDATS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        
        for nom in CANDIDATS:
            try:
                model = genai.GenerativeModel(nom if "/" in nom else f"models/{nom}")
                prompt = "Identifie précisément ce produit. Donne 4 suggestions. Format: 1. [Marque Modèle]"
                response = model.generate_content([prompt] + ready_imgs)
                props = [re.sub(r"^[\d\.\-\)\*]+\s*", "", l).strip() for l in response.text.strip().split('\n') if l]
                if props: return props[:4], nom
            except: continue 
        return [], "Erreur IA"
    except Exception as e: return [], str(e)

# --- 2. MOTEUR DE RECHERCHE & AGRÉGATION ---

def get_visual_hint(model_name):
    try:
        params = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google_images", "q": model_name, "num": "1"}
        return GoogleSearch(params).get_dict().get("images_results", [])[0].get("thumbnail")
    except: return None

def scan_google_shopping_world(query):
    try:
        scan_target = query
        if query.isdigit() and len(query) > 8:
            p_ean = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google", "q": query, "gl": "fr"}
            res = GoogleSearch(p_ean).get_dict().get("organic_results", [])
            if res: scan_target = res[0].get("title", "").split(" - ")[0]

        params = {
            "api_key": st.secrets["SERPAPI_KEY"], "engine": "google_shopping",
            "q": scan_target, "google_domain": "google.fr", "gl": "fr", "hl": "fr", "num": "30"
        }
        
        results = GoogleSearch(params).get_dict().get("shopping_results", [])
        
        prices = []; clean_res = []; main_img = ""
        for item in results:
            p_txt = str(item.get("price", "0")).replace("€", "").replace(",", ".").replace("\xa0", "").strip()
            val = float(re.findall(r"(\d+[\.,]?\d*)", p_txt)[0]) if re.findall(r"(\d+[\.,]?\d*)", p_txt) else 0
            link = item.get("link", item.get("product_link", ""))
            source = item.get("source", "Autre")
            
            if val > 5: # On filtre les accessoires à bas prix
                prices.append(val)
                clean_res.append({"source": source, "prix": val, "lien": link, "titre": item.get("title", "")})
            if not main_img: main_img = item.get("thumbnail")
            
        stats = {"min": min(prices) if prices else 0, "max": max(prices) if prices else 0, "med": statistics.median(prices) if prices else 0, "count": len(prices)}
        return stats, clean_res, main_img, scan_target
    except Exception as e:
        return {"count":0, "error": str(e)}, [], "", query

# --- 3. UI ---

def reset_all():
    for key in ['nom_final', 'go_search', 'props', 'current_img', 'scan_results', 'suggestions_data']:
        st.session_state[key] = None if key != 'go_search' else False

if 'nom_final' not in st.session_state: reset_all()

st.title("⚖️ Trokia v18.4 : Arbitrage de Vente")

t_ia, t_man = st.tabs(["📸 SCAN IA", "⌨️ MANUEL / EAN"])

with t_ia:
    files = st.file_uploader("Photos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    if files:
        cv = st.columns(6)
        imgs = [Image.open(f) for f in files]
        for i, img in enumerate(imgs): cv[i%6].image(img, width=100)
        if st.button("🧠 Identifier", use_container_width=True, type="primary"):
            with st.spinner("Analyse..."):
                props, _ = analyser_image_multi_cascade(imgs)
                if props: st.session_state.suggestions_data = [{"name": p, "img": get_visual_hint(p)} for p in props]

    if st.session_state.suggestions_data:
        st.write("---")
        cols_c = st.columns(4)
        for i, item in enumerate(st.session_state.suggestions_data):
            with cols_c[i]:
                if item["img"]: st.image(item["img"], use_container_width=True)
                if st.button(item["name"], key=f"b_{i}", use_container_width=True):
                    st.session_state.nom_final = item["name"]; st.session_state.go_search = True; st.rerun()

with t_man:
    with st.form("m"):
        q = st.text_input("Recherche (ex: iPhone 13 Pro Occasion)")
        if st.form_submit_button("Lancer l'Arbitrage"):
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# --- ANALYSE ET RÉSULTATS ---
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    if not st.session_state.scan_results:
        with st.spinner("📊 Analyse comparative des plateformes..."):
            stats, details, img_ref, nom_reel = scan_google_shopping_world(st.session_state.nom_final)
            st.session_state.scan_results = (stats, details, img_ref, nom_reel)
    
    res = st.session_state.scan_results
    if res and res[0]["count"] > 0:
        stats, details, img_ref, nom_reel = res
        st.header(f"🎯 Analyse : {nom_reel}")
        
        # --- NOUVEAU : BLOC ARBITRAGE PAR PLATEFORME ---
        st.write("### ⚖️ Où vendre au meilleur prix ?")
        df = pd.DataFrame(details)
        # On calcule la moyenne par plateforme
        plateformes = df.groupby("source")["prix"].agg(['mean', 'count']).sort_values(by='mean', ascending=False)
        
        cols_p = st.columns(len(plateformes) if len(plateformes) < 5 else 5)
        for i, (site, row) in enumerate(plateformes.head(5).iterrows()):
            with cols_p[i]:
                st.metric(site, f"{row['mean']:.0f} €", f"{int(row['count'])} offres")
        
        st.write("---")
        
        # --- RECAP GLOBAL ---
        c_i, c_s = st.columns([1, 3])
        if img_ref: c_i.image(img_ref, width=150)
        with c_s:
            k1, k2, k3 = st.columns(3)
            k1.metric("Prix Plancher", f"{stats['min']:.0f} €")
            k2.metric("Prix Marché (Médian)", f"{stats['med']:.0f} €")
            k3.metric("Prix Plafond", f"{stats['max']:.0f} €")

        # --- DÉTAIL DES OFFRES AVEC BOUTON VOIR ---
        st.write("---")
        st.write("##### 🔎 Sources vérifiées (Back Market, eBay, Rakuten...)")
        
        # Tableau scannable
        for i, item in enumerate(details[:15]):
            col_a, col_b, col_c = st.columns([1, 4, 1])
            col_a.write(f"**{item['prix']:.0f} €**")
            col_b.write(f"{item['source']} : *{item['titre'][:60]}...*")
            if item["lien"]:
                col_c.link_button("Voir l'offre", item["lien"])
            else:
                col_c.button("N/A", disabled=True, key=f"na_{i}")
    else:
        st.warning("Aucune donnée disponible pour cette recherche.")
