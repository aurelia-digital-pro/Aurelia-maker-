# AURELIA Maker — إثبات التعافي والقبول الإنتاجي

## 1. ROOT CAUSE

فشل run السابق `32974171812` بعد أن وصل الإنتاج الحقيقي إلى `PRODUCTION_COMPLETE` و`DELIVERY 100%` وأنشأ الـFINAL MP4 ونتيجة QC. كان السبب دائرة اعتماد في state machine، وليس فشلًا في MASTER أو QC أو Delivery.

كان `FactoryRunner.run_episode_production()` يضع الوظيفة في `AWAITING_GITHUB_ACTIONS` ويكتب:

> `PRODUCTION_COMPLETE — awaiting GitHub Actions success for commit 553d2c6372147e129a59ce5c29ded2448f12998c`

ثم كان workflow نفسه ينتظر حالة `COMPLETED` فقط. لذلك ظل انتظار workflow قائمًا حتى انتهت مهلة العملية الداخلية، ثم رُفعت رسالة `RuntimeError: Production failed` بعد اكتمال الإنتاج. أصبح المسار فعليًا:

```text
GitHub Actions → Factory → PRODUCTION_COMPLETE
             ↖ انتظار نجاح GitHub Actions نفسه
```

وهذا هو deadlock الذي أنتج الفشل بعد نحو 54 دقيقة. لم يكن رفع `timeout-minutes` علاجًا صحيحًا.

## 2. FILES CHANGED

| الملف | التغيير |
|---|---|
| `aurelia/factory_runner.py` | جعل دورة المصنع مستقلة عن GitHub Actions؛ بعد validation النهائي يصبح job `COMPLETED` ويخرج بدل الانتظار أو polling على CI. |
| `aurelia/server.py` | جعل endpoint الفيديو يربط الجاهزية بـFactory validation، لا بشرط GitHub خارجي. |
| `web/app.js` | Browser Chat يعرض النتيجة بعد `COMPLETED` الفعلي من Factory، ولا يعلق على حالة انتظار CI. |
| `.github/workflows/production-e2e-test.yml` | workflow ينتظر `PRODUCTION_COMPLETE` أو `COMPLETED`، يرفض حالات الفشل، ويبقي proof المحلي مرشحًا `accepted=false` ثم يمنح القبول فقط بعد كل بوابات GitHub الحالية. |
| `aurelia/acceptance_authority.py` | الإبقاء على عقد إثبات GitHub اللاحق دون helper runtime يربط Factory بتشغيله الحالي. |
| `aurelia/visual_backend.py` | إضافة `shot_index` إلى logs وprovenance لإظهار هوية الطلب البصري بدقة. |
| `aurelia/episode_engine.py` | تمرير `shot_index` الحقيقي إلى provider في كلا مساري scene-with-shots وscene-without-shots. |
| `aurelia/visual_checkpoint.py` | التحقق من أن مسار الملف المحفوظ يطابق `expected_path` قبل اعتبار shot مكتملًا، إضافة إلى SHA والحجم. |
| `tests/unit/test_acceptance_authority.py` | اختبارات success/failure وworkflow gate وBrowser Chat completion المستقل. |
| `tests/unit/test_visual_checkpoint_and_dedup.py` | اختبارات uniqueness لكل shot، وإعادة استخدام cache، ورفض مسار checkpoint الخاطئ. |

الـcommit الذي يحتوي الإصلاح الجذري هو:

`ebbf6ff9cf2edf4cf3eb839162fb5b8a26d503e8`

وسبقته إصلاحات EDIT single-pass وFFmpeg timeout-aware في `3d96ce53b5e7511903c470ca9e025c4370d52ab8`، وإصلاح مطابقة البيئة العربية في `136bf63830467289854cdce9bc19078e9d5cd5aa`.

## 3. EXACT FIX

أصبح lifecycle الصحيح داخل Factory هو:

```text
SCRIPT → DEVELOPMENT → STORY → WORLD → CHARACTER → SERIES_BIBLE
→ RESEARCH → PRE_PRODUCTION → SEQUENCE → SCENE → SHOT → STORYBOARD
→ ANIMATIC → VISUAL → ASSET → CAMERA → DEPTH → MOTION → LIGHT
→ ATMOSPHERE → VFX → NARRATION → DIALOGUE → SOUND → MUSIC → EDIT
→ COLOR → SUBTITLE → MASTER → QC → DELIVERY
→ validate FINAL artifact → COMPLETED → process exit 0
```

بعد `DELIVERY` يتحقق Factory من وجود الـFINAL، وmaster validation، وvisual manifest validation، وQC المكتمل. عند نجاحها يكتب `job.status = "COMPLETED"` ويعيد النتيجة. لا توجد بعد ذلك قراءة لـ`GITHUB_ACTIONS`، ولا استدعاء لـ`gh`، ولا polling، ولا انتظار لنجاح العملية التي تشغّل Factory.

في المقابل، لا تزال حالات الاستثناء حقيقية: أي stage exception أو artifact مفقود أو فشل QC يمر عبر `execute()` إلى `job.status = "FAILED"` ويُعاد رفع exception، ولذلك لا يتحول failure إلى success.

داخل GitHub workflow يُنشأ proof أولي صراحة بحالة `accepted=false` و`acceptance_state=PRODUCTION_COMPLETE`. بعد ذلك تنفذ خطوات Hard artifact verification وmanifest/QC/hash checks، ثم يحدّث workflow proof إلى `accepted=true` و`acceptance_state=COMPLETED` و`github_conclusion=success`. بهذا تصبح GitHub Actions جهة التحقق الخارجية، لا dependency داخل Factory.

### تحليل تكرار Pollinations

أظهر السجل السابق رسائل متكررة من نوع `Scene N: cloud OK via pollinations`، لكن الكود كان ينفذ الحلقة على مستوى **shot**، بينما كانت الرسالة القديمة تعرض رقم scene فقط. كما أن `generate_via_api()` يستدعي Pollinations مرة واحدة لكل shot، ولا ينتقل إلى backend آخر إلا عند failure، بينما `_read_response_bytes()` يسمح بثلاث محاولات كحد أقصى عند timeout أو response ناقص؛ وهذا retry حقيقي ومحدود، وليس إعادة توليد بعد نجاح.

أكد التدقيق في call sites أن `EpisodeProduction.generate_visual_assets()` هو المسار البصري المستخدم من Factory، وأنه يستدعي `generate_visual()` مرة واحدة لكل `(scene_index, shot_index)`. لا يوجد استدعاء ثانٍ موازي أو تشغيل `run_all()` داخل Factory. لذلك لم يكن التكرار الناجح المؤكد في السجل إعادة توليد لنفس shot؛ كان الالتباس ناتجًا عن logging غير المميز بين shots.

الإصلاح العام كان إضافة `shot_index` إلى كل provider log وprovenance، مع تشديد checkpoint كي لا يعيد استخدام ملف صحيح يخص مسار shot آخر. يظل retry الفعلي محفوظًا عند failure فقط. في الإنتاج الناجح اللاحق ظهر كل استدعاء كـ`Scene N shot M`، ونتجت `19` لقطات جديدة و`0` resumed و`0` Pillow fallback.

### مدة الوسائط

لم يُجرَ تغيير غير ضروري في retiming أو padding. run الناجح أنتج مدة `81.301s`، واجتاز `duration_ok` و`av_duration` و`av_sync` وfull decode وQC، ولذلك لم توجد قرينة على أن معالجة المدة سببت invalid output أو desynchronization أو QC failure.

## 4. TESTS RUN

قبل E2E، نُفذت الاختبارات المباشرة التالية:

| الاختبار | النتيجة |
|---|---:|
| completion/failure authority وworkflow contract وBrowser Chat contract | `27 passed` |
| Pollinations bounded retry وresponse integrity | ناجح؛ retry محدود إلى `3` محاولات عند failure |
| checkpoint path/SHA وvisual uniqueness/resume | ناجح؛ كل shot مرة واحدة، وإعادة التشغيل تستخدم cache |
| Python compilation وYAML parse و`git diff --check` | ناجح |
| suite المستودع الكاملة | `82 passed, 7 warnings` |

التحذيرات السبعة warnings من dependencies/deprecations، ولم تكن فشلًا في الإنتاج أو QC. لم تُخفض عتبات QC، ولم يُسمح بـPillow fallback في production mode، ولم تتغير قاعدة `visual_variation` الصارمة `0.005`.

## 5. GITHUB ACTIONS RESULT

تم دفع الإصلاح إلى `main` بالـSHA:

`ebbf6ff9cf2edf4cf3eb839162fb5b8a26d503e8`

ثم بدأ التشغيل التلقائي الوحيد بعد الإصلاح:

| الحقل | القيمة |
|---|---|
| Workflow | `production-e2e-test.yml` |
| Run ID | `32981471428` |
| Event | `push` |
| Head SHA | `ebbf6ff9cf2edf4cf3eb839162fb5b8a26d503e8` |
| Job | `production-test` |
| Status | `completed` |
| Conclusion | `success` |
| رابط التشغيل | [GitHub Actions run 32981471428](https://github.com/aurelia-digital-pro/Aurelia-maker-/actions/runs/32981471428) |

تثبت سجلات GitHub أن checkout استخدم SHA `ebbf6ff9cf2edf4cf3eb839162fb5b8a26d503e8`، وأن Factory وصل إلى:

> `[FACTORY] PRODUCTION_COMPLETE — FINAL MP4: .../episode-0003-FINAL.mp4`

ثم واصلت الخطوات التنفيذية إلى Hard artifact verification وBuild final production proof وUpload proof artifacts. لم يعد workflow ينتظر Factory بعد `PRODUCTION_COMPLETE`، ولم يظهر `RuntimeError: Production failed`، ولم يظهر exit `124` أو timeout.

تم رفع artifact بنجاح:

| الحقل | القيمة |
|---|---|
| Artifact | `aurelia-production-proof` |
| Artifact ID | `9612876264` |
| الملفات المرفوعة | `89` |
| الحجم | `424832550 bytes` |
| Artifact digest | `15c5c251e96f0f74efe930fdbe974fb7ebfd2d10b8cb5e5009a4d27a882319e7` |
| الرابط | [artifact 9612876264](https://github.com/aurelia-digital-pro/Aurelia-maker-/actions/runs/32981471428/artifacts/9612876264) |

## 6. FINAL MP4 RESULT

الـFINAL الناتج من GitHub Actions، وليس فيديوًّا محليًا بديلًا، هو:

`runs/e2e/episode-0003-FINAL.mp4`

| البوابة | النتيجة الفعلية من run |
|---|---|
| Episode | `0003` |
| Factory job | `5c68fecfe8974d0bb2db3ef1449cb99d` |
| مدة الفيديو | `81.301s` |
| الحجم | `50521949 bytes` |
| SHA-256 | `d78bb63951edbd1e3147fa3d4170e48617974b3bfb4c5af0be6aa493f13bcab0` |
| video stream | موجود، `H.264`، `1920×1080`، مدة `81.301s` |
| audio stream | موجود، واجتاز `audio_stream` و`narration_audible` |
| frame diversity | `3` إطارات مختلفة من `3` عينات |
| visual provider | `cloud-api/pollinations` |
| Pillow fallback | `0` |
| cinematic treatments | `19` |
| depth artifacts | `19` |
| transitions | `16` عبر `19` shots |
| narration | Edge TTS، الصوت `ar-SA-HamedNeural`، اللغة `ar`، fallback `false`، degraded `false` |
| narration duration | `81.288027s` |
| audio loudness | `-16.0 LUFS` |
| true peak | `-3.7 dBFS` |
| clipping | `false` |
| subtitle artifact | موجود، و`subtitle_completeness` اجتازت |

اجتازت بوابات QC في GitHub: وجود الملف وحجمه، video/audio streams، الصيغة، المدة، FPS، full decode، freeze frames، temporal variation، visual variation بعتبة `0.005`، loudness، true peak، clipping، subtitle file، subtitle completeness، narration audibility، black frames، A/V duration وA/V sync وtarget duration. كانت `qc['delivery_blocked'] = false` وقائمة `fatals` فارغة، واجتاز `visual_qc`، ثم تطابق hash بعد Hard artifact verification مع proof النهائي.

نتيجة proof قبل البوابة كانت عمدًا `accepted=false` و`PRODUCTION_COMPLETE`. بعد نجاح كل بوابات GitHub أصبح proof النهائي `accepted=true` و`acceptance_state=COMPLETED` و`github_conclusion=success`. هذه هي النقطة التي تثبت أن القبول ليس مبنيًا على وجود MP4 فقط.

## 7. REMAINING ISSUES

لا توجد مشكلة متبقية تمنع مسار الإنتاج الذي عالجه هذا التوجيه. ما زالت هناك تحذيرات dependency/deprecation غير حاجبة في suite، كما أن حزمة artifact كبيرة لأنها تتضمن الأصول واللقطات الوسيطة وأدلة الإنتاج، لكنها رُفعت بنجاح ولا تؤثر على صحة الـFINAL.

لا يُعاد تشغيل E2E إضافي لهذا الإصلاح؛ التشغيل المعتمد الوحيد بعد الإصلاح هو `32981471428`، وهو `SUCCESS` على commit `ebbf6ff9cf2edf4cf3eb839162fb5b8a26d503e8`.

## References

1. [GitHub Actions run 32981471428](https://github.com/aurelia-digital-pro/Aurelia-maker-/actions/runs/32981471428)
2. [GitHub Actions artifact 9612876264](https://github.com/aurelia-digital-pro/Aurelia-maker-/actions/runs/32981471428/artifacts/9612876264)
3. [AURELIA Maker repository](https://github.com/aurelia-digital-pro/Aurelia-maker-)
