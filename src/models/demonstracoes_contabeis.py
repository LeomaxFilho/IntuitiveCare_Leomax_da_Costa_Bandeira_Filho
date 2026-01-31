import logging
import zipfile
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://dadosabertos.ans.gov.br/FTP/PDA/demonstracoes_contabeis/"
BASE_URL_CADOP = "https://dadosabertos.ans.gov.br/FTP/PDA/operadoras_de_plano_de_saude_ativas/Relatorio_cadop.csv"
BASE_URL_CADOP_CANCELADAS = "https://dadosabertos.ans.gov.br/FTP/PDA/operadoras_de_plano_de_saude_canceladas/Relatorio_cadop_canceladas.csv"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
DATA_PROCESSADO_DIR = PROJECT_ROOT / "data" / "processado"


class DemonstracoesContabeis:
    def __init__(self):
        self.path = DATA_RAW_DIR / "demonstracoes_contabeis"
        self.ano_agora: datetime = datetime.now()
        self.anos: list[str] = []
        self.trimestres: dict[str, list[str]] = {}

    def get_relatorios_cadop(self) -> pd.DataFrame:
        path_raw = Path(f"{DATA_RAW_DIR}/relatorios_cadop")
        path_interim = Path(f"{DATA_INTERIM_DIR}/relatorios_cadop")

        path_raw.mkdir(parents=True, exist_ok=True)
        path_interim.mkdir(parents=True, exist_ok=True)

        df_cadop_cancelados = pd.read_csv(BASE_URL_CADOP,sep=";",encoding="latin-1",decimal=",")
        df_cadop_cancelados.to_csv(f"{path_raw}/relatorio_cadop_canceladas.csv")
        
        df_cadop = pd.read_csv(BASE_URL_CADOP_CANCELADAS,sep=";",encoding="latin-1",decimal=",")
        df_cadop.to_csv(f"{path_raw}/relatorio_cadop.csv")

        df_cadop_concat = pd.concat([df_cadop, df_cadop_cancelados], ignore_index=True)
        cols = ["REGISTRO_OPERADORA", "CNPJ", "Razao_Social"]
        df_reg_ans = df_cadop_concat[cols]

        df_reg_ans = df_reg_ans.rename(columns={'REGISTRO_OPERADORA': 'REG_ANS'}) # type: ignore[reportCallIssue]
        df_reg_ans.to_csv(f"{path_interim}/reg_ans_cnpj.csv")

        return df_reg_ans

    def get_anos_disponiveis(self) -> list[datetime]:
        try:
            response = requests.get(BASE_URL, timeout=30)
            response.raise_for_status()
            html_content = response.text
            self.anos = HtmlParser.parse_html_anos(html_content)

        except requests.RequestException as e:
            logger.error(f"Error: {e}")

        return [datetime.strptime(ano, "%Y") for ano in self.anos]

    def get_demonstracoes_contabeis(
        self, ano: int | None = None, *, num_trimestres: int = 3
    ):
        if ano is None:
            ano = self.ano_agora.year

        if str(ano) not in self.anos:
            ano = int(self.anos[-1])

        total_obtidos = sum(len(v) for v in self.trimestres.values())
        while num_trimestres > total_obtidos:

            trimestres_faltando = num_trimestres - total_obtidos
            try:
                response = requests.get(f"{BASE_URL}/{ano}", timeout=30)
                response.raise_for_status()

                html_content = response.text
                self.trimestres[f"{ano}"] = HtmlParser.parse_html_demonstracoes(
                    html_content, trimestres_faltando
                )
            except requests.RequestException as e:
                logger.error(f"Error: {e}")

            ano -= 1

            if str(ano) not in self.anos:
                break

            total_obtidos = sum(len(v) for v in self.trimestres.values())


        return self.trimestres

    def save_demonstracoes_contabeis(self):
        self.path.mkdir(parents=True, exist_ok=True)

        for ano, trimestres in self.trimestres.items():
            for trimestre in trimestres:
                file_path = self.path / f"{trimestre}.zip"

                try:
                    response = requests.get(
                        f"{BASE_URL}/{ano}/{trimestre}.zip", timeout=30
                    )
                    response.raise_for_status()

                    with open(file_path, "wb") as f:
                        f.write(response.content)

                except requests.RequestException as e:
                    logger.error(f"Error ao baixar/salvar o arquivo {file_path}: {e}")

                try:
                    with zipfile.ZipFile(file_path, "r") as zip_ref:
                        zip_ref.extractall(self.path)
                    file_path.unlink()
                    logger.info(f"Arquivo {file_path} removido apos extracao.")

                except (zipfile.BadZipFile, OSError) as e:
                    logger.error(f"Erro ao descompactar o arquivo {file_path}: {e}")

        return

    def consolidar_analise(self) -> pd.DataFrame:
        df_reg_ans = self.get_relatorios_cadop()

        dfs = []
        for ano, trimestres in self.trimestres.items():
            for trimestre in trimestres:
                df = pd.read_csv(f"{DATA_RAW_DIR}/demonstracoes_contabeis/{trimestre}.csv", sep=";",encoding="latin-1",decimal=",")
                
                df["Ano"] = ano
                df["Trimestre"] = trimestre
                dfs.append(df)

        df_concat = pd.concat(dfs, ignore_index=True)
        df_filtrado = df_concat[df_concat.DESCRICAO.str.contains(r'(?=.*eventos)(?=.*sinistros)', case=False, na=False, regex=True)]
        df_filrado_com_cnpj = df_filtrado.merge(df_reg_ans, how="inner", on="REG_ANS")
        df_filrado_com_cnpj["ValorDespesas"] = df_filrado_com_cnpj.VL_SALDO_FINAL - df_filrado_com_cnpj.VL_SALDO_INICIAL
        cols = ['CNPJ', 'Razao_Social', 'ValorDespesas']
        df_fim = df_filrado_com_cnpj[cols]
        df_fim = df_fim.dropna() # qualquer linha que tiver a ausencia de um desses valores é uma linha inválida

        df_fim = df_fim.rename(columns={
            'Razao_Social' : 'RazaoSocial'
        } )# type: ignore[reportCallIssue]

        return df_fim

    def salvar_dataframe_zip(self, df):
        nome_arquivo_csv='consolidado_despesas.csv'
        path = f"{DATA_PROCESSADO_DIR}/consolidado_despesas.zip"

        diretorio = os.path.dirname(path)
        if diretorio and not os.path.exists(diretorio):
            os.makedirs(diretorio)

        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            csv_data = df.to_csv(index=False)
            zipf.writestr(nome_arquivo_csv, csv_data)

class HtmlParser:
    @staticmethod
    def parse_html_anos(html_content: str) -> list[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        links = soup.find_all("a", href=True)

        anos = [
            link.text.strip().rstrip("/")
            for link in links
            if link.text.strip().rstrip("/").isdigit()
        ]
        return anos

    @staticmethod
    def parse_html_demonstracoes(
        html_content: str, trimestres_faltando: int
    ) -> list[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        links = soup.find_all("a", href=True)
        demonstracoes = [
            link.text.strip().removesuffix(".zip")
            for link in links
            if link.text.strip().endswith(".zip")
        ]
        if len(demonstracoes) > trimestres_faltando:
            demonstracoes = demonstracoes[-trimestres_faltando:]

        return demonstracoes