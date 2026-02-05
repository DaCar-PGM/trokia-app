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

# --- CONFIGURATION ULTIME ---
st.set_page_config(page_title="Trokia v17 : World Scan", page_icon="🌍", layout="wide")

# --- 1. FONCTIONS IA & UTILITAIRES ---
def configurer_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        all_m = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        choix = next((m for m in all_m if "flash" in m.lower() and "1.5" in m), None)
        return choix if choix else all_m[0]
    except: return None

def analyser_image_multi(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        prompt = "Analyse l'image. Donne la CATÉGORIE et 4 modèles précis. Format:\nCAT: ...\n1. ...\n2. ...\n3. ...\n4. ..."
        response = model.generate_content([prompt, image_pil])
        text = response.text.strip()
        propositions = []
        lines = text.split('\n')
        for l in lines:
            if l[0].isdigit() and "." in l: propositions.append(l.split(".", 1)[1].strip())
        return propositions, None
    except Exception as e: return [], str(e)

# --- 2. LE NOUVEAU MOTEUR MONDIAL (SerpApi/Google Shopping) ---
def scan_google_shopping_world(query):
    """
    Interroge Google Shopping pour avoir une vue globale du marché européen.
    Nécessite la clé SERPAPI_KEY dans les secrets Streamlit.
    """
    try:
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_shopping",
            "q": query,
            "google_domain": "google.fr", # On cible le marché FR/Europe
            "gl": "fr",
            "hl": "fr",
            "num": "20" # On récupère les 20 meilleurs résultats
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        shopping_results = results.get("shopping_results", [])
        
        prices = []
        clean_results = []
        main_image = ""
        
        for item in shopping_results:
            # Extraction propre du prix
            prix_txt = item.get("price", "0").replace("\xa0€", "").replace("€", "").replace(",", ".").strip()
            try:
                p_float = float(re.findall(r"(\d+[\.,]?\d*)", prix_txt)[0])
                if p_float > 1: prices.append(p_float)
            except: p_float = 0
            
            # On prend la première belle image comme référence
            if not main_image and item.get("thumbnail"):
                main_image = item.get("thumbnail")

            clean_results.append({
                "source": item.get("source", "Inconnu"),
                "prix": p_float,
                "lien": item.get("link"),
                "titre": item.get("title")
            })
            
        # Calculs statistiques
        stats = {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0,
            "med": statistics.median(prices) if prices else 0,
            "count": len(prices)
        }
        return stats, clean_results, main_image

    except Exception as e:
        print(f"Erreur SerpApi: {e}")
        return {"min":0, "med":0, "max":0, "count":0}, [], ""

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
            headers = data[0]
            rows = data[-5:]
            rows.reverse()
            return pd.DataFrame(rows, columns=headers)
    except: pass
    return pd.DataFrame()

# --- UI ---
st.title("🌍 Trokia v17 : World Scan")
if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

def reset_all():
    st.session_state.nom_final = ""; st.session_state.go_search = False
    st.session_state.props = []; st.session_state.current_img = None
    st.session_state.scan_results = None

if 'nom_final' not in st.session_state: reset_all()

# Header
c_logo, c_btn = st.columns([4,1])
c_logo.caption("Propulsé par Google Shopping Global")
if c_btn.button("🔄 Reset"): reset_all(); st.rerun()

# Onglets
tab_photo, tab_manuel = st.tabs(["📸 IA VISUELLE", "⌨️ MANUEL / EAN"])

with tab_photo:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    if f and st.session_state.current_img != f.name:
        st.session_state.current_img = f.name
        with st.spinner("🤖 Identification IA..."):
            p, e = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
            if p: st.session_state.props = p; st.rerun()
    if st.session_state.props:
        st.write("##### Choisir le modèle :")
        choix = st.radio("Options IA :", st.session_state.props + ["Autre"], horizontal=False)
        if st.button("Valider & Scanner", type="primary"):
            if choix != "Autre": st.session_state.nom_final = choix; st.session_state.go_search = True; st.rerun()

with tab_manuel:
    with st.form("man"):
        q = st.text_input("Recherche ou EAN")
        if st.form_submit_button("🔎 Scanner le Monde") and q:
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# RÉSULTATS DU SCAN MONDIAL
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    st.markdown(f"### 🎯 Analyse Globale : **{st.session_state.nom_final}**")
    
    with st.spinner("🌍 Interrogation des marchés européens via Google Shopping..."):
        stats, details, img_ref = scan_google_shopping_world(st.session_state.nom_final)
        st.session_state.scan_results = (stats, details, img_ref)

    if stats["count"] > 0:
        # Affichage Image + Stats Clés
        c_img, c_stats = st.columns([1, 3])
        if img_ref: c_img.image(img_ref, width=150, caption="Réf. Google")
        
        with c_stats:
            k1, k2, k3 = st.columns(3)
            k1.metric("Prix Bas (Opportunité)", f"{stats['min']:.0f} €")
            k2.metric("Prix Médian (La Vraie Cote)", f"{stats['med']:.0f} €", f"{stats['count']} offres scannées")
            k3.metric("Prix Haut (Pro)", f"{stats['max']:.0f} €")
        
        # Détail des offres (Top 5 pour pas polluer)
        st.write("---")
        st.write("##### 🔎 Détail des meilleures offres trouvées :")
        cols_offres = st.columns(5)
        for i, item in enumerate(details[:5]):
            with cols_offres[i]:
                st.metric(item["source"], f"{item['prix']:.0f} €")
                st.caption(item["titre"][:30]+"...")
                st.link_button("Voir", item["lien"])

        # Calculateur Marge
        st.write("---")
        st.markdown("#### 💰 Calculateur de Marge Nette")
        cc1, cc2, cc3 = st.columns(3)
        pv = cc1.number_input("Vente (€)", value=float(stats['med']), step=1.0)
        pa = cc2.number_input("Achat (€)", 0.0, step=1.0)
        marge = pv - pa - (pv * 0.15)
        cc3.metric("Profit Net Estimé", f"{marge:.2f} €", delta="Gagnant" if marge > 0 else "Perdant")

        if st.button("💾 Sauvegarder ce Scan", use_container_width=True):
            if sheet:
                sheet.append_row([datetime.now().strftime("%d/%m %H:%M"), st.session_state.nom_final, pv, pa, f"{marge:.2f}", img_ref])
                st.balloons(); st.success("Sauvegardé !"); time.sleep(1); reset_all(); st.rerun()
    else:
        st.warning("Aucun résultat probant trouvé sur Google Shopping pour cette recherche.")

# Historique
if sheet:
    df = get_historique(sheet)
    if not df.empty: st.write("---"); st.write("### 📋 Historique"); st.dataframe(df, use_container_width=True, hide_index=True)
