<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="Licence : MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <strong>Français</strong> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

Expériences sur la prédiction de branchement et la mémoire cache sur un
**AMD Ryzen 7 9800X3D sous Windows x64**, inspirées de
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf),
de Joseph Ravichandran et Mengjia Yan. Le dossier de recherche comprend des
protocoles définis à l'avance, des traces brutes, des contrôles appariés,
les empreintes des exécutables et des analyses reproductibles.

Les études Windows mesurent une réponse du cache répétable et sensible
à la séquence d'entraînement. Les contrôles de dépendance et les interventions
sur l'encodeur testent les modifications qui la suppriment.

[Rapport de recherche](../../RESEARCH_REPORT.md) · [Résultats et données](../../results/k7-k8-windows-causal/README.md) · [Guide de reproduction](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Études suivantes](../../RESEARCH_ROUTE.md)

## Résultats

| Étude | Réplication | Résultat | Dossier |
|---|---|---|---|
| K3 : nouveau récepteur | Un processus | Non concluant : 56/58 critères de contrôle ; échec des contrôles négatifs | [K3](../../results/k3-fresh-windows/README.md) |
| K4 : contrôle du contexte | Étude pilote et trois processus de suivi | 58/58 critères dans chaque cas ; la réponse se reproduit | [K4](../../results/k4-context-windows/README.md) |
| K5 : contrôle de dépendance | Trois démarrages Windows | 1,179,648 épisodes ; 88/88 critères à chaque tentative | [K5](../../results/k5-windows-replication/README.md) |
| K7 : dépendance avec contrôle apparié | Trois nouveaux processus sans redémarrage | 140/140 critères dans chaque cas ; critères principaux à froid satisfaits | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8 : interventions sur l'encodeur | Trois nouveaux processus dans cette même session | 140/140 critères dans chaque cas ; critères d'intervention sur la réponse publique satisfaits | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6 : test de privilèges | Test fonctionnel logiciel sous QEMU TCG | Vérifications CPL/PC réussies ; collecte sur matériel physique en attente | [K6](../../results/k5-k6-development/README.md) |

K7/K8 comprennent **983,040 épisodes**, dont 491,520 épisodes réservés
à la validation. La réplication est évaluée entre processus ; les épisodes
d'un même processus partagent les conditions de la même exécution.

## Effets des dépendances et de l'encodeur

Pour le critère principal p0 avec une ligne de condition froide, le contraste
sham-minus-true-mask vaut +99.902, +99.707 et +99.414 points de pourcentage
sur les trois répétitions. Les intervalles plain-minus-sham restent dans la
marge d'équivalence prédéfinie de +/-10 pp. Supprimer la lecture de l'encodeur
dans la banque interrogée ou rediriger les deux lectures de l'encodeur supprime
la réponse publique. Supprimer uniquement la lecture dans l'autre banque
préserve cette réponse.

![Effets des dépendances et de l'encodeur sur trois répétitions](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Les points représentent les estimations par processus ; les barres indiquent
les intervalles complémentaires à 95% issus d'un bootstrap par blocs au sein
d'une exécution. Les [18 intervalles des contrastes principaux](../../results/k7-k8-windows-causal/endpoint-table.csv)
suivent la règle de Bonferroni figée, soit environ 99.17% par critère.
Chaque famille de six contrastes couvre une paire de répétitions planifiée.
Les contrastes ajustés peuvent dépasser 100 pp.*

Dans le contrôle exploratoire p0 avec une ligne de condition chaude, la variante
sham réduit la fréquence des accès servis par le cache de 14.16–16.31 pp.
Le résultat d'équivalence à froid est donc propre à ce critère principal.

<details>
<summary>Contrôle avec une ligne de condition chaude</summary>

![Comptages exploratoires plain et sham avec une ligne de condition chaude](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Comptages descriptifs du contrôle complémentaire à chaud, en dehors des
six contrastes principaux.

</details>

## Reproduire les résultats

Avec Python 3.10+ et sa bibliothèque standard, vérifiez à nouveau les seuils,
les comptages par cellule, les critères de contrôle et les estimations
ponctuelles principales à partir de l'archive originale :

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

Le [guide de reproduction](../../results/k7-k8-windows-causal/REPRODUCE.md)
décrit la réexécution exacte de l'analyse, la génération des graphiques et
l'inspection du code. Chaque résultat est accompagné des archives originales
et de leurs empreintes. La [validation logicielle](https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml)
vérifie les jeux de test de l'analyse, le code source généré et la documentation.

Les études terminées conservent leurs plans et révisions de code source figés.
Toute nouvelle collecte commence par un nouveau plan. La collecte sous Windows
nécessite MSVC x64 Build Tools et un Windows SDK.

## Réanalyse des données des auteurs de Fractal

La [réanalyse de l'artefact M1](../../results/fractal-author-data-reanalysis/README.md)
vérifie **48 traces et 240,192 lignes publiées** provenant des mesures diffusées
par Ravichandran et Yan. JSON, CSV et figures sont disponibles avec le dossier
de provenance et de licence de l'artefact.

## Contexte des mesures

Les collecteurs Windows s'exécutent en mode utilisateur. K5 couvre trois
démarrages sur une même station de travail. K7/K8 utilisent trois processus
par étude sans redémarrage, avec la présence d'un hyperviseur et l'état VBS
consignés. Les interventions s'appliquent à l'entraînement comme au sondage ;
le contrôle utilisant les banques privées observe la réponse publique.

Les temps des capteurs K7/K8 sont des multiples de 47 unités du compteur TSC
et permettent une classification calibrée des accès au cache. Le prédicteur
exact, le chemin d'exécution transitoire et l'influence physique du mode
utilisateur sur le noyau restent des questions ouvertes.
Le document [Études suivantes](../../RESEARCH_ROUTE.md) décrit les voies de collecte
sous Linux natif et avec Fractal sur matériel physique.

## Fichiers du projet

| Chemin | Contenu |
|---|---|
| [`programs/`](../../programs/) | Collecteurs C et sites de mesure en assembleur |
| [`protocols/`](../../protocols/) | Plans de collecte et règles d'analyse |
| [`scripts/`](../../scripts/) | Outils de collecte, d'analyse et de traçabilité |
| [`tests/`](../../tests/) | Jeux de test logiciels et tests de non-régression |
| [`results/`](../../results/) | Données brutes, tableaux numériques et figures |

## Citation

Projet maintenu par [Tymoteusz Netter](https://github.com/xShadyy).
Citez ce logiciel à l'aide de [CITATION.cff](../../CITATION.cff).

> Joseph Ravichandran et Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Article](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Artefact de recherche](https://doi.org/10.5281/zenodo.19556693)

Le code du projet est sous [licence MIT](../../LICENSE). Les composants amont
et l'artefact des auteurs conservent leurs licences et mentions d'attribution
respectives.
