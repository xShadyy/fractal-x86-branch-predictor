<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="Licença: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <strong>Português (Brasil)</strong><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

Experimentos de predição de desvios e cache em um **AMD Ryzen 7 9800X3D com
Windows x64**, inspirados no
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf),
de Joseph Ravichandran e Mengjia Yan. O registro da pesquisa inclui protocolos
definidos previamente, traços de medição brutos, controles pareados, hashes
dos executáveis e análises que podem ser reproduzidas.

Os estudos no Windows medem uma resposta de cache repetível e sensível
à sequência de treinamento. Os controles de dependência e as intervenções
no codificador testam quais mudanças a suprimem.

[Relatório de pesquisa](../../RESEARCH_REPORT.md) · [Resultados e dados](../../results/k7-k8-windows-causal/README.md) · [Guia de reprodução](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Próximos estudos](../../RESEARCH_ROUTE.md)

## Resultados

| Estudo | Replicação | Resultado | Registro |
|---|---|---|---|
| K3: receptor novo | Um processo | Inconclusivo: 56/58 critérios de controle; os controles negativos falharam | [K3](../../results/k3-fresh-windows/README.md) |
| K4: controle de contexto | Piloto e três processos de acompanhamento | 58/58 critérios em cada um; a resposta se repete | [K4](../../results/k4-context-windows/README.md) |
| K5: controle de dependência | Três inicializações do Windows | 1,179,648 episódios; 88/88 critérios em cada tentativa | [K5](../../results/k5-windows-replication/README.md) |
| K7: dependência com controle pareado | Três novos processos em uma única sessão do sistema | 140/140 critérios em cada um; os critérios principais com condição fria são atendidos | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8: intervenções no codificador | Três novos processos nessa mesma sessão | 140/140 critérios em cada um; os critérios de intervenção na resposta pública são atendidos | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6: teste de privilégios | Teste funcional de software no QEMU TCG | Verificações CPL/PC aprovadas; coleta em hardware físico pendente | [K6](../../results/k5-k6-development/README.md) |

K7/K8 contêm **983,040 episódios**, incluindo 491,520 reservados para
validação. A replicação é avaliada entre processos; episódios de um mesmo
processo compartilham as condições daquela execução.

## Efeitos da dependência e do codificador

No desfecho primário p0 com a linha de condição fria, o contraste
sham-minus-true-mask é de +99.902, +99.707 e +99.414 pontos percentuais
nas três repetições. Os intervalos plain-minus-sham ficam dentro da margem
de equivalência predefinida de +/-10 pp. Remover a leitura do codificador
no banco consultado ou redirecionar ambas as leituras do codificador suprime
a resposta pública. Remover apenas a leitura do outro banco a preserva.

![Efeitos da dependência e do codificador em três repetições](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Os pontos mostram estimativas por processo; as barras mostram intervalos
complementares de 95% por bootstrap por conglomerados dentro de cada execução.
Os [18 intervalos dos contrastes primários](../../results/k7-k8-windows-causal/endpoint-table.csv)
usam a regra de Bonferroni fixada, aproximadamente 99.17% por desfecho.
Cada família de seis contrastes cobre um par de repetições programado.
Os contrastes ajustados podem ultrapassar 100 pp.*

No controle exploratório p0 com a linha de condição quente, a variante
sham reduz a frequência de acertos de cache em 14.16–16.31 pp. Portanto,
a equivalência na condição fria é específica desse desfecho primário.

<details>
<summary>Controle com condição quente</summary>

![Contagens exploratórias de plain e sham com condição quente](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Contagens descritivas da condição quente complementar, fora dos seis
contrastes primários.

</details>

## Reproduzir os resultados

Use Python 3.10+ e sua biblioteca padrão para conferir os limiares,
as contagens por célula, os critérios de controle e as estimativas pontuais
primárias a partir do arquivo original:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

O [guia de reprodução](../../results/k7-k8-windows-causal/REPRODUCE.md)
descreve como repetir a análise exatamente, gerar os gráficos e inspecionar
o código. Os arquivos originais e seus hashes acompanham cada resultado.
A [validação de software](https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml)
verifica os dados de teste das análises, o código-fonte gerado e a documentação.

Os estudos concluídos mantêm seus planos e revisões de código-fonte fixados.
Uma nova coleta começa com um novo plano. A coleta no Windows exige
MSVC x64 Build Tools e um Windows SDK.

## Reanálise dos dados dos autores do Fractal

A [reanálise do artefato M1](../../results/fractal-author-data-reanalysis/README.md)
verifica **48 traços e 240,192 linhas publicadas** das medições disponibilizadas
por Ravichandran e Yan. JSON, CSV e figuras estão disponíveis junto com
o registro de procedência e licenças do artefato.

## Contexto das medições

Os coletores do Windows são executados em modo usuário. K5 abrange três
inicializações em uma mesma estação de trabalho. K7/K8 usam três processos
por estudo, com apenas uma inicialização do sistema, e registram a presença
de um hipervisor e o estado do VBS. As intervenções se aplicam durante
o treinamento e a sondagem; o controle com bancos privados observa
a resposta pública.

Os tempos dos sensores K7/K8 ocorrem em múltiplos de 47 unidades do contador
TSC e permitem classificações calibradas de cache. O preditor exato, o caminho
de execução transitória e a influência física do modo usuário sobre o kernel
continuam sendo questões em aberto.
A página [Próximos estudos](../../RESEARCH_ROUTE.md) descreve as rotas de coleta
em Linux nativo e com Fractal em hardware físico.

## Arquivos do projeto

| Caminho | Conteúdo |
|---|---|
| [`programs/`](../../programs/) | Coletores em C e pontos de medição em assembly |
| [`protocols/`](../../protocols/) | Planos de coleta e regras de análise |
| [`scripts/`](../../scripts/) | Ferramentas de coleta, análise e procedência |
| [`tests/`](../../tests/) | Dados de teste de software e testes de regressão |
| [`results/`](../../results/) | Evidências brutas, tabelas numéricas e figuras |

## Citação

Mantido por [Tymoteusz Netter](https://github.com/xShadyy).
Cite este software com [CITATION.cff](../../CITATION.cff).

> Joseph Ravichandran e Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Artigo](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Artefato de pesquisa](https://doi.org/10.5281/zenodo.19556693)

O código do projeto usa a [licença MIT](../../LICENSE). Os componentes
de outros projetos e o artefato dos autores mantêm suas respectivas
licenças e atribuições.
