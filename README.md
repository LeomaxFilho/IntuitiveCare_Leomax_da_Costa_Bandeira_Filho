# Teste Intuitive Care - Leomax da Costa Bandeira Filho

Esse projeto foi desenvolvido como parte do processo seletivo para estágio na Intuitive Care. Abaixo explico as decisões que tomei durante o desenvolvimento, principalmente focando no Tópico 1 (Integração com API Pública).

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

O programa vai baixar automaticamente os dados dos últimos 3 trimestres, processar e gerar o arquivo `consolidado_despesas.zip` na pasta `data/processado/`.

---

## Tópico 1 - Integração com API Pública

### 1.1 Acesso à API de Dados Abertos da ANS

A primeira coisa que percebi ao acessar a URL da ANS é que não é bem uma API REST tradicional - é mais um servidor de arquivos (FTP via HTTP). A página retorna um HTML com links para os diretórios de cada ano.

**Como resolvi:** Usei `requests` pra buscar o HTML e `BeautifulSoup` pra fazer o parsing dos links. A classe `HtmlParser` tem dois métodos estáticos:
- `parse_html_anos()`: extrai os anos disponíveis (2008, 2009, ..., 2025)
- `parse_html_demonstracoes()`: extrai os nomes dos arquivos ZIP de cada trimestre

Fiz dessa forma porque achei mais simples do que tentar alguma lib de scraping mais pesada. O BeautifulSoup resolve bem o problema e é leve.

### 1.2 Processamento de Arquivos

**Baixar os últimos 3 trimestres:** O código começa pelo ano atual e vai voltando até conseguir 3 trimestres. Isso é importante porque nem sempre o ano atual tem todos os trimestres publicados - quando rodei os testes, 2025 só tinha até o 3T.

A lógica tá no método `get_demonstracoes_contabeis()`:
```python
while num_trimestres > total_obtidos:
    # busca trimestres do ano atual
    # se não completar 3, vai pro ano anterior
    ano -= 1
```

**Extração automática dos ZIPs:** Depois de baixar, o código já extrai os CSVs e deleta os ZIPs originais pra não ocupar espaço à toa. Decidi fazer isso pra manter a pasta limpa.

**Identificar arquivos com Eventos/Sinistros:** Aqui foi onde gastei mais tempo pensando. Os arquivos têm várias colunas e precisava filtrar só as linhas relacionadas a "Despesas com Eventos/Sinistros".

Usei uma regex com lookahead pra pegar linhas que contenham TANTO "eventos" QUANTO "sinistros" (em qualquer ordem):
```python
df_filtrado = df_concat[df_concat.DESCRICAO.str.contains(
    r'(?=.*eventos)(?=.*sinistros)',
    case=False,
    na=False,
    regex=True
)]
```

O `case=False` garante que pega independente de maiúsculas/minúsculas, e o `na=False` evita problemas com valores nulos.

### Trade-off: Processamento em memória vs incremental

**Decisão:** Optei por processar tudo em memória.

**Por quê:** Fiz uma análise rápida do tamanho dos arquivos - cada CSV trimestral tem em torno de 200-300MB. Com 3 trimestres, estamos falando de menos de 1GB de dados. Considerando que o pandas adiciona algum overhead, ainda assim fica tranquilo pra rodar em qualquer máquina moderna (a maioria tem pelo menos 8GB de RAM).

Se fosse um cenário com MUITO mais dados (tipo histórico de 10 anos), aí sim faria sentido processar em chunks ou usar algo como Dask. Mas pro escopo do teste, carregar tudo em memória é mais simples e rápido de implementar.

### 1.3 Consolidação e Análise de Inconsistências

Essa parte foi interessante porque precisei juntar os dados das demonstrações contábeis com os dados cadastrais das operadoras pra conseguir o CNPJ e a Razão Social.

**Problema 1: De onde vem o CNPJ?**

Os arquivos de demonstrações contábeis têm uma coluna `REG_ANS` (registro na ANS), mas não têm CNPJ. O CNPJ tá nos arquivos de cadastro das operadoras (Relatorio_cadop.csv).

**Solução:** Fiz um merge usando `REG_ANS` como chave. Baixo os dois arquivos de cadastro (operadoras ativas E canceladas) porque algumas operadoras que aparecem nas demonstrações podem já ter sido canceladas.

```python
df_cadop_concat = pd.concat([df_cadop, df_cadop_cancelados], ignore_index=True)
df_filrado_com_cnpj = df_filtrado.merge(df_reg_ans, how="inner", on="REG_ANS")
```

**Problema 2: CNPJs duplicados com razões sociais diferentes**

Encontrei casos assim durante a exploração (notebook `0.1_leomaxfilho_exploracao_inicial.ipynb`):

| CNPJ | Razao_Social |
|------|--------------|
| 126507000196 | MASSA FALIDA DE UNILIFE SAÚDE LTDA. |
| 126507000196 | ODONTO SAÚDE LTDA |

**Análise:** São empresas que mudaram de nome/razão social ao longo do tempo, mas mantiveram o mesmo CNPJ. Algumas entraram em falência, outras foram adquiridas, etc.

**Decisão:** Mantive ambos os registros. Se eu escolhesse só um, estaria perdendo informação histórica. Como o objetivo é analisar despesas, faz sentido manter o registro mesmo que a empresa tenha mudado de nome.

**Problema 3: Valores zerados ou negativos**

O campo `ValorDespesas` é calculado como a diferença entre saldo final e inicial:
```python
df["ValorDespesas"] = df.VL_SALDO_FINAL - df.VL_SALDO_INICIAL
```

Isso pode resultar em valores negativos (quando o saldo diminuiu) ou zero.

**Decisão:** Mantive esses valores. Um valor negativo não é necessariamente um erro - pode indicar reversão de provisão, por exemplo. Remover esses dados seria "limpar" informação que pode ser relevante pra análise.

**Problema 4: Linhas com dados faltantes**

Usei `dropna()` pra remover linhas onde CNPJ, Razão Social ou Valor estejam nulos:
```python
df_fim = df_fim.dropna()
```

Se algum desses campos está vazio, a linha não serve pra análise mesmo, então faz sentido descartar.

### Saída final

O arquivo `consolidado_despesas.zip` contém um CSV com as colunas:
- `CNPJ`
- `RazaoSocial`
- `ValorDespesas`

---

## Notebooks de exploração

Antes de escrever o código final, fiz uma exploração nos notebooks pra entender melhor os dados:

- `0.1_leomaxfilho_exploracao_inicial.ipynb`: Exploração inicial, entendendo a estrutura dos CSVs, testando o merge com os dados cadastrais
- `0.2_leomaxfilho_exploracao_inicial.ipynb`: Testando a classe `DemonstracoesContabeis` e refinando a lógica de processamento

Os notebooks mostram o processo de "descoberta" - testei algumas coisas que não funcionaram antes de chegar na solução final. Deixei os comentários originais (alguns até em "internetês" tipo "esse valor tava muito estranho fui testar kkkk") porque acho que mostra o processo real de desenvolvimento.

---

## Autor

Leomax da Costa Bandeira Filho
leomax.filho@gmail.com
