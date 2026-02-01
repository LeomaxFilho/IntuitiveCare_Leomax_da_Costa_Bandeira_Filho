from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


def salvar_csv(df: pd.DataFrame, nome: str, caminho: str | Path, index: bool = False) -> None:
    caminho_completo = Path(caminho) / f'{nome}.csv'
    caminho_completo.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho_completo, index=index)

def validar_cnpj(cnpj):
    cnpj = str(cnpj).strip()
    cnpj = ''.join(filter(str.isdigit, cnpj))
    
    if len(cnpj) != 14:
        return False
    
    if cnpj == cnpj[0] * 14:
        return False
    
    peso = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * peso[i] for i in range(12))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto
    
    if int(cnpj[12]) != digito1:
        return False
    
    peso = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * peso[i] for i in range(13))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto
    
    if int(cnpj[13]) != digito2:
        return False
    
    return True


def validar_e_filtrar_cnpjs(df, coluna_cnpj='CNPJ'):
    df['CnpjValido'] = df[coluna_cnpj].apply(validar_cnpj)
    
    df_valido = df[df['CnpjValido'] == True].copy()
    df_valido.drop('CnpjValido', axis=1, inplace=True)
    
    return df_valido

def validar_cnpjs_flag(df, coluna_cnpj='CNPJ'):
    df['CnpjValido'] = df[coluna_cnpj].apply(validar_cnpj)

    return df

def validar_valores_despesas_flag(df, coluna_valor='ValorDespesas'):
    df[coluna_valor] = pd.to_numeric(df[coluna_valor], errors='coerce')    
    df['ValorValido'] = (df[coluna_valor].notna()) & (df[coluna_valor] >= 0)

    return df

def validar_razao_social_flag(df, coluna_razao='Razao_Social'):
    df['RazaoSocialValida'] = (
        df[coluna_razao].notna() & 
        (df[coluna_razao].astype(str).str.strip() != '')
    )

    return df

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
