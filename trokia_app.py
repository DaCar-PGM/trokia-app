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
st.set_page_config(page_title="Trokia v17.3 : Debug Mode", page_icon="🐞", layout="wide")

# --- 1. FONCTIONS ---
def configurer_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        all_m = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # On cherche le modèle Flash (rapide) ou Pro
        choix = next((m for m in all_m if "flash" in m.lower() and "1.5" in m), None)
        return choix if choix else all_m[0]
    except Exception as e: return None

def analyser_image_multi(image_pil, modele):
    try:
        if not modele: return [], "Erreur Clé API Gemini (Vérifie tes secrets)"
        
        model = genai.GenerativeModel(modele)
        # Prompt plus permissif
        prompt = "Analyse l'image. Donne la CATÉGORIE et 4 modèles précis. Format:\n1. [Marque Modèle]\n2. [Marque Modèle]..."
        response = model.generate_content([prompt, image_pil])
        text = response.text.strip()
        
        propositions = []
        lines = text.split('\n')
        for l in lines:
            l = l.strip()
            # On capture tout ce qui commence par un chiffre, un tiret ou une étoile
            if l and (l[0].isdigit() or l.startswith("-") or l.startswith("*")):
                # Nettoyage : on vire le "1." ou "- " du début
                clean_l = re.sub(r"^[\d\.\-\)\*]+\s*", "", l)
                propositions.append(clean_l)
        
        if not propositions:
            return [], f"L'IA a répondu mais format illisible : {text[:50]}..."
            
        return propositions, None
    except Exception as e: return [], str(e)

def scan_google_shopping_world(query):
    try:
        if "SERPAPI_KEY" not in st.secrets: return {"count":0}, [], ""
        
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_shopping",
            "q": query,
            "google_domain": "google.fr",
            "gl": "fr",
            "hl": "fr",
            "num": "20"
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        
        if "error" in results:
            print(f"Erreur SerpApi: {results['error']}")
            return {"count":0}, [], ""

        shopping_results = results.get("shopping_results", [])
        
        prices = []
        clean_results = []
        main_image = ""
        
        for item in shopping_results:
            prix_txt = str(item.get("price", "0")).replace("\xa0€", "").replace("€", "").replace(",", ".").strip()
            try:
                found = re.findall(r"(\d+[\.,]?\d*)", prix_txt)
                if found:
                    p_float = float(found[0])
                    if p_float > 1: prices.append(p_float)
                else: p_float = 0
            except: p_float = 0
            
            if not main_image and item.get("thumbnail"): main_image = item.get("thumbnail")

            link_final = item.get("link")
            if not link_final: link_final = item.get("product_link", "")

            clean_results.append({
                "source": item.get("source", "Web"),
                "prix": p_float,
                "lien": link_final,
                "titre": item.get("title", "Sans titre")
            })
            
        stats = {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0,
            "med": statistics.median(prices) if prices else 0,
            "count": len(prices)
        }
        return stats, clean_results, main_image

    except Exception as e:
        print(f"Crash Scan: {e}")
        return {"count":0}, [], ""

# --- SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds"])
        return gspread.authorize(creds).open("Trokia_DB").sheet1
    except: return None

def get_historique(sheet):
    try:
        data = sheet.get_all_values()
        if len(data) > 1:
            headers = data[0]; rows = data[-5:]; rows.reverse()
            return pd.DataFrame(rows, columns=headers)
    except: pass
    return pd.DataFrame()

# --- UI ---
st.title("🐞 Trokia v17.3 : Debug Mode")
if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

def reset_all():
    st.session_state.nom_final = ""; st.session_state.go_search = False
    st.session_state.props = []; st.session_state.current_img = None
    st.session_state.scan_results = None

if 'nom_final' not in st.session_state: reset_all()

# Header
c_logo, c_btn = st.columns([4,1])
c_logo.caption("Mode robuste activé")
if c_btn.button("🔄 Reset Total"): reset_all(); st.rerun()

# Onglets
tab_photo, tab_manuel = st.tabs(["📸 IA VISUELLE", "⌨️ MANUEL / EAN"])

with tab_photo:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    # Bouton de secours si le chargement auto échoue
    if f:
        if st.button("⚡ Forcer l'analyse (Si bloqué)", type="secondary"):
            st.session_state.current_img = None # Force le rechargement
            st.rerun()

    # Logique IA
    if f and st.session_state.current_img != f.name:
        st.session_state.current_img = f.name
        st.session_state.go_search = False 
        st.session_state.scan_results = None
        
        with st.spinner("🤖 Identification IA en cours..."):
            p, err = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
            if p: 
                st.session_state.props = p
                st.rerun()
            else:
                # ICI ON AFFICHE ENFIN L'ERREUR !
                st.error(f"⚠️ L'IA a échoué : {err}")
                st.info("Conseil : Réessayez ou passez en mode Manuel.")

    # Affichage Choix
    if st.session_state.props:
        st.write("##### 👇 Cliquez sur le bon modèle :")
        c1, c2 = st.columns(2)
        for i, prop in enumerate(st.session_state.props):
            col = c1 if i % 2 == 0 else c2
            if col.button(f"🔍 {prop}", use_container_width=True):
                st.session_state.nom_final = prop
                st.session_state.go_search = True
                st.rerun()

with tab_manuel:
    with st.form("man"):
        q = st.text_input("Recherche ou EAN")
        if st.form_submit_button("🔎 Scanner") and q:
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# RÉSULTATS
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    st.markdown(f"### 🎯 Résultat : **{st.session_state.nom_final}**")
    
    if not st.session_state.scan_results:
        with st.spinner("🌍 Scan Mondial (Google Shopping)..."):
            stats, details, img_ref = scan_google_shopping_world(st.session_state.nom_final)
            st.session_state.scan_results = (stats, details, img_ref)
    
    if st.session_state.scan_results:
        stats, details, img_ref = st.session_state.scan_results
        if stats["count"] > 0:
            c_img, c_stats = st.columns([1, 3])
            if img_ref: c_img.image(img_ref, width=150)
            with c_stats:
                k1, k2, k3 = st.columns(3)
                k1.metric("Min", f"{stats['min']:.0f} €")
                k2.metric("Médian", f"{stats['med']:.0f} €")
                k3.metric("Max", f"{stats['max']:.0f} €")
            
            st.write("---")
            cols = st.columns(5)
            for i, item in enumerate(details[:10]):
                with cols[i%5]:
                    st.metric(item["source"], f"{item['prix']:.0f} €")
                    st.caption(item["titre"][:20]+"..")
                    if item["lien"]: st.link_button("Voir", item["lien"])
                    else: st.button("X", disabled=True, key=f"n{i}")
                    st.divider()

            st.write("---")
            cc1, cc2, cc3 = st.columns(3)
            pv = cc1.number_input("Vente (€)", value=float(stats['med'])); pa = cc2.number_input("Achat (€)", 0.0)
            marge = pv - pa - (pv*0.15)
            cc3.metric("Marge", f"{marge:.2f} €", delta="Gain" if marge>0 else "Perte")
            
            if st.button("💾 Sauvegarder"):
                if sheet:
                    sheet.append_row([datetime.now().strftime("%d/%m"), st.session_state.nom_final, pv, pa, f"{marge:.2f}", img_ref])
                    st.balloons(); st.success("OK"); time.sleep(1); reset_all(); st.rerun()
        else:
            st.warning("Rien trouvé. Vérifiez votre clé SerpApi ou essayez une autre recherche.")

if sheet:
    df = get_historique(sheet)
    if not df.empty: st.write("---"); st.dataframe(df, use_container_width=True, hide_index=True)
