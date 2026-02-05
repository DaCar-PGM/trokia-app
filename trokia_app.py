import streamlit as st
import pandas as pd
import os
from datetime import datetime
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia Ultimate", page_icon="💎", layout="wide")
FICHIER_STOCK = "stock_trokia.xlsx"

# --- CERVEAU (DICTIONNAIRE AMÉLIORÉ) ---
def deviner_categorie(nom_produit):
    nom = str(nom_produit).lower()
    regles = {
        "🎮 Gaming": ["ps5", "ps4", "switch", "nintendo", "xbox", "jeu", "zelda", "mario", "manette", "console", "gameboy", "game boy", "pokemon", "sega"],
        "📱 Téléphonie": ["iphone", "samsung", "galaxy", "xiaomi", "redmi", "pixel", "huawei", "smartphone", "oppo", "nokia"],
        "💻 Informatique": ["macbook", "dell", "hp", "asus", "lenovo", "ordinateur", "pc", "laptop", "clavier", "souris", "usb", "ipad", "tablette", "geforce", "nvidia"],
        "📸 Photo/Vidéo": ["canon", "nikon", "sony alpha", "gopro", "camera", "objectif", "instax", "lumix", "kodak"],
        "📚 Livres/Culture": ["livre", "roman", "bd", "manga", "tome", "album", "cd", "dvd", "blu-ray", "vinyle", "collector"],
        "👟 Mode/Luxe": ["nike", "adidas", "jordan", "yeezy", "sac", "montre", "rolex", "seiko", "vêtement", "gucci", "vuitton"],
        "🏠 Maison/Électro": ["aspirateur", "dyson", "cafetière", "robot", "cuisine", "outil", "bricolage", "bosch", "makita"]
    }
    for categorie, mots_cles in regles.items():
        if any(mot in nom for mot in mots_cles): return categorie
    return "📦 Divers"

# --- BACKEND (MOTEUR AVEC YEUX) ---
def configurer_navigateur():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    return options

def analyser_produit_ebay(driver, recherche):
    # Cette fonction renvoie MAINTENANT 2 choses : Le PRIX et L'IMAGE
    url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
    driver.get(url)
    time.sleep(2)
    
    # 1. Récupération de l'image (Premier résultat)
    image_url = None
    try:
        # On cherche l'image du premier résultat
        img_element = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
        image_url = img_element.get_attribute("src")
    except:
        image_url = "https://via.placeholder.com/300x300.png?text=Pas+d+image"

    # 2. Récupération du prix
    texte = driver.find_element(By.TAG_NAME, "body").text
    motifs = re.findall(r"(\d+[\.,]?\d*)\s*EUR", texte)
    prix_liste = []
    for p in motifs:
        try:
            val = float(p.replace(',', '.').strip())
            if 1 < val < 10000: prix_liste.append(val)
        except: continue
    
    prix_final = sum(prix_liste) / len(prix_liste) if prix_liste else 0
    
    return prix_final, image_url

def charger_stock():
    if not os.path.exists(FICHIER_STOCK):
        return pd.DataFrame(columns=["Date", "Produit", "Estimation (€)", "Prix Achat (€)", "Catégorie", "Image"])
    
    df = pd.read_excel(FICHIER_STOCK)
    modifie = False
    
    # Migrations colonnes
    if "Prix Achat (€)" not in df.columns: df["Prix Achat (€)"], modifie = 0.0, True
    if "Catégorie" not in df.columns: df["Catégorie"], modifie = "Non classé", True
    if "Image" not in df.columns: df["Image"], modifie = "", True # Nouvelle colonne Image
        
    for index, row in df.iterrows():
        cat = str(row.get("Catégorie", "Non classé"))
        if cat in ["Non classé", "nan", "None", "📦 Divers"]: # On re-vérifie même les "Divers"
            nouvelle_cat = deviner_categorie(row["Produit"])
            if nouvelle_cat != cat:
                df.at[index, "Catégorie"] = nouvelle_cat
                modifie = True
            
    if modifie: df.to_excel(FICHIER_STOCK, index=False)
    return df

def sauvegarder_stock(df):
    df.to_excel(FICHIER_STOCK, index=False)

# --- INTERFACE ---
st.title("💎 Trokia Ultimate : Vision & Trader")

col_scan, col_kpi = st.columns([1, 2])

# GAUCHE : SCANNER VISUEL
with col_scan:
    st.markdown("### 👁️ Scanner Visuel")
    entree = st.text_input("Produit", placeholder="Ex: Game Boy Color")
    
    if 'dernier_prix' not in st.session_state: st.session_state.dernier_prix = None
    if 'dernier_img' not in st.session_state: st.session_state.dernier_img = None
    if 'dernier_produit' not in st.session_state: st.session_state.dernier_produit = ""

    if st.button("Lancer l'Analyse 🚀", use_container_width=True):
        with st.spinner("Recherche visuelle et financière..."):
            service = Service(ChromeDriverManager().install())
            options = configurer_navigateur()
            driver = webdriver.Chrome(service=service, options=options)
            try:
                # On récupère PRIX et IMAGE
                prix, img = analyser_produit_ebay(driver, entree)
                st.session_state.dernier_prix = prix
                st.session_state.dernier_img = img
                st.session_state.dernier_produit = entree
            except: 
                st.session_state.dernier_prix = 0
            finally: 
                driver.quit()

    if st.session_state.dernier_prix is not None and st.session_state.dernier_prix > 0:
        valeur = round(st.session_state.dernier_prix, 2)
        
        # ZONE DE VALIDATION VISUELLE
        c_img, c_info = st.columns([1, 2])
        with c_img:
            if st.session_state.dernier_img:
                st.image(st.session_state.dernier_img, caption="Produit trouvé", width=150)
        with c_info:
            st.success(f"Cote : **{valeur} €**")
            prix_achat = st.number_input("Prix d'achat (€)", min_value=0.0, step=1.0)
            
            profit = valeur - prix_achat
            if profit > 0:
                st.metric("Marge", f"+{round(profit, 2)} €", delta="PROFIT")
            else:
                st.metric("Marge", f"{round(profit, 2)} €", delta="PERTE", delta_color="inverse")
        
        if st.button("💾 Valider (Image + Prix)", use_container_width=True):
            df = charger_stock()
            cat = deviner_categorie(st.session_state.dernier_produit)
            new_row = {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Produit": st.session_state.dernier_produit,
                "Estimation (€)": valeur,
                "Prix Achat (€)": prix_achat,
                "Catégorie": cat,
                "Image": st.session_state.dernier_img
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            sauvegarder_stock(df)
            st.toast("Stock mis à jour !", icon="📸")
            st.session_state.dernier_prix = None
            st.rerun()

# DROITE : DASHBOARD
with col_kpi:
    st.markdown("### 📊 Empire Financier")
    df = charger_stock()
    
    if not df.empty:
        total_valeur = df["Estimation (€)"].sum()
        total_investi = df["Prix Achat (€)"].sum()
        total_profit = total_valeur - total_investi
        marge_pct = ((total_profit / total_investi) * 100) if total_investi > 0 else 0
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Valeur Stock", f"{round(total_valeur, 2)} €")
        k2.metric("Investissement", f"{round(total_investi, 2)} €")
        k3.metric("NET PROFIT", f"{round(total_profit, 2)} €", delta=f"{round(marge_pct)} %")
        
        df["Marge"] = df["Estimation (€)"] - df["Prix Achat (€)"]
        chart_data = df.groupby("Catégorie")["Marge"].sum()
        st.bar_chart(chart_data, color="#2ECC71")
    else:
        st.info("En attente de données...")

st.markdown("---")
st.subheader("🛠️ Inventaire & Images")
if not df.empty:
    st.dataframe(
        df[["Date", "Produit", "Estimation (€)", "Prix Achat (€)", "Catégorie", "Image"]],
        column_config={"Image": st.column_config.ImageColumn("Aperçu", width="small")},
        use_container_width=True
    )