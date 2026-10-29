import os
import tarfile
import subprocess
import requests
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Buscador de Brechós B2B", page_icon="🛍️", layout="wide")
st.title("🛍️ Buscador de Brechós B2B")
st.caption("Encontre novos clientes e parceiros diretamente no Google Maps")

BINARY_NAME = "google-maps-scraper"
# URL do binário pré-compilado (Versão Linux x86_64)
RELEASE_URL = "https://github.com/gosom/google-maps-scraper/releases/download/v0.3.10/google-maps-scraper_Linux_x86_64.tar.gz"

# --- FUNÇÃO PARA GARANTIR O BINÁRIO RODE ---
def setup_scraper_binary():
    if not os.path.exists(BINARY_NAME):
        with st.spinner("Instalando o motor de busca..."):
            response = requests.get(RELEASE_URL, stream=True)
            archive_path = "scraper.tar.gz"
            with open(archive_path, "wb") as f:
                f.write(response.content)
            
            # Extrai o executável
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall()
            
            # Concede permissão de execução
            os.chmod(BINARY_NAME, 0o755)
            if os.path.exists(archive_path):
                os.remove(archive_path)

# --- FUNÇÃO DE ENVIO PARA O GOOGLE SHEETS ---
def salvar_no_google_sheets(df):
    try:
        if "GOOGLE_CREDENTIALS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            
            # Abre a planilha pelo nome configurado
            sheet_name = st.secrets.get("SPREADSHEET_NAME", "Prospecção de Brechós")
            sheet = client.open(sheet_name).sheet1
            
            # Prepara os dados e injeta
            sheet.append_rows(df.astype(str).values.tolist())
            return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")
        return False
    return False

# --- INTERFACE E FLUXO PRINCIPAL ---
setup_scraper_binary()

termo_busca = st.text_input("Digite o termo de busca:", placeholder="Ex: brechó Caxias do Sul")
profundidade = st.slider("Quantidade de resultados (Profundidade):", min_value=1, max_value=5, value=1)

if st.button("🚀 Iniciar Busca", type="primary"):
    if not termo_busca:
        st.warning("Por favor, digite um termo de busca.")
    else:
        results_file = "resultados_brutos.csv"
        
        # Remove arquivo de busca anterior se existir
        if os.path.exists(results_file):
            os.remove(results_file)

        cmd = [
            f"./{BINARY_NAME}",
            "-q", termo_busca,
            "-results", results_file,
            "-depth", str(profundidade),
            "-lang", "pt"
        ]

        with st.spinner("Varrendo o Google Maps... Isso pode levar de 1 a 3 minutos."):
            process = subprocess.run(cmd, capture_output=True, text=True)

        if os.path.exists(results_file):
            df_bruto = pd.read_csv(results_file)
            
            if not df_bruto.empty:
                # Trata e filtra colunas essenciais
                colunas_desejadas = ["title", "phone", "website", "address", "rating", "reviews_total"]
                colunas_existentes = [col for col in colunas_desejadas if col in df_bruto.columns]
                
                df_limpo = df_bruto[colunas_existentes].dropna(subset=["phone"]) if "phone" in df_bruto.columns else df_bruto[colunas_existentes]
                
                renomear = {
                    "title": "Nome do Brechó",
                    "phone": "Telefone/WhatsApp",
                    "website": "Site/Instagram",
                    "address": "Endereço",
                    "rating": "Nota",
                    "reviews_total": "Total Avaliações"
                }
                df_limpo = df_limpo.rename(columns=renomear)

                st.success(f"Busca finalizada! {len(df_limpo)} brechós encontrados.")
                
                # Exibe a tabela interativa no Streamlit
                st.dataframe(df_limpo, use_container_width=True)

                # Botão de Download direto em CSV
                csv_data = df_limpo.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Baixar em CSV / Excel",
                    data=csv_data,
                    file_name=f"brechos_{termo_busca.replace(' ', '_')}.csv",
                    mime="text/csv",
                )

                # Tenta salvar automaticamente no Google Sheets
                if salvar_no_google_sheets(df_limpo):
                    st.toast("Contatos sincronizados com o Google Sheets!", icon="✅")

            else:
                st.info("Nenhum resultado encontrado para essa busca.")
        else:
            st.error("Falha ao gerar o arquivo de resultados. Tente novamente com outro termo.")
