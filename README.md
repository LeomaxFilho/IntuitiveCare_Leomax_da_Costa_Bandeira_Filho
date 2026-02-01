# Teste Intuitive Care - Leomax da Costa Bandeira Filho

Esse projeto foi desenvolvido como parte do processo seletivo para estágio na Intuitive Care. Abaixo documento as decisões técnicas que tomei durante o desenvolvimento, explicando os trade-offs considerados e o raciocínio por trás de cada escolha.

## Como executar

### Requisitos
- Python 3.14+
- uv (gerenciador de pacotes)

### Instalação

```bash
# Clone o repositório
git clone <repo-url>
cd IntuitiveCare_Leomax_da_Costa_Bandeira_Filho

# Instale as dependências
uv sync

# Execute o programa principal
uv run intuitive-care
```

O programa vai:
1. Baixar automaticamente os dados dos últimos 3 trimestres
2. Processar e gerar o arquivo `consolidado_despesas.zip` na pasta `data/processado/`
3. Validar os dados e adicionar flags de qualidade
4. Enriquecer o dataframe com dados cadastrais (Modalidade, UF, status de atividade)

---

## Tópico 1 - Integração com API Pública

### 1.1 Acesso à API de Dados Abertos da ANS

A primeira coisa que percebi ao acessar a URL da ANS é que não é bem uma API REST tradicional - é mais um servidor de arquivos (FTP via HTTP). A página retorna um HTML com links para os diretórios de cada ano.

**Como resolvi:** Usei `requests` pra buscar o HTML e `BeautifulSoup` pra fazer o parsing dos links. A classe `HtmlParser` (em `src/models/funcs.py`) tem dois métodos estáticos:
- `parse_html_anos()`: extrai os anos disponíveis (2008, 2009, ..., 2025)
- `parse_html_demonstracoes()`: extrai os nomes dos arquivos ZIP de cada trimestre

Optei por essa abordagem porque é mais simples do que usar uma lib de scraping mais robusta. O BeautifulSoup resolve bem o problema e é leve.

### 1.2 Processamento de Arquivos

**Baixar os últimos 3 trimestres:** O código começa pelo ano atual e vai voltando até conseguir 3 trimestres. Isso é importante porque nem sempre o ano atual tem todos os trimestres publicados - quando rodei os testes, 2025 só tinha até o 3T.

A lógica está no método `get_demonstracoes_contabeis()`:
```python
while num_trimestres > total_obtidos:
    # busca trimestres do ano atual
    # se não completar 3, vai pro ano anterior
    ano -= 1
```

**Extração automática dos ZIPs:** Depois de baixar, o código já extrai os CSVs e deleta os ZIPs originais pra não ocupar espaço desnecessário.

**Identificar arquivos com Eventos/Sinistros:** Usei uma regex com lookahead pra pegar linhas que contenham TANTO "eventos" QUANTO "sinistros" (em qualquer ordem):
```python
df_filtrado = df_concat[df_concat.DESCRICAO.str.contains(
    r'(?=.*eventos)(?=.*sinistros)',
    case=False,
    na=False,
    regex=True
)]
```

O `case=False` garante que funciona independente de maiúsculas/minúsculas, e o `na=False` evita problemas com valores nulos.

### Trade-off: Processamento em memória vs incremental

**Decisão:** Optei por processar tudo em memória.

**Justificativa:** Analisei o tamanho dos arquivos - cada CSV trimestral tem em torno de 200-300MB. Com 3 trimestres, estamos falando de menos de 1GB de dados. Considerando o overhead do pandas, ainda assim fica tranquilo pra rodar em qualquer máquina moderna (a maioria tem pelo menos 8GB de RAM).

Se fosse um cenário com muito mais dados (tipo histórico de 10 anos), aí faria sentido processar em chunks ou usar Dask. Mas pro escopo do teste, carregar tudo em memória é mais simples e rápido de implementar.

### 1.3 Consolidação e Análise de Inconsistências

Essa parte foi interessante porque precisei juntar os dados das demonstrações contábeis com os dados cadastrais das operadoras pra conseguir o CNPJ e a Razão Social.

**Problema 1: De onde vem o CNPJ?**

Os arquivos de demonstrações contábeis têm uma coluna `REG_ANS` (registro na ANS), mas não têm CNPJ. O CNPJ está nos arquivos de cadastro das operadoras (Relatorio_cadop.csv).

**Solução:** Fiz um merge usando `REG_ANS` como chave com `how="left"`:
```python
df_cadop_concat = pd.concat([df_cadop, df_cadop_cancelados], ignore_index=True)
df_filrado_com_cnpj = df_filtrado.merge(df_reg_ans, how="left", on="REG_ANS")
```

**Problema 2: CNPJs sem correspondência no cadastro**

Durante a exploração inicial (notebooks 0.1 e 0.2), percebi que alguns `REG_ANS` das demonstrações contábeis não tinham correspondência no cadastro de operadoras ativas. Investiguei mais a fundo no notebook `1.0_leomaxfilho_exploracao_inicial.ipynb` e descobri que esses registros eram de **operadoras canceladas**.

**Solução:** Passei a baixar também o arquivo de operadoras canceladas e concatenar com as ativas. Adicionei uma flag `RegASNAtivo` pra indicar o status:
```python
df_cadop_cancelados["RegASNAtivo"] = False
df_cadop["RegASNAtivo"] = True
df_cadop_concat = pd.concat([df_cadop, df_cadop_cancelados], ignore_index=True)
```

Isso resolveu o problema - a análise no notebook 1.0 mostra que não existe mais nenhum CNPJ sem correspondente depois dessa mudança.

**Problema 3: CNPJs duplicados com razões sociais diferentes**

Encontrei casos assim durante a exploração:

| CNPJ | Razao_Social |
|------|--------------|
| 126507000196 | MASSA FALIDA DE UNILIFE SAÚDE LTDA. |
| 126507000196 | ODONTO SAÚDE LTDA |

**Análise:** São empresas que mudaram de nome/razão social ao longo do tempo, mas mantiveram o mesmo CNPJ. Algumas entraram em falência, outras foram adquiridas.

**Decisão:** Mantive ambos os registros. Se eu escolhesse só um, estaria perdendo informação histórica. Como o objetivo é analisar despesas, faz sentido manter o registro mesmo que a empresa tenha mudado de nome.

**Problema 4: Valores zerados ou negativos**

O campo `ValorDespesas` é calculado como a diferença entre saldo final e inicial:
```python
df["ValorDespesas"] = df.VL_SALDO_FINAL - df.VL_SALDO_INICIAL
```

Isso pode resultar em valores negativos (quando o saldo diminuiu) ou zero.

**Decisão:** Mantive esses valores. Um valor negativo não é necessariamente um erro - pode indicar reversão de provisão, por exemplo. Remover esses dados seria "limpar" informação que pode ser relevante pra análise.

**Problema 5: Linhas com dados faltantes**

Usei `dropna()` pra remover linhas onde CNPJ, Razão Social ou Valor estejam nulos:
```python
df_fim = df_fim.dropna()
```

Se algum desses campos está vazio, a linha não serve pra análise, então faz sentido descartar.

### Saída final

O método `consolidar_analise()` retorna dois dataframes:
1. `df_fim`: versão limpa com apenas `CNPJ`, `RazaoSocial`, `ValorDespesas` - salvo no ZIP
2. `df_filrado_com_cnpj`: versão completa com todas as colunas - usado para validação e enriquecimento

O arquivo `consolidado_despesas.zip` contém o CSV limpo.

---

## Tópico 2 - Transformação e Validação de Dados

### 2.1 Estratégia de Validação: Flags vs Filtragem

O PDF do teste pede validações para CNPJ, valores numéricos positivos e razão social não vazia - mas deixa em aberto **como** tratar os registros que falharem.

**Decisão:** Optei por usar **flags** (colunas booleanas) pra marcar registros inválidos, em vez de removê-los do dataset.

As validações adicionam as seguintes colunas:
- `CnpjValido`: valida formato (14 dígitos) e dígitos verificadores
- `ValorValido`: verifica se o valor é numérico e >= 0
- `RazaoSocialValida`: verifica se a razão social não está vazia ou nula

**Implementação:**
```python
df = (df
    .pipe(validar_cnpjs_flag)
    .pipe(validar_valores_despesas_flag)
    .pipe(validar_razao_social_flag)
)
```

### Por que flags em vez de remover?

**Prós:**
- **Preserva os dados originais:** O analista pode decidir o que fazer com registros inválidos dependendo do contexto
- **Transparência:** Fica explícito quantos registros têm problemas e quais são
- **Flexibilidade:** Dá pra filtrar depois (`df[df.CnpjValido]`) ou analisar os inválidos separadamente (`df[~df.CnpjValido]`)
- **Auditoria:** Facilita investigar por que certos CNPJs são inválidos (erro de digitação? formato antigo?)
- **Reversibilidade:** Nenhuma informação é perdida permanentemente

**Contras:**
- **Mais colunas no dataset:** Adiciona 3 colunas extras que podem não ser necessárias pra todos os usos
- **Requer passo adicional:** Quem for usar os dados precisa filtrar explicitamente se quiser só os válidos

### Trade-off: Por que não remover direto?

A alternativa seria filtrar e manter apenas registros válidos:
```python
df = df[df['CnpjValido'] & df['ValorValido'] & df['RazaoSocialValida']]
```

Não segui esse caminho porque:
1. **Perda de informação:** Remover registros pode esconder problemas sistemáticos nos dados
2. **Decisão de negócio:** O que fazer com um CNPJ inválido pode depender do contexto
3. **Análise exploratória:** Durante a exploração, é útil ver os "outliers" e entender por que estão inválidos

### Sobre a validação de CNPJ

A função `validar_cnpj()` verifica:
1. Se tem exatamente 14 dígitos (após remover formatação)
2. Se não é uma sequência repetida (ex: 11111111111111)
3. Se os dois dígitos verificadores estão corretos (algoritmo padrão da Receita Federal)

Isso garante que o CNPJ é **matematicamente válido**, mas não que ele existe de fato na base da Receita. Pra confirmar a existência seria necessário consultar a API da Receita Federal, o que está fora do escopo.

### 2.2 Enriquecimento de Dados

Depois da validação, o método `enriquecimento_dataframe()` seleciona e organiza as colunas do dataframe final.

**Colunas do dataframe enriquecido:**
| Coluna | Descrição |
|--------|-----------|
| `REG_ANS` | Registro da operadora na ANS |
| `CNPJ` | CNPJ da operadora |
| `Razao_Social` | Nome da empresa |
| `Trimestre` | Período do dado (ex: 3T2024) |
| `Ano` | Ano do dado |
| `ValorDespesas` | Valor calculado das despesas |
| `Modalidade` | Tipo de operadora (Medicina de Grupo, Cooperativa, etc.) |
| `UF` | Estado da operadora |
| `CnpjValido` | Flag de validação do CNPJ |
| `ValorValido` | Flag de validação do valor |
| `RazaoSocialValida` | Flag de validação da razão social |
| `RegASNAtivo` | Se a operadora está ativa ou cancelada na ANS |

A flag `RegASNAtivo` é especialmente útil pra identificar operadoras que já não estão mais em operação mas ainda aparecem nos dados históricos.

### 2.3 Agregação com Múltiplas Estratégias

O método `agregacao_multiplas_estrategias()` gera 4 dataframes com diferentes visões dos dados:

**1. `df_uf_razao_social`** - Agrupado por UF e CNPJ:
- `RazaoSocial`: nome da operadora
- `MediaDespesas`: média das despesas
- `TotalDespesas`: soma total das despesas

**2. `df_total_despesas_operadora`** - Agrupado por CNPJ:
- `RazaoSocial`: nome da operadora
- `TotalDespesas`: soma total das despesas

**3. `df_medias_despezas_operadora`** - Agrupado por CNPJ e Trimestre (desafio adicional):
- `RazaoSocial`: nome da operadora
- `MediaDespesaTrimestre`: média de despesas no trimestre
- `DesvioPadraoDespesaTrimestre`: desvio padrão das despesas (identifica operadoras com valores muito variáveis)

**4. `df_medias_despezas_uf`** - Agrupado por UF e Trimestre (desafio adicional):
- `MediaDespesaTrimestre`: média de despesas por UF no trimestre
- `DesvioPadraoDespesaTrimestre`: desvio padrão das despesas por UF

### Trade-off: Estratégia de Ordenação

**Decisão:** Usei `sort_values()` do pandas com ordenação em memória.

**Justificativa:** Para o volume de dados que estamos trabalhando (alguns milhares de registros agregados), a ordenação em memória com pandas é suficiente e performática. O algoritmo padrão do pandas (Timsort) tem complexidade O(n log n) e é otimizado para dados parcialmente ordenados.

**Alternativas consideradas:**
- **Ordenação externa (disco):** Necessária apenas para datasets que não cabem em memória. Nosso caso está longe disso.

Todos os dataframes são ordenados por valor (maior para menor) usando:
```python
df = df.sort_values(by="TotalDespesas", ascending=False)
```

---

## Notebooks de exploração

A exploração foi feita em 4 notebooks, cada um com um propósito:

- **`0.1_leomaxfilho_exploracao_inicial.ipynb`**: Exploração inicial - entendi a estrutura dos CSVs e testei o merge com os dados cadastrais. Aqui descobri os CNPJs duplicados com razões sociais diferentes.

- **`0.2_leomaxfilho_exploracao_inicial.ipynb`**: Testei a classe `DemonstracoesContabeis` e refinei a lógica de processamento.

- **`1.0_leomaxfilho_exploracao_inicial.ipynb`**: Investiguei os registros sem correspondência no cadastro. Descobri que eram operadoras canceladas e implementei a solução de baixar também o arquivo de canceladas. A análise mostra que após essa mudança, não existe mais nenhum CNPJ sem correspondente.

- **`1.1_leomaxfilho_exploracao_inicial.ipynb`**: Análises de agregação - testei os agrupamentos por RazãoSocial, UF e Trimestre. Calculei totais, médias e desvio padrão das despesas por operadora. Esse notebook serviu de base para implementar o método `agregacao_multiplas_estrategias()`.

---

## Estrutura do projeto

```
.
├── data/
│   ├── raw/                          # Dados brutos baixados
│   │   ├── demonstracoes_contabeis/  # CSVs extraídos dos ZIPs
│   │   └── relatorios_cadop/         # Cadastros de operadoras
│   ├── interim/                      # Dados intermediários
│   │   └── relatorios_cadop/         # Cadastro consolidado
│   └── processado/                   # Saída final (consolidado_despesas.zip)
├── notebooks/                        # Notebooks de exploração
├── src/
│   ├── models/
│   │   ├── demonstracoes_contabeis.py  # Classe principal
│   │   └── funcs.py                    # Validações e HtmlParser
│   └── main.py                       # Entry point
└── README.md
```

---

## Autor

Leomax da Costa Bandeira Filho
leomax.filho@gmail.com
