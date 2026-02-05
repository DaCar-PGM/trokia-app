import streamlit as st
from serpapi import GoogleSearch
import pandas as pd
from datetime import datetime
import time

st.set_page_config(page_title="Trokia v17 : World Scan", page_icon="🌍")

# TA CLÉ SECRÈTE (À mettre dans st.secrets pour la vraie version)
SERPAPI_KEY = "COLLE_TA_CLE_ICI_POUR_TESTER" 

def scan_google_shopping(query):
    """
    Interroge Google Shopping pour avoir les prix de TOUT le web.
    """
    params = {
        "engine": "google_shopping",
        "q": query,
        "google_domain": "google.fr", # On cible la France/Europe
        "gl": "fr",
        "hl": "fr",
        "api_key": SERPAPI_KEY
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # On récupère la liste des vendeurs
        shopping_results = results.get("shopping_results", [])
        
        data = []
        prices = []
        
        for item in shopping_results:
            # On extrait proprement
            vendeur = item.get("source", "Inconnu")
            prix = item.get("price", "0").replace("\xa0€", "").replace("€", "").replace(",", ".").strip()
            # Nettoyage prix (parfois "1 200")
            try: 
                prix_float = float(prix.replace(" ", ""))
                prices.append(prix_float)
            except: prix_float = 0
            
            link = item.get("link", "")
            img = item.get("thumbnail", "")
            title = item.get("title", "")
            
            data.append({
                "Vendeur": vendeur,
                "Prix": prix_float,
                "Titre": title,
                "Lien": link,
                "Image": img
            })
            
        return data, prices
            
    except Exception as e:
        st.error(f"Erreur Scan: {e}")
        return [], []

# --- INTERFACE SIMPLIFIÉE ---
st.title("🌍 Trokia v17 : Le Scan Mondial")

query = st.text_input("Recherche un produit (ex: Nitro Venture, iPhone 12...)")

if st.button("Lancer le Scan Global 🚀"):
    with st.spinner(f"Interrogation de tous les marchands pour : {query}..."):
        resultats, liste_prix = scan_google_shopping(query)
    
    if resultats:
        # Calculs statistiques
        import statistics
        prix_min = min(liste_prix)
        prix_max = max(liste_prix)
        prix_med = statistics.median(liste_prix)
        
        # AFFICHER LES CHIFFRES CLÉS
        c1, c2, c3 = st.columns(3)
        c1.metric("Prix Bas", f"{prix_min:.2f} €")
        c2.metric("Prix Médian (Vrai Cote)", f"{prix_med:.2f} €")
        c3.metric("Prix Haut", f"{prix_max:.2f} €")
        
        st.write("---")
        st.write(f"### 🛍️ {len(resultats)} Offres trouvées sur le Web")
        
        # AFFICHER LES OFFRES
        # On fait une grille propre
        cols = st.columns(3)
        for i, item in enumerate(resultats):
            with cols[i % 3]:
                st.image(item["Image"], width=100)
                st.write(f"**{item['Prix']} €**")
                st.caption(f"Chez : {item['Vendeur']}")
                st.link_button("Voir l'offre", item["Lien"])
                st.divider()
    else:
        st.warning("Aucun résultat trouvé (ou quota API dépassé).")
