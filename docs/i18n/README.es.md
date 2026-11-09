<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="Licencia: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <strong>Español</strong> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

Experimentos de predicción de saltos y caché en un **AMD Ryzen 7 9800X3D con
Windows x64**, inspirados en
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf),
de Joseph Ravichandran y Mengjia Yan.

Los estudios en Windows miden una respuesta de caché repetible y sensible
a la secuencia de entrenamiento. Los controles de dependencia y las
intervenciones en el codificador prueban qué cambios la suprimen.

[Resultados y datos](../../results/k7-k8-windows-causal/README.md) · [Guía de reproducción](../../results/k7-k8-windows-causal/REPRODUCE.md)

## Resultados

| Estudio | Replicación | Resultado | Registro |
|---|---|---|---|
| K3: receptor nuevo | Un proceso | No concluyente: 56/58 criterios de control; fallaron los controles negativos | [K3](../../results/k3-fresh-windows/README.md) |
| K4: control de contexto | Piloto y tres procesos de seguimiento | 58/58 criterios en cada uno; la respuesta se repite | [K4](../../results/k4-context-windows/README.md) |
| K5: control de dependencia | Tres arranques de Windows | 1,179,648 episodios; 88/88 criterios en cada intento | [K5](../../results/k5-windows-replication/README.md) |
| K7: dependencia con control emparejado | Tres procesos nuevos sin reiniciar el sistema | 140/140 criterios en cada uno; se cumplen los criterios principales con la condición fría | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8: intervenciones en el codificador | Tres procesos nuevos en esa misma sesión | 140/140 criterios en cada uno; se cumplen los criterios de intervención sobre la respuesta pública | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6: prueba de privilegios | Prueba funcional de software en QEMU TCG | Se superan las comprobaciones CPL/PC; pendiente la recogida en hardware físico | [K6](../../results/k5-k6-development/README.md) |

K7/K8 contienen **983,040 episodios**, incluidos 491,520 reservados para
validación. La replicación se evalúa entre procesos; los episodios de un
mismo proceso comparten las condiciones de esa ejecución.

## Efectos de la dependencia y del codificador

En el criterio principal p0 con la línea de condición fría, el contraste
sham-minus-true-mask es de +99.902, +99.707 y +99.414 puntos porcentuales
en las tres repeticiones. Los intervalos plain-minus-sham quedan dentro del
margen de equivalencia predefinido de +/-10 pp. Suprimir la lectura del
codificador en el banco consultado o redirigir ambas lecturas del codificador
suprime la respuesta pública. Suprimir solo la lectura del otro banco
la conserva.

En el control exploratorio p0 con la línea de condición caliente, la variante
sham reduce la frecuencia de aciertos de caché en 14.16–16.31 pp. Por tanto,
el resultado de equivalencia en la condición fría es específico de ese criterio principal.

![Efectos de la dependencia y del codificador en tres repeticiones](../../results/k7-k8-windows-causal/windows-causal-responses.png)

<details>
<summary>Control con la condición caliente</summary>

![Recuentos exploratorios de plain y sham con la condición caliente](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

</details>

## Reproducir los resultados

Usa Python 3.10+ y su biblioteca estándar para volver a comprobar los umbrales,
los recuentos por celda, los criterios de control y las estimaciones puntuales
principales a partir del archivo original:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

La [guía de reproducción](../../results/k7-k8-windows-causal/REPRODUCE.md)
explica cómo repetir exactamente el análisis, generar los gráficos e inspeccionar
el código. Los archivos originales y sus hashes acompañan a cada resultado.

## Reanálisis de los datos de los autores de Fractal

El [reanálisis del artefacto M1](../../results/fractal-author-data-reanalysis/README.md)
comprueba **48 trazas y 240,192 filas publicadas** de las mediciones difundidas
por Ravichandran y Yan. Hay JSON, CSV y figuras junto con el registro de
procedencia y licencias del artefacto.

## Contexto de las mediciones

Los recolectores de Windows se ejecutan en modo usuario. K5 abarca tres
arranques en una misma estación de trabajo. K7/K8 usan tres procesos por
estudio sin reiniciar el sistema, con la presencia de un hipervisor y el estado
de VBS registrados. Las intervenciones se aplican tanto durante el entrenamiento
como durante el sondeo; el control con bancos privados observa la respuesta pública.

Los tiempos de los sensores K7/K8 son múltiplos de 47 unidades del contador TSC
y permiten clasificaciones de caché calibradas. El predictor exacto, la ruta
de ejecución transitoria y la influencia física del modo usuario sobre
el núcleo del sistema siguen siendo cuestiones abiertas.

## Citas

Mantenido por [Tymoteusz Netter](https://github.com/xShadyy).
Cita este software mediante [CITATION.cff](../../CITATION.cff).

> Joseph Ravichandran y Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Artículo](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Artefacto de investigación](https://doi.org/10.5281/zenodo.19556693)

El código del proyecto usa la [licencia MIT](../../LICENSE). Los componentes
de otros proyectos y el artefacto de los autores conservan sus respectivas
licencias y atribuciones.
