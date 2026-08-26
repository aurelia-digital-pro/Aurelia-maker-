# إثبات القبول الإنتاجي — AURELIA Maker

## الحكم النهائي

**PASS — اجتاز محرك AURELIA Maker اختبار القبول الحقيقي بعد إصلاح مسار TTS العربي.** تم تنفيذ السيناريو من Browser Chat الحقيقي حتى FINAL MP4، ثم فُحصت النتيجة تقنيًا وبصريًا وصوتيًا. لم يكتفِ التحقق بنجاح اختبارات Python أو بوجود ملف MP4.

## سبب عطل TTS وتشخيصه

كانت رسالة الفشل السابقة هي `TTS: all dialogue segments failed`. عند فحص تاريخ Git، ظهرت هذه الرسالة في مسار TTS القديم الذي كان يقسم النص إلى dialogue segments، يبتلع الاستثناءات داخل كل segment، ثم يعرض رسالة عامة بلا سبب subprocess أو timeout أو encoding أو ملف مؤقت. أما مسار الإنتاج الحالي في `EpisodeProduction` فيستخدم `EdgeTTSProvider` مباشرة، ولذلك لا ينبغي أن يعيد إدخال هذا المسار القديم أو أن يتجاوز TTS صامتًا.

تم فحص البيئة الحالية فعليًا: executable `edge-tts` موجود بإصدار `7.2.8`، وتمت إعادة تجربة النص العربي الكامل بنجاح مع الصوت `ar-SA-HamedNeural` وبدون fallback. وبذلك لم يكن الحل تغيير رسالة الخطأ أو تجاوز narration؛ الإصلاح المطبق جعل مسار Edge أكثر قابلية للتشخيص، وحافظ على الفشل الصارم عند وجود مشكلة حقيقية.

## الإصلاحات العامة

أصبح Edge TTS يحتفظ بتاريخ كل محاولة، ويميز بوضوح بين timeout، وخروج subprocess غير صفري، وفشل تحويل WAV عبر FFmpeg، وفشل الملف الناتج أو probe. تظهر المحاولة والسبب الفعلي في الاستثناء النهائي بدل ابتلاع الخطأ. كما أصبحت ملفات Edge المؤقتة تُنشأ داخل مجلد إخراج الوجهة نفسها، لتفادي فشل `os.replace` الناتج عن اختلاف filesystem بين `/tmp` وvolume الإخراج. بقيت سياسة production كما هي: Edge Neural إلزامي، وfallback المحلي لا يُسمح به في production acceptance.

أضيفت regression tests لاختبار تسجيل timeout لكل محاولة، وضمان تمرير النص العربي الكامل إلى Edge TTS دون dialogue segmentation صامتة. لم يتغير مسار English TTS أو مراحل الصوت والمونتاج والـQC، وأُعيد اختبار مزوّد الصوت الإنجليزي أيضًا.

## Production Validation الحقيقي من Browser Chat

أُعيد تشغيل Browser Chat من commit الكود `175f6ca5dbd739a92cc751b5b9ccb45be28ed74d` مع `AURELIA_PRODUCTION_MODE=1` و`AURELIA_FORCE_FALLBACK=0`. أُرسل السيناريو العربي من واجهة `http://127.0.0.1:8765/` بعنوان:

> AURELIA Maker — A Cinematic Welcome to the World

كان نص Browser Chat هو المدخل authoritative، وحُفظ في:

`output/.chat_inputs/episode-0001-9dea25efd00941d9a7afd6a20173ccbe.txt`

ثم مر الطلب عبر المسار الكامل:

> Browser Chat → `/api/chat` → Chat Entry → Factory Runner → Script/Scene Planning → Visual Direction → Pollinations → Cinematic Motion → Edge TTS → Audio Mix → Subtitles → Edit → Color → Master → QC → Delivery → FINAL MP4

| دليل التكامل | النتيجة الفعلية |
|---|---|
| Episode | `0001` |
| Job ID | `29d002cbc08f46e68f1c029f991200ad` |
| Browser Chat | قبل الطلب، ثم عرض `COMPLETED (100%)` |
| خطة الإنتاج | 9 مشاهد، 23 لقطة |
| النتيجة في Chat | player و`Download FINAL MP4` |
| player readyState | `4` |
| مدة player | `115.882s` |
| endpoint | `/api/jobs/29d002cbc08f46e68f1c029f991200ad/video` |

## خصائص FINAL MP4

ملف التسليم هو:

`output/episode-0001/job-29d002cbc08f46e68f1c029f991200ad/delivery/episode-0001-FINAL.mp4`

| البوابة | النتيجة الفعلية |
|---|---|
| SHA-256 | `462fa5736abcadc46c68779168f76ed8156360b19fd4fb6068c1bcde539dd496` |
| الحجم | `72,635,861` bytes |
| الحاوية | MP4، probe score `100` |
| الفيديو | H.264 High، `1920×1080`، progressive، `24 fps`، `115.875s` |
| الصوت | AAC LC، stereo، `48 kHz`، `115.882s` |
| full decode | نجح، return code `0`، بلا أخطاء |
| freezedetect | نجح باستخدام `freezedetect=n=-60dB:d=0.5`، بلا freeze durations |
| visual variation | نجح؛ minimum diff `0.09248025599` مقابل threshold `0.005` |
| run_qc الرسمي | `passed=true`، بلا FATAL وبلا WARNING |
| مدة الإنتاج | أقل من دقيقتين كما طلبت المواصفة |

أُعيد تشغيل `run_qc` الرسمي على FINAL مع `require_audio_quality=True` وعلى ملف الإدخال المحفوظ من Browser Chat. اجتازت البوابات جميعها: وجود الملف، الحاوية، الفيديو، الصوت، المدة، الدقة، FPS، الترميز، full decode، freeze frames، temporal variation، visual variation، loudness، true peak، clipping، subtitle completeness، narration audibility، black frames، A/V duration، وA/V sync.

## مزودات الصورة والتوجيه السينمائي

| العنصر | النتيجة الفعلية |
|---|---|
| visual provider | `cloud-api/pollinations` لكل الأصول |
| الصور الحقيقية | 23 أصلًا مولدًا عبر API |
| Pillow fallback | `0` |
| depth assets | 23 |
| cinematic treatments | 23 |
| الانتقالات | 19 انتقالًا عبر 23 لقطة |
| البيئات | `space`, `home`, `abstract`, `laboratory`, `city`, `ocean` |
| provenance | محفوظ في `production_manifest.json` و`visual_manifest.json` |

تم فحص contact sheet يضم 12 إطارًا من FINAL، إضافة إلى contact sheet للأصول الخام الـ23. ظهرت بيئات الفضاء، غرفة التخطيط، المختبر، المدينة الممطرة، والمحيط بصورة متمايزة. ظهرت المدينة والمحيط كبيئتين مستقلتين، ولم تظهر وجوه أو نساء أو شخصيات عشوائية في الإطارات الممثلة، كما لم تظهر واجهة أو prompt أو provider text داخل الصورة. الألوان ليست معالجة أحادية ثابتة؛ فالداخل دافئ، والمختبر أزرق تقني، والمدينة ذات انعكاسات حضرية، والمحيط والفضاء لهما لوحات مختلفة. كما حافظ الفيديو على حركة كاميرا وانتقالات فعلية، وليس slideshow ثابتًا.

## الصوت والترجمة

| العنصر | النتيجة الفعلية |
|---|---|
| narration provider | `edge-tts` |
| Arabic voice | `ar-SA-HamedNeural` |
| اللغة | `ar` |
| fallback | `false` |
| Edge attempts | `1` |
| narration duration | `115.871973s` |
| integrated loudness | `-16.1 LUFS`، ضمن الهدف `-16.0` |
| true peak | `-3.7 dBFS`، تحت الحد `-1.5 dBFS` |
| sample peak | `-3.711774 dBFS`، بلا clipping |
| SRT | 21 cue، `2655` bytes، واكتمال ناجح |
| subtitle placement | bottom-centered safe area، بلا حجب للموضوع البيئي الرئيسي في الإطارات المفحوصة |
| music/ambient | provenance مسجل، وfallback=false |

## الاختبارات وGitHub

نجحت اختبارات TTS المركزة واختبارات provider adapters بنتيجة **7 passed, 7 warnings**. ثم نجحت suite المستودع الكاملة بنتيجة **58 passed, 7 warnings**. التحذيرات خارجية ومحصورة في Syntax/Deprecation warnings من pydub وPillow، ولم تفشل أي بوابة. مرّ `git diff --check`.

تم دفع إصلاح TTS إلى GitHub في commit:

`175f6ca5dbd739a92cc751b5b9ccb45be28ed74d`

وبعد ذلك تم دفع هذه الوثيقة نفسها إلى `main` بعد commit الكود المختبر `175f6ca5dbd739a92cc751b5b9ccb45be28ed74d`. وتم التحقق مباشرة بعد الدفع من SHA المستودع في GitHub ومن أن `local SHA = origin/main SHA`، مع بقاء شجرة العمل نظيفة. ويظهر commit التوثيق النهائي في سجل `main` على GitHub.

تم التحقق من أن شجرة العمل لا تحتوي تغييرات غير ملتزم بها، وأن `local SHA = origin/main SHA` بعد كل عملية دفع. لا يحتوي المستودع على MP4 أو contact sheets مولدة؛ تحفظ الوثيقة المسارات والـhashes والنتائج، بينما يبقى الفيديو المرفق خارج Git كartifact إنتاجي.

## النتيجة

اجتاز AURELIA Maker بوابة القبول المطلوبة: **Browser Chat → فهم السيناريو → تخطيط المشاهد → توجيه البيئات واللقطات → Pollinations الحقيقي → depth/parallax والحركة والانتقالات → Edge Arabic Neural narration → mix → subtitles → edit → color → master → QC → delivery → FINAL MP4**.
