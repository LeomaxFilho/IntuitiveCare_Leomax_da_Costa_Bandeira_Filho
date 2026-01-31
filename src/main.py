
from src.models.demonstracoes_contabeis import (
    DemonstracoesContabeis
)


def main():
    data = DemonstracoesContabeis()
    data.get_anos_disponiveis()
    data.get_demonstracoes_contabeis()
    data.save_demonstracoes_contabeis()

    df = data.consolidar_analise() # pega os relatorios que vao ter os dados de CNJP e razao social
    data.salvar_dataframe_zip(df)

    return

if __name__ == "__main__":
    main()
