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
st.set_page_config(page_title="Trokia v18.2 : Full Cascade", page_icon="🚀", layout="wide")

# --- 1. FONCTIONS IA AVEC TOUS LES MODÈLES (30 CANDIDATS) ---

def optimiser_image(image_pil):
    """Réduit la taille de l'image pour l'envoi API"""
    img = image_pil.copy()
    img.thumbnail((800, 800))
    return img

def get_visual_hint(model_name):
    """Récupère une image de référence pour aider au choix"""
    try:
        params = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google_images", "q": model_name, "num": "1"}
        search = GoogleSearch(params)
        images = search.get_dict().get("images_results", [])
        return images[0].get("thumbnail") if images else None
    except: return None

def analyser_image_multi_cascade(images_pil_list):
    """
    Tente l'analyse sur la TOTALITÉ des modèles disponibles.
    Ordre optimisé : du plus récent/puissant au plus stable.
    """
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        ready_images = [optimiser_image(img) for img in images_pil_list]
        
        # TA LISTE COMPLÈTE DE 30 MODÈLES (Cibles multimodales prioritaires)
        CANDIDATS = [
            # Les "Tops" récents
            "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro-preview", 
            "gemini-3-flash-preview", "gemini-2.0-flash", "gemini-2.0-flash-001",
            "gemini-exp-1206", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite",
            "gemini-3-pro-image-preview", "gemini-2.5-flash-image",
            
            # Les versions stables / standards
            "gemini-1.5-flash", "gemini-1.5-pro", "gemini-flash-latest", 
            "gemini-pro-latest", "gemini-1.5-flash-001", "gemini-1.5-flash-002",
            
            # Les versions de secours (Lite / Anciennes)
            "gemini-flash-lite-latest", "gemini-2.5-flash-lite-preview-09-2025",
            "gemini-1.0-pro", "gemini-pro", "gemini-pro-vision",
            
            # Les spécialisés (Dernier recours)
            "gemini-2.5-computer-use-preview-10-2025", "deep-research-pro-preview-12-2025",
            "gemini-robotics-er-1.5-preview", "nano-banana-pro-preview"
        ]
        
        last_error = ""
        for nom in CANDIDATS:
            try:
                # Si le nom ne commence pas par models/, on l'ajoute (Streamlit/API check)
                model_id = nom if "/" in nom else f"models/{nom}"
                model = genai.GenerativeModel(model_id)
                
                prompt = """Expert en identification. Analyse ces angles de vue. 
                Donne moi 4 suggestions de modèles précis. 
                Format : 
                1. [Marque] [Modèle]
                2. [Marque] [Modèle]..."""
                
                response = model.generate_content([prompt] + ready_images)
                text = response.text.strip()
                
                props = []
                for l in text.split('\n'):
                    if l and (l[0].isdigit() or l.startswith("-")):
                        p = re.sub(r"^[\d\.\-\)\*]+\s*", "", l).strip()
                        if len(p) > 3: props.append(p)
                
                if props:
                    st.toast(f"✅ Modèle utilisé : {nom}")
                    return props[:4], nom
            except Exception as e:
                last_error = str(e)
                continue 
        return [], last_error
    except Exception as e: return [], str(e)

# --- 2. MOTEUR DE PRIX (SERPAPI) ---

def scan_google_shopping_world(query):
    try:
        scan_target = query
        # Traduction EAN si nécessaire
        if query.isdigit() and len(query) > 8:
            p_ean = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google", "q": query}
            res = GoogleSearch(p_ean).get_dict().get("organic_results", [])
            if res: scan_target = res[0].get("title", "").split(" - ")[0]

        params = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google_shopping", "q": scan_target, "google_domain": "google.fr", "num": "15"}
        results = GoogleSearch(params).get_dict().get("shopping_results", [])
        
        prices = []; clean_res = []; main_img = ""
        for item in results:
            p_txt = str(item.get("price", "0")).replace("€", "").replace(",", ".").replace("\xa0", "").strip()
            val = float(re.findall(r"(\d+[\.,]?\d*)", p_txt)[0]) if re.findall(r"(\d+[\.,]?\d*)", p_txt) else 0
            if val > 1:
                prices.append(val)
                clean_res.append({"source": item.get("source", "Web"), "prix": val, "lien": item.get("link", ""), "titre": item.get("title", "")})
            if not main_img: main_img = item.get("thumbnail")
            
        stats = {"min": min(prices) if prices else 0, "max": max(prices) if prices else 0, "med": statistics.median(prices) if prices else 0, "count": len(prices)}
        return stats, clean_res, main_img, scan_target
    except: return {"count":0}, [], "", query

# --- 3. UI ---

def reset_all():
    for key in ['nom_final', 'go_search', 'props', 'current_img', 'scan_results', 'suggestions_data']:
        st.session_state[key] = None if key != 'go_search' else False

if 'nom_final' not in st.session_state: reset_all()

st.title("🚀 Trokia v18.2 : Full Cascade Edition")

tab_ia, tab_man = st.tabs(["📸 SCAN IA MULTI-VUES", "⌨️ MANUEL"])

with tab_ia:
    files = st.file_uploader("Photos (Vignettes)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    
    if files:
        cols_v = st.columns(6)
        imgs_pil = []
        for idx, f in enumerate(files):
            img = Image.open(f)
            imgs_pil.append(img)
            cols_v[idx % 6].image(img, width=100) # Vignettes compactes
        
        if st.button("🧠 Identifier avec la Cascade des 30 modèles", use_container_width=True, type="primary"):
            with st.spinner("L'IA teste ses cerveaux un par un..."):
                props, model_info = analyser_image_multi_cascade(imgs_pil)
                if props:
                    enriched = []
                    for p in props:
                        enriched.append({"name": p, "img": get_visual_hint(p)})
                    st.session_state.suggestions_data = enriched
                else:
                    st.error(f"Aucun modèle n'a pu identifier l'image. Erreur : {model_info}")

    if st.session_state.suggestions_data:
        st.write("---")
        st.write("##### 🎯 Suggestions visuelles :")
        cols_choice = st.columns(4)
        for i, item in enumerate(st.session_state.suggestions_data):
            with cols_choice[i]:
                if item["img"]: st.image(item["img"], use_container_width=True)
                if st.button(item["name"], key=f"btn_{i}", use_container_width=True):
                    st.session_state.nom_final = item["name"]; st.session_state.go_search = True; st.rerun()

with tab_man:
    with st.form("m"):
        q = st.text_input("Recherche manuelle ou Code-barre")
        if st.form_submit_button("Scanner"):
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# RÉSULTATS
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    with st.spinner(f"Scan mondial pour : {st.session_state.nom_final}..."):
        stats, details, img_ref, nom_reel = scan_google_shopping_world(st.session_state.nom_final)
    
    if stats["count"] > 0:
        st.header(f"🎯 {nom_reel}")
        c_i, c_s = st.columns([1, 3])
        if img_ref: c_i.image(img_ref, width=150)
        with c_s:
            k1, k2, k3 = st.columns(3)
            k1.metric("Prix Bas", f"{stats['min']:.0f} €")
            k2.metric("Médian", f"{stats['med']:.0f} €", f"{stats['count']} offres")
            k3.metric("Prix Haut", f"{stats['max']:.0f} €")
        
        st.write("---")
        c_offres = st.columns(5)
        for i, item in enumerate(details[:10]):
            with c_offres[i%5]:
                st.metric(item["source"], f"{item['prix']:.0f} €")
                st.caption(item["titre"][:30])
                if item["lien"]: st.link_button("Lien", item["lien"])
                st.divider()
