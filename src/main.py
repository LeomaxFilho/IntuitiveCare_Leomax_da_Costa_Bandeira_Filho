from src.models.demonstracoes_contabeis import demonstracoes_contabeis


def main() -> None:
    data = demonstracoes_contabeis()
    data.get_anos_disponiveis()
    data.get_demonstracoes_contabeis()
    data.save_demonstracoes_contabeis()


if __name__ == "__main__":
    main()
