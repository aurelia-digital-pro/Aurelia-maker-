# إثبات القبول الإنتاجي — AURELIA Maker

## الحكم النهائي

**PASS — اجتاز AURELIA Maker بوابة القبول الإنتاجي العام عبر Browser Chat بعد إصلاح موثوقية EDIT وإصلاح تصنيف البيئة العربي.** أُرسل سيناريو عربي عام من الواجهة الحقيقية، وقبله Chat، واستلمه Factory Runner، ثم مرّ عبر التخطيط والتوجيه البصري وتوليد الأصول والصوت والتحرير واللون والترجمة والـmaster وQC والتسليم حتى FINAL MP4 قابل للتشغيل. لم يعتمد الحكم على unit tests أو وجود ملف MP4 فقط؛ بل على job إنتاج حقيقي، وffprobe، وfull decode، وQC الرسمي، وفحص صوتي، وفحص بصري مستقل.

## نطاق المحرك والمسار المثبت

الاختبار يثبت المسار العام التالي، وليس مسارًا مخصصًا لفيلم أو مشهد ثابت:

> Browser Chat → Chat Entry → Factory Runner → Script/Scenario Understanding → Story & Scene Planning → Cinematic Directing → Pollinations visual generation → Shot/Motion/Camera/Depth treatments → Edge Arabic TTS → Sound/Music → Edit → Color → Subtitles → Master → QC → Delivery → FINAL MP4

كان نص Browser Chat هو المدخل authoritative المحفوظ في:

`output/.chat_inputs/episode-0003-*.txt`

وتكوّن الإنتاج تلقائيًا من **8 مشاهد و23 لقطة** في سيناريو عربي أقل من دقيقتين، شمل الفضاء وغرفة التخطيط والمختبر والمدينة الممطرة والمحيط والخاتمة المفاهيمية. لم يُستخدم Showcase workflow منفصل، ولم تُستدعَ دالة إنتاج داخلية بدل Chat.

## سبب عطل EDIT السابق والخطر المرتبط بـexit 124

كان خطر `exit code 124` ناتجًا عن التجميع المتسلسل للقطات: عند كل حد لقطة أو انتقال كان `assemble_cinematic_clips` يعيد ترميز ناتج جديد، فتتكون سلسلة O(n) من ملفات `.cinematic-step-*`. هذا يكرر قراءة وترميز المادة على امتداد الحدود، ويزيد الزمن واحتمال تجاوز غلاف GitHub Actions الخارجي `timeout 55m` والمهلة الإجمالية للوظيفة `60m`. كما أن طبقة تشغيل FFmpeg لم تكن تسجل مهلة أو مرحلة أو مدة أو ملفًا مسببًا عند التعثر.

لم يكن العلاج زيادة `timeout-minutes` فقط. في commit `3d96ce53b5e7511903c470ca9e025c4370d52ab8` أُعيد بناء EDIT ليستخدم **filter graph واحدًا single-pass** لكل اللقطات، مع تطبيق `xfade` فقط على الانتقالات غير-cut وتجميع حدود القطع داخليًا، بدل إعادة الترميز عند كل حد. وتتحقق المرحلة مسبقًا من وجود كل clip ومن video stream ومدته قبل تشغيل FFmpeg.

كما أصبحت `run_ffmpeg` و`run_ffprobe` في `aurelia/ffmpeg_util.py` محددتي المهلة وقابلتي الضبط عبر `AURELIA_FFMPEG_TIMEOUT_SECONDS` و`AURELIA_FFPROBE_TIMEOUT_SECONDS`، مع `-nostdin`. عند انتهاء المهلة تتضمن الرسالة stage وtimeout وelapsed وملف الإخراج والأمر وstderr، فتكون المشكلة قابلة للتشخيص بدل hang صامت.

## إصلاح تصنيف البيئة العربي

أظهر الفحص البصري لـ0002 أن الخاتمة المفاهيمية صُنّفت خطأً كبيئة نار. السبب كان مطابقة substring؛ إذ طابقت كلمة `نار` داخل `السيناريو`، كما أن `محرك` كانت keyword صناعية عامة غير مناسبة. في commit `136bf63830467289854cdce9bc19078e9d5cd5aa` أصبحت المطابقة العربية whole-token مع دعم بادئة `ال`، وأزيلت الكلمات العامة من تصنيف الصناعة. لذلك صُنّفت خاتمة 0003 فعليًا `abstract`، ولم تُنتج بيئة fire غير مطلوبة.

## Production Validation الحقيقي من Browser Chat

شُغّل الخادم من commit `136bf63830467289854cdce9bc19078e9d5cd5aa` مع `AURELIA_PRODUCTION_MODE=1` و`AURELIA_FORCE_FALLBACK=0`. أُرسل الطلب من Browser Chat بعنوان:

> AURELIA Maker — Cinema from Meaning

وظهرت في الواجهة رسالة قبول الحلقة وبدء المصنع، ثم الحالة `0003 — COMPLETED (100%)`، وظهر player ورابط `Download FINAL MP4`. endpoint التسليم هو:

`/api/jobs/5572834efd1d472c9a9e492593875547/video`

| دليل التكامل | النتيجة الفعلية |
|---|---|
| Episode | `0003` |
| Job ID | `5572834efd1d472c9a9e492593875547` |
| Browser Chat | قبل الطلب ثم عرض `COMPLETED (100%)` |
| Factory | استلم النص المحفوظ من Chat وشغّل المراحل canonical كلها |
| الخطة | 8 مشاهد، 23 لقطة، تقدير 55 ثانية قبل تمديد narration |
| التسليم في Chat | player و`Download FINAL MP4` |
| player | ظهر في Browser Chat بمدة معروضة تقارب 1:36 |
| النتيجة | `Episode 0003 complete! shots FINAL MP4 ready.` |

## دليل EDIT والمهلة

سجل الإنتاج المحفوظ في:

`output/episode-0003/job-5572834efd1d472c9a9e492593875547/production_5572834efd1d472c9a9e492593875547.ndjson`

يثبت أن EDIT بدأ عند `11:28:31.331414Z`، وسجل تطبيق **18 cinematic transitions across 23 shots** عند `11:33:13.155271Z`، ثم بدأ التجميع والمزج عند `11:33:13.155364Z`. بدأ COLOR عند `11:35:22.502455Z`؛ أي أن مرحلة التجميع والمزج من سجل `Editing` إلى COLOR استغرقت تقريبًا **129.35 ثانية**. اكتمل MASTER عند `11:36:22.067307Z`، وبدأ QC عند `11:39:23.126031Z`، ثم DELIVERY عند `11:39:41.350374Z`، واكتمل التسليم عند `11:39:42.476008Z`.

| دليل الاعتمادية | النتيجة |
|---|---|
| intermediate cinematic steps | لا توجد أي ملفات `.cinematic-step-*` |
| ملفات EDIT الطبيعية | `video_concat.mp4` و`video_padded.mp4` و`edit_mixed.mp4` فقط |
| transitions | 18 انتقالًا عبر 23 لقطة |
| timeout | لا يوجد `FFmpeg timeout` في سجل job |
| exit 124 | لم يحدث؛ job أكمل DELIVERY بنسبة 100% |
| مسار التنفيذ | filter graph single-pass، لا سلسلة إعادة ترميز لكل boundary |

## خصائص FINAL MP4 والتدقيق المستقل

ملف التسليم النهائي هو:

`output/episode-0003/job-5572834efd1d472c9a9e492593875547/delivery/episode-0003-FINAL.mp4`

والـSHA-256 هو:

`675ae3bf010271aafcc26630c29567e4d03053f37ba49268896e9115ef9374ce`

| البوابة | النتيجة الفعلية |
|---|---|
| الحجم | `60,387,378` bytes |
| الحاوية | MP4، probe score صالح |
| الفيديو | H.264، `1920×1080`، `24 fps`، مدة stream `96.833333s` |
| الصوت | AAC، stereo، `48 kHz`، مدة `96.853000s` |
| مدة الملف | `96.853s`، أقل من دقيقتين |
| full decode | return code `0`، بلا أخطاء |
| freezedetect | `freezedetect=n=-60dB:d=0.5`، بلا freeze durations |
| visual variation | `minimum diff = 0.05274373638` مقابل threshold `0.005` |
| run_qc الرسمي | `passed=true`، بلا FATAL وبلا WARNING |
| A/V sync | اجتاز QC |
| subtitle completeness | اجتازت QC |

أُعيد تشغيل التدقيق عبر `run_qc(..., require_audio_quality=True)` على FINAL مع ملف الإدخال authoritative المحفوظ من Browser Chat. شملت البوابات وجود الملف وحجمه، video/audio streams، المدة والدقة وFPS والترميز، full decode، freeze frames، temporal/visual variation، loudness، true peak، clipping، subtitle file/completeness، narration audibility، black frames، A/V duration وA/V sync؛ وجميعها اجتازت.

## مزودات الصورة والتوجيه السينمائي

| العنصر | النتيجة الفعلية |
|---|---|
| visual provider | `cloud-api/pollinations` لكل الأصول الـ23 |
| Pillow fallback | `0` |
| الأصول الحقيقية | 23 صورة جديدة مولدة عبر Cloud API، لا أصول resumed |
| depth assets | 23 |
| cinematic treatments | 8 معالجات مشهدية موثقة، مع توجيه لقطة/كاميرا لكل اللقطات |
| transitions | 18 |
| البيئات | `space`, `home`, `laboratory`, `city`, `ocean`, `abstract` |
| manifest | `visual_manifest.json` و`production_manifest.json` وstage artifacts محفوظة |

تؤكد المعاينة المستقلة لـ12 إطارًا من FINAL وcontact sheet للأصول الخام أن البيئات الموصوفة في السيناريو ظهرت فعليًا: فضاء، غرفة تخطيط دافئة، مختبر تقني أزرق، مدينة ممطرة، محيط، ثم معالجة مفاهيمية زرقاء/فيروزية. لا تظهر وجوه أو أشخاص في الإطارات المفحوصة، ولا تظهر واجهة debug أو نصوص provider أو prompts داخل الفيلم. كما أن اللون ليس monochrome واحدًا: الغرفة دافئة، المختبر بارد وتقني، المدينة ذات انعكاسات ومصابيح دافئة، والفضاء والمحيط والخاتمة لها لوحات مستقلة.

الخاتمة المفاهيمية هي `abstract` وليست `fire`، وهو دليل إنتاجي مباشر على أن إصلاح whole-token العربي منع false positive السابق. وتثبت خطة اللقطات وسجل `18 cinematic transitions` ووجود depth assets أن الناتج ليس slideshow ثابتًا. كما لم تسجل `freezedetect` مدد تجمد، واجتازت `visual_variation` العتبة الصارمة.

## الصوت والترجمة

| العنصر | النتيجة الفعلية |
|---|---|
| narration provider | `edge-tts` |
| Arabic voice | `ar-SA-HamedNeural` |
| اللغة | `ar` |
| fallback | `false` |
| degraded | `false` |
| attempts | `1` |
| narration duration | `96.816009s` |
| integrated loudness | `-16.2 LUFS`، ضمن الهدف |
| true peak | `-3.9 dBFS`، تحت الحد `-1.5 dBFS` |
| sample peak | `-3.87166 dBFS`، بلا clipping |
| SRT | 15 cue، واكتمال ناجح |
| subtitle placement | bottom-centered safe area، مقروء في الإطارات المفحوصة |
| audio QC | passed، بلا warnings أو fatals |

## الاختبارات والكود المدفوع

بعد إصلاح EDIT أصبحت suite المستودع **61 passed, 7 warnings**، ثم بعد إصلاح تصنيف البيئة أصبحت **62 passed, 7 warnings**. تشمل الاختبارات الجديدة رسالة timeout التفصيلية، رفض clip المفقود قبل FFmpeg، إثبات process واحدة للتجميع، نمط cut/dissolve/cut، وتصنيف العربية دون substring false positives. مرّ `git diff --check`، ولم تُضعف عتبات QC أو visual variation، ولم يُسمح بـPillow fallback في production acceptance.

الإصلاحان البرمجيان المدفوعان إلى `main` هما:

| commit | الغرض |
|---|---|
| `3d96ce53b5e7511903c470ca9e025c4370d52ab8` | جعل EDIT single-pass وFFmpeg/FFprobe timeout-aware |
| `136bf63830467289854cdce9bc19078e9d5cd5aa` | منع misclassification العربي بالـsubstring |

لا تُلتزم ملفات الفيديو أو contact sheets الكبيرة داخل Git؛ تحتفظ الوثيقة بمسار artifact والـhash وprovenance، بينما يبقى FINAL MP4 في مجلد الإنتاج المحلي ومتاحًا من Browser Chat.

## النتيجة

اجتاز AURELIA Maker بوابة القبول المطلوبة كمحرك إنتاج عام: **أي سيناريو يصل من Browser Chat يمر عبر الفهم والتخطيط والتوجيه البصري وتوليد الأصول الحقيقية والحركة والعمق والصوت والترجمة والتحرير واللون والـmaster وQC والتسليم حتى FINAL MP4**. أثبت job `5572834efd1d472c9a9e492593875547` المسار الفعلي بعد إصلاح سبب exit 124، وأثبتت المعاينة أن المشهد الختامي لم يعد يُصنف نارًا بسبب تطابق عربي خاطئ.
