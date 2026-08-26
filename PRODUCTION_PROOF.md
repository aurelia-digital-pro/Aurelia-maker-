# إثبات القبول الإنتاجي — AURELIA Maker

## الحكم النهائي

**PASS — اجتاز المحرك العام مسار الإنتاج الحقيقي من Browser Chat إلى FINAL MP4.** تم التحقق من النتيجة على الفيديو الفعلي، وليس على السجلات أو الاختبارات وحدها.

## مسار التحقق

أُرسل السيناريو من واجهة Browser Chat الحقيقية على `http://127.0.0.1:8765/`. كان النص الموجود في Browser Chat هو المدخل الإنتاجي authoritative، ثم مر عبر المسار canonical التالي:

> Browser Chat → `/api/chat` → Chat Entry → Factory Runner → Production Pipeline → FINAL MP4 → Chat player/download

معرّف الحلقة الاختبارية: `0204`  
معرّف job: `2fea4cb7ed92493da5008aa1031d8719`  
ملف الإدخال المحفوظ من Chat: `output/.chat_inputs/episode-0204-7ff231c6431c4e98b9ecd55296dddd4a.txt`  
ملف التسليم: `output/episode-0204/job-2fea4cb7ed92493da5008aa1031d8719/delivery/episode-0204-FINAL.mp4`

عرض Browser Chat حالة `0204 — COMPLETED (100%)`، ومشغل الفيديو، ورابط `Download FINAL MP4`. فحص عنصر الفيديو داخل الصفحة أعاد `readyState=4` ومدة `113.045s`، وكان مصدر المشغل ورابط التنزيل يشيران إلى endpoint `/api/jobs/2fea4cb7ed92493da5008aa1031d8719/video`.

## خصائص FINAL MP4

| البوابة | النتيجة الفعلية |
|---|---|
| SHA-256 | `9b17532d54e1c8f38b572022f44c1df79f5a4d7514ac79a7feb4e5f38cd511a0` |
| الحجم | `70,652,497` bytes |
| الحاوية | MP4 / probe score 100 |
| الفيديو | H.264 High, `1920x1080`, progressive, `24 fps`, `113.041667s` |
| الصوت | AAC LC, stereo, `48 kHz`, `113.045s` |
| full decode | نجح، return code `0`، بلا أخطاء |
| freezedetect | نجح بالمرشح `freezedetect=n=-60dB:d=0.5`، بلا freeze durations |
| visual variation | نجح؛ minimum diff `0.1053734341` مقابل threshold `0.005` |
| run_qc الرسمي | `passed=true`، بلا FATAL وبلا WARNING |

أُعيد تشغيل `run_qc` الرسمي على ملف الإدخال authoritative من Browser Chat مع `require_audio_quality=True`. اجتازت جميع البوابات: وجود الملف، الحاوية، الفيديو، الصوت، المدة، الدقة، معدل الإطارات، الترميز، full decode، freeze frames، temporal variation، visual variation، loudness، true peak، clipping، subtitle completeness، narration، black frames، A/V duration، وA/V sync.

## المصدر البصري والاستمرارية

| العنصر | الدليل الفعلي |
|---|---|
| مزود الصور | `cloud-api/pollinations` لكل الأصول الـ24 |
| Pillow fallback | `0` |
| الأصول البصرية | `24` صورة مولدة فعليًا |
| depth assets | `24` ملفًا |
| cinematic treatments | `24` treatment موثقًا |
| الانتقالات | `19` انتقالًا عبر `24` لقطة |
| البيئات المخططة | `space`, `abstract`, `home`, `laboratory`, `city`, `ocean` |
| provenance | مسجل في `production_manifest.json` و`visual_manifest.json` |

أظهر الفحص البصري لـ12 إطارًا ممثلًا من FINAL، مع contact sheet للأصول الخام، فضاءً عميقًا، غرفة تخطيط دافئة خالية من الأشخاص، مختبرًا تقنيًا أزرق، شارع مدينة ممطرًا عند الغروب، ومحيطًا متحركًا. ظهرت المدينة والمحيط كمشهدين منفصلين بعد إصلاح planner العام. لم تظهر وجوه أو نساء أو شخصيات عشوائية في الإطارات الممثلة، كما لم تظهر واجهة أو prompt أو provider text داخل الصورة. حافظت المعالجة النهائية على اختلافات اللون بين المشاهد بدل تحويل parallax إلى magenta/grayscale؛ وقد تم التحقق من ذلك على الفيديو الفعلي بعد الإصلاح، لا من metadata فقط.

## الصوت والترجمة

| العنصر | النتيجة الفعلية |
|---|---|
| السرد | Edge TTS، الصوت `ar-SA-HamedNeural`، اللغة `ar`، fallback=false، مدة `113.04s` |
| integrated loudness | `-16.1 LUFS`، ضمن الهدف `-16.0` |
| true peak | `-3.7 dBFS`، تحت الحد `-1.5 dBFS` |
| sample peak | `-3.684015 dBFS`، بلا clipping |
| SRT | `18` cue، `2534` bytes، اجتاز completeness وword coverage |
| العرض | bottom-centered safe area؛ لا يحجب الموضوعات البيئية الأساسية في الإطارات المفحوصة |

## إصلاحات المحرك الموثقة

أُصلحت ثلاث عيوب عامة ظهرت من فحص إنتاج حقيقي. أولًا، أصبح prompt البيئي يقدّم البيئة والأشياء والـshot detail والـpalette والـtreatment والـdepth ضمن core لا يُحذف بالـtoken budget، مع إزالة عبارات النفي التي كانت تعيد تحفيز صور portrait في المشاهد غير البشرية. ثانيًا، أُضيف negative prompt ديناميكي لمسار Stable Diffusion المحلي عندما لا يطلب السيناريو شخصًا صراحة. ثالثًا، أصبح parallax يستخدم `yuv444p` قبل `maskedmerge` للحفاظ على chroma، مع regression يثبت اللون وعدم التجمد. وأخيرًا، أصبح planner يحافظ على الجمل السردية كوحدات مشهد مستقلة عندما يسمح `max_scenes`، فلا تُدمج بيئتان مختلفتان مثل المدينة والمحيط في مشهد واحد.

## الاختبارات وGitHub

نجحت suite المستودع الكاملة: **56 passed, 7 warnings**. التحذيرات خارجية ومحصورة في deprecation warnings من pydub/Pillow، ولم تفشل أي بوابة. كما نجحت الاختبارات المركزة الخاصة بـplanner وcinematic/parallax والحركة والـvisual preflight.

التنفيذ الإنتاجي النهائي تم من commit الكود:

`a4eb9d100e619d79dd635bfcdf319780eb7d4d2a`

تم التحقق مباشرة من GitHub API أن `origin/main` يطابق هذا الـSHA قبل commit وثيقة الإثبات. لا يحتوي المستودع على MP4 أو contact sheets المولدة؛ تبقى الأدلة الثقيلة خارج Git، بينما تحفظ هذه الوثيقة المسارات والـhashes والنتائج القابلة للتدقيق.

## النتيجة

المحرك اجتاز بوابة القبول لهذا التحقق العام: **Browser Chat → فهم السيناريو → تخطيط مشاهد وبيئات مستقلة → توجيه بصري → Pollinations حقيقي → depth/parallax وحركة وانتقالات → Edge Arabic narration → audio mix → subtitles → mastering → QC → FINAL MP4**.
