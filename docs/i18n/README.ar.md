<p align="center" dir="ltr">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center" dir="ltr">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="الترخيص: MIT"></a>
</p>

<p align="center" dir="ltr">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <strong>العربية</strong> · <a href="README.nl.md">Nederlands</a>
</p>

<div dir="rtl" align="right">

# Fractal x86

تجارب على التنبؤ بالتفرعات والذاكرة المخبئية باستخدام **معالج AMD Ryzen 7 9800X3D
يعمل بنظام Windows x64**، مستوحاة من ورقة
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
لجوزيف رافيتشاندران ومنغجيا يان.

تقيس دراسات Windows استجابة قابلة للتكرار في الذاكرة المخبئية تتأثر بالتدريب.
وتختبر ضوابط الاعتماد على البيانات والتدخلات في المُرمِّز التغييرات التي تكبح
هذه الاستجابة.

[النتائج والبيانات](../../results/k7-k8-windows-causal/README.md) · [دليل إعادة الإنتاج](../../results/k7-k8-windows-causal/REPRODUCE.md)

## النتائج

| الدراسة | التكرار | النتيجة | السجل |
|---|---|---|---|
| K3: مستقبِل جديد | عملية واحدة | غير حاسمة: 56/58 من معايير التحقق؛ لم تجتز الضوابط السلبية | [K3](../../results/k3-fresh-windows/README.md) |
| K4: ضبط السياق | عملية أولية وثلاث عمليات متابعة | اجتياز 58/58 من معايير التحقق في كل عملية؛ تتكرر الاستجابة | [K4](../../results/k4-context-windows/README.md) |
| K5: ضبط الاعتماد على البيانات | ثلاث عمليات إقلاع لنظام Windows | 1,179,648 حلقة قياس؛ اجتياز 88/88 من معايير التحقق في كل محاولة | [K5](../../results/k5-windows-replication/README.md) |
| K7: اعتماد متناظر على البيانات | ثلاث عمليات جديدة خلال إقلاع واحد | اجتياز 140/140 من معايير التحقق في كل عملية؛ تحققت المعايير الأساسية في الحالة الباردة | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8: تدخلات في المُرمِّز | ثلاث عمليات جديدة خلال الإقلاع نفسه | اجتياز 140/140 من معايير التحقق في كل عملية؛ تحققت معايير التدخل في استجابة البنك العام | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6: اختبار مستويات الامتياز | اختبار برمجي وظيفي قصير باستخدام QEMU TCG | اجتياز فحوص CPL/PC؛ لا يزال جمع البيانات على العتاد الفعلي معلقًا | [K6](../../results/k5-k6-development/README.md) |

تتضمن K7/K8 **983,040 حلقة قياس**، منها 491,520 حلقة محجوزة للتقييم.
يُقيَّم التكرار بين العمليات؛ أما الحلقات داخل العملية الواحدة فتشترك في ظروف
التشغيل نفسها.

## أثر الاعتماد على البيانات وتدخلات الترميز

عند المقياس الأساسي p0 في الحالة الباردة، يبلغ الفارق «القناع الشكلي ناقص
القناع الحقيقي» <bdi dir="ltr">+99.902</bdi> و<bdi dir="ltr">+99.707</bdi>
و<bdi dir="ltr">+99.414</bdi> نقطة مئوية عبر التكرارات الثلاثة.
وتقع فترات الفارق الناتج عن طرح `sham` من `plain` ضمن هامش التكافؤ المحدد
مسبقًا، وقدره <bdi dir="ltr">+/-10 pp</bdi>. تؤدي إزالة تعليمة التحميل الخاصة
بالبنك المستعلَم عنه في المُرمِّز، أو إعادة توجيه تعليمتَي التحميل معًا، إلى
كبح الاستجابة في البنك العام. وتبقى الاستجابة عند إزالة تعليمة التحميل الخاصة
بالبنك الآخر وحده.

في الضبط الاستكشافي p0 للحالة الدافئة، يخفض القناع الشكلي نسبة الإصابات بمقدار
<bdi dir="ltr">14.16–16.31 pp</bdi>. لذا تخص نتيجة التكافؤ في الحالة الباردة
ذلك المقياس الأساسي تحديدًا.

![أثر الاعتماد على البيانات وتدخلات الترميز عبر ثلاثة تكرارات](../../results/k7-k8-windows-causal/windows-causal-responses.png)

<details>
<summary>ضبط الحالة الدافئة</summary>

![أعداد استكشافية لوضعَي plain وsham في الحالة الدافئة](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

</details>

## إعادة الإنتاج

استخدم Python 3.10+ ومكتبته القياسية لإعادة التحقق من العتبات، وأعداد الخلايا،
ومعايير التحقق، والتقديرات النقطية الأساسية من الأرشيف الأصلي:

<div dir="ltr" align="left">

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

</div>

يغطي [دليل إعادة الإنتاج](../../results/k7-k8-windows-causal/REPRODUCE.md) إعادة
تنفيذ التحليل بدقة، وإنشاء الرسوم البيانية، وفحص الشيفرة. وترافق كل نتيجة
الأرشيفات الأصلية وبصمات التجزئة.

## إعادة تحليل بيانات مؤلفَي Fractal

تتحقق [إعادة تحليل مادة M1 البحثية](../../results/fractal-author-data-reanalysis/README.md)
من **48 سجل تتبع و240,192 صفًا منشورًا** من القياسات التي أتاحها رافيتشاندران
ويان. وتتوفر ملفات JSON وCSV والرسوم مع سجل مصدر المادة البحثية وترخيصها.

## سياق القياس

تعمل برامج جمع القياسات على Windows في وضع المستخدم.
تشمل K5 ثلاث عمليات إقلاع على محطة عمل واحدة. وتستخدم K7/K8 ثلاث عمليات لكل
دراسة خلال إقلاع واحد، مع توثيق وجود مراقب الأجهزة الافتراضية وحالة VBS.
وتُطبَّق تدخلاتهما أثناء التدريب والقياس معًا؛ ويرصد ضبط البنك الخاص الاستجابة
في البنك العام.

تأتي أزمنة مستشعرات K7/K8 بمضاعفات 47 نبضة TSC، وتدعم تصنيف حالات الذاكرة
المخبئية بعد المعايرة. ولا تزال هوية المتنبئ الدقيقة، ومسار التنفيذ العابر،
والتأثير الفعلي من وضع المستخدم إلى وضع النواة مسائل مفتوحة.
## الاستشهاد

يتولى [Tymoteusz Netter](https://github.com/xShadyy) صيانة المشروع.
للاستشهاد بهذا البرنامج، استخدم [CITATION.cff](../../CITATION.cff).

<div dir="ltr" align="left">

> Joseph Ravichandran and Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [الورقة](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [نظام Fractal](https://github.com/jprx/fractal)
> · [المادة البحثية](https://doi.org/10.5281/zenodo.19556693)

</div>

تُرخَّص شيفرة المشروع بموجب [ترخيص MIT](../../LICENSE). وتحتفظ المكونات
المستمدة من المشروع الأصلي ومادة المؤلفين البحثية بتراخيصها ونسبتها إلى أصحابها.

</div>
