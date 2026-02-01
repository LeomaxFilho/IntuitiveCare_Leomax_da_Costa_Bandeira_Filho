from pathlib import Path

from src.models.demonstracoes_contabeis import (
    DemonstracoesContabeis
)
from src.models.funcs import (
    salvar_csv
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent   
DATA_PROCESSADO_DIR = PROJECT_ROOT / "data" / "processado"


def main():
    data = DemonstracoesContabeis()
    data.get_anos_disponiveis()
    data.get_demonstracoes_contabeis()
    data.save_demonstracoes_contabeis()

    df_save, df = data.consolidar_analise() # pega os relatorios que vao ter os dados de CNJP e razao social
    data.salvar_dataframe_csv(df_save)
    del df_save # poupar memoria e sempre bom ne

    df = data.validar_dados(df)
    df = data.enriquecimento_dataframe(df)
    df_uf_razao_social, df_total_despesas_operadora, df_medias_despezas_operadora, df_medias_despezas_uf = data.agregacao_multiplas_estrategias(df)
    
    salvar_csv(df_uf_razao_social, "df_uf_razao_social",DATA_PROCESSADO_DIR)
    salvar_csv(df_total_despesas_operadora, "df_total_despesas_operadora",DATA_PROCESSADO_DIR)
    salvar_csv(df_medias_despezas_operadora, "df_medias_despezas_operadora",DATA_PROCESSADO_DIR)
    salvar_csv(df_medias_despezas_uf, "df_medias_despezas_uf",DATA_PROCESSADO_DIR)

    return

if __name__ == "__main__":
    main()
