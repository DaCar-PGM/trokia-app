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
st.set_page_config(page_title="Trokia v18.0 : Galerie de Choix", page_icon="🖼️", layout="wide")

# --- 1. FONCTION DE RECHERCHE D'IMAGE (Pour les suggestions) ---

def get_visual_hint(model_name):
    """
    Va chercher une image miniature pour aider l'utilisateur à choisir le bon modèle.
    """
    try:
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_images",
            "q": model_name,
            "num": "1" # On ne prend que la première image
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        images = results.get("images_results", [])
        if images:
            return images[0].get("thumbnail")
    except:
        return None
    return None

# --- 2. L'IA EN CASCADE (Multi-Vues) ---

def analyser_image_multi_cascade(images_pil_list):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        CANDIDATS = [
            "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"
        ]
        
        for nom in CANDIDATS:
            try:
                model = genai.GenerativeModel(nom)
                prompt = "Identifie ce produit. Donne 4 modèles précis. Format: 1. [Marque Modèle] 2. [Marque Modèle]..."
                response = model.generate_content([prompt] + images_pil_list)
                text = response.text.strip()
                
                propositions = []
                for l in text.split('\n'):
                    if l and (l[0].isdigit() or l.startswith("-")):
                        propositions.append(re.sub(r"^[\d\.\-\)\*]+\s*", "", l).strip())
                
                if propositions:
                    return propositions[:4], nom
            except:
                continue 
        return [], None
    except:
        return [], None

# --- 3. MOTEUR DE PRIX (SerpApi) ---

def scan_google_shopping_world(query):
    try:
        # Si c'est un EAN, on l'identifie d'abord
        scan_target = query
        if query.isdigit() and len(query) > 8:
            params_ean = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google", "q": query}
            res_ean = GoogleSearch(params_ean).get_dict().get("organic_results", [])
            if res_ean: scan_target = res_ean[0].get("title", "").split(" - ")[0]

        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_shopping",
            "q": scan_target,
            "google_domain": "google.fr",
            "num": "15"
        }
        results = GoogleSearch(params).get_dict().get("shopping_results", [])
        
        prices = []
        clean_res = []
        main_img = ""
        for item in results:
            p_txt = str(item.get("price", "0")).replace("€", "").replace(",", ".").replace("\xa0", "").strip()
            val = float(re.findall(r"(\d+[\.,]?\d*)", p_txt)[0]) if re.findall(r"(\d+[\.,]?\d*)", p_txt) else 0
            if val > 1:
                prices.append(val)
                clean_res.append({"source": item.get("source", "Web"), "prix": val, "lien": item.get("link", ""), "titre": item.get("title", "")})
            if not main_img: main_img = item.get("thumbnail")
            
        stats = {"min": min(prices) if prices else 0, "max": max(prices) if prices else 0, "med": statistics.median(prices) if prices else 0, "count": len(prices)}
        return stats, clean_res, main_img, scan_target
    except:
        return {"count":0}, [], "", query

# --- UI STREAMLIT ---

def reset_all():
    for key in ['nom_final', 'go_search', 'props', 'current_img', 'scan_results', 'suggestions_data']:
        st.session_state[key] = None if key != 'go_search' else False

if 'nom_final' not in st.session_state: reset_all()

st.title("🖼️ Trokia v18.0 : Galerie de Choix")

t_ia, t_man = st.tabs(["📸 SCAN IA MULTI-VUES", "⌨️ RECHERCHE"])

with t_ia:
    files = st.file_uploader("Photos (Vignettes)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    
    if files:
        # AFFICHAGE EN VIGNETTES
        cols_vignettes = st.columns(len(files) if len(files) < 6 else 6)
        imgs_pil = []
        for idx, f in enumerate(files):
            img = Image.open(f)
            imgs_pil.append(img)
            cols_vignettes[idx % 6].image(img, width=120) # TAILLE VIGNETTE
        
        if st.button("🧠 Identifier le modèle", use_container_width=True, type="primary"):
            with st.spinner("L'IA analyse les angles..."):
                props, model_used = analyser_image_multi_cascade(imgs_pil)
                if props:
                    # ENRICHISSEMENT VISUEL DES PROPOSITIONS
                    enriched = []
                    for p in props:
                        enriched.append({"name": p, "img": get_visual_hint(p)})
                    st.session_state.suggestions_data = enriched
                    st.toast(f"Modèle {model_used} activé")
                else:
                    st.error("L'IA n'a pas pu identifier l'objet.")

    # AFFICHAGE DES CARTES DE CHOIX AVEC IMAGES
    if st.session_state.suggestions_data:
        st.write("---")
        st.write("##### 🎯 Quel est votre modèle ?")
        cols_choice = st.columns(4)
        for i, item in enumerate(st.session_state.suggestions_data):
            with cols_choice[i]:
                if item["img"]:
                    st.image(item["img"], use_container_width=True)
                else:
                    st.info("Pas d'aperçu")
                
                if st.button(item["name"], key=f"btn_{i}", use_container_width=True):
                    st.session_state.nom_final = item["name"]
                    st.session_state.go_search = True
                    st.rerun()

with t_man:
    with st.form("m"):
        q = st.text_input("Saisie manuelle")
        if st.form_submit_button("Scanner"):
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# RÉSULTATS DU SCAN
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    with st.spinner(f"Scan mondial pour : {st.session_state.nom_final}..."):
        stats, details, img_ref, nom_reel = scan_google_shopping_world(st.session_state.nom_final)
    
    if stats["count"] > 0:
        st.header(f"🎯 {nom_reel}")
        c_i, c_s = st.columns([1, 3])
        if img_ref: c_i.image(img_ref, width=200)
        with c_s:
            k1, k2, k3 = st.columns(3)
            k1.metric("Prix Bas", f"{stats['min']:.0f} €")
            k2.metric("Cote Médiane", f"{stats['med']:.0f} €", f"{stats['count']} offres")
            k3.metric("Prix Haut", f"{stats['max']:.0f} €")
        
        st.write("---")
        cols_offres = st.columns(5)
        for i, item in enumerate(details[:10]):
            with cols_offres[i%5]:
                st.metric(item["source"], f"{item['prix']:.0f} €")
                st.caption(item["titre"][:30])
                if item["lien"]: st.link_button("Voir", item["lien"])
                st.divider()
    else:
        st.warning("Aucune offre trouvée.")
