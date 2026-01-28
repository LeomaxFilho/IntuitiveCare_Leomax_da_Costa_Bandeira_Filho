import logging
import os
import zipfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://dadosabertos.ans.gov.br/FTP/PDA/demonstracoes_contabeis/"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
DATA_PROCESSADO_DIR = PROJECT_ROOT / "data" / "processado"

if __name__ == "__main__":
    logger.info("Starting script")
    logger.info("Script finished")


class demonstracoes_contabeis:
    def __init__(self):
        self.path = DATA_RAW_DIR / "demonstracoes_contabeis"
        self.ano_agora: datetime = datetime.now()
        self.anos: list[str] = []
        self.trimestres: dict[str] = {}

    def get_anos_disponiveis(self) -> list[datetime]:
        try:
            response = requests.get(BASE_URL)
            html_content = response.text
            self.anos = html_parser().parse_html_anos(html_content)

        except Exception as e:
            logger.error(f"Error: {e}")

        return [datetime.strptime(ano, "%Y") for ano in self.anos]

    def get_demonstracoes_contabeis(
        self, ano: int | None = None, *, num_trimestres: int = 3
    ):
        if ano is None:
            ano = self.ano_agora.year

        try:
            while num_trimestres > sum(len(v) for v in self.trimestres.values()):
                trimestres_faltando = num_trimestres - sum(
                    len(v) for v in self.trimestres.values()
                )
                response = requests.get(f"{BASE_URL}/{ano}")

                html_content = response.text
                self.trimestres[f"{ano}"] = html_parser().parse_html_demonstracoes(
                    html_content, trimestres_faltando
                )

                ano -= 1

        except Exception as e:
            logger.error(f"Error: {e}")

        return self.trimestres

    def save_demonstracoes_contabeis(self):
        os.makedirs(self.path, exist_ok=True)

        for ano, trimestres in self.trimestres.items():
            for trimestre in trimestres:
                file_path = f"{self.path}/{trimestre}.zip"

                try:
                    response = requests.get(f"{BASE_URL}/{ano}/{trimestre}.zip")

                    with open(f"{file_path}", "wb") as f:
                        f.write(response.content)

                except Exception as e:
                    logger.error(f"Error ao baixar/salvar o arquivo {file_path}: {e}")

                try:
                    with zipfile.ZipFile(file_path, "r") as zip_ref:
                        zip_ref.extractall(self.path)
                    os.remove(file_path)
                    logger.info(f"Arquivo {file_path} removido apos extracao.")

                except Exception as e:
                    logger.error(f"Erro ao descompactar o arquivo {file_path}: {e}")


class html_parser:
    def __init__(self):
        self.data = None

    def parse_html_anos(self, html_content) -> list[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        links = soup.find_all("a", href=True)

        anos = [
            link.text.strip().rstrip("/")
            for link in links
            if link.text.strip().rstrip("/").isdigit()
        ]
        return anos

    def parse_html_demonstracoes(
        self, html_content: str, trimestres_faltando: int
    ) -> list[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        links = soup.find_all("a", href=True)
        demonstracoes = [
            link.text.strip().rstrip(".zip")
            for link in links
            if link.text.strip()[-4:] == ".zip"
        ]
        if len(demonstracoes) > trimestres_faltando:
            demonstracoes = demonstracoes[:trimestres_faltando]

        return demonstracoes
