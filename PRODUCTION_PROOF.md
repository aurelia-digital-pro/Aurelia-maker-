# AURELIA Maker — تقرير إثبات القبول الإنتاجي النهائي

## FINAL ARCHITECTURE

تم توحيد النظام حول محرك إنتاج canonical واحد هو الشجرة الجذرية `aurelia/`. أزيلت الشجرة التنفيذية المكررة `aurelia-engine/` من Git، ونُقلت الوثائق التاريخية غير التنفيذية فقط إلى `docs/legacy/`. لم يعد في المستودع مسار إنتاج Python ثانٍ، أو Factory بديل، أو مشغّل TypeScript ينفذ الإنتاج، أو TTS legacy مخفي.

الواجهة المتعاقد عليها هي Browser Chat، ويصل الطلب إلى `aurelia.server` ثم `aurelia.chat_entry` ثم `FactoryRunner` ثم `ProductionPipeline` ثم `EpisodeProduction`. مسار `/api/productions` في TypeScript أصبح compatibility proxy عديم الحالة إلى canonical Python API، ولا ينشئ job map أو state machine أو subprocess خاصًا به.

## CANONICAL PRODUCTION PATH

المسار الفعلي الموحد هو:

```text
Browser Chat
  → aurelia.server
  → chat_entry.handle_chat_production
  → FactoryRunner
  → ProductionPipeline / FactoryExecutor
  → EpisodeProduction
  → visual provider + shot checkpoints
  → Edge TTS narration
  → edit / color / subtitles / master
  → artifact validation
  → QC
  → delivery
  → Factory COMPLETED
  → GitHub Actions hard verification
  → accepted=true
```

عقود المراحل معرفة في `aurelia/production_contract.py`، ويجري التحقق من المدخلات قبل كل stage ومن مخرجاته قبل السماح بالانتقال. الناتج الناقص أو metadata-only لا يعد نجاحًا؛ يتحول إلى `FAILED` مع الاحتفاظ بالسبب الجذري.

## WHAT WAS WRONG

كشفت المواصفة الأحدث مسارين متوازيين حقيقيين. كان `artifacts/api-server/src/routes/productions.ts` يستدعي `spawn` لتشغيل `aurelia-engine/run_job.py`، وكانت تلك الشجرة تستخدم state model مختلفًا (`VALIDATED`) ومسار TTS offline مختلفًا. لذلك لم يكن نجاح Edge TTS السابق يثبت أن مسار Episode 0120 الفعلي يستخدم Edge TTS.

كما كان التنفيذ السابق يحتوي دائرة اعتماد أخرى: Factory ينتظر نجاح GitHub Actions الذي يشغّل Factory نفسه. أزيل هذا الانتظار؛ GitHub يتحقق من Factory بعد اكتماله، ولا يعتمد Factory على حالة CI الحالية.

ظهر في أول تشغيل بعد canonicalization، run `32994536009`، فشل مبكر عند عقدة SCRIPT لأن الحالة الابتدائية لم تكن تحتوي `episode_id` رغم أن العقدة تطلبه. لم يبدأ ذلك التشغيل أي إنتاج media/provider فعليًا. أضيف `episode_id` إلى initial state، واختُبر الإصلاح محليًا قبل التشغيل النهائي.

## WHAT WAS CONSOLIDATED

| المجال | الحالة الموحدة الحالية |
|---|---|
| المحرك | `aurelia/` الجذرية فقط؛ لا تنفيذ من `aurelia-engine/` |
| API | Python canonical API؛ TypeScript compatibility proxy فقط |
| dependencies | `requirements.txt` هو المصدر authoritative؛ `pyproject.toml` و`.replit` وGitHub متسقة مع Python 3.12 |
| TTS | Edge TTS canonical؛ العربية `ar-SA-HamedNeural` والإنجليزية `en-US-AriaNeural` |
| state | `QUEUED/RUNNING/FAILED/COMPLETED/STOPPED` بعقود وانتقالات حقيقية |
| idempotency | هوية job من episode/profile/source-text SHA تحت lock ذري؛ duplicate active/completed يعاد استخدامه |
| retry | retries محدودة، ولا retry بعد نجاح artifact |
| checkpoint | per-job وper-scene/per-shot مع expected path وSHA والحجم وprovenance |
| provenance | backend/voice/language/shot/text hash/output/attempts/artifact validation محفوظة |
| acceptance | Factory يكمل مستقلًا؛ GitHub يرقّي proof إلى accepted بعد hard verification فقط |

في المسار البصري، كان الالتباس السابق ناتجًا أيضًا عن logs تعرض رقم scene بينما التنفيذ كان لكل shot. أضيف `shot_index` إلى logs وprovenance. إعادة الطلب محصورة في timeout أو response ناقص، بحد أقصى ثلاث محاولات إجمالًا، بينما checkpoint يمنع إعادة توليد shot ناجح.

## TTS ROOT CAUSE (Episode 0120)

سبب تعارض Episode 0120 كان أن API القديم يطلق `aurelia-engine/run_job.py`، لا أن Edge TTS canonical فشل بصمت. الشجرة القديمة كانت تستخدم legacy/offline TTS (`espeak`/`pyttsx3`) وتعرض تشخيصًا عامًا عند فشل الحوار، ولذلك كان الدليل السابق على Edge TTS لا ينطبق على المسار الذي شغله ذلك الطلب.

تم حذف الشجرة التنفيذية المكررة، وتحويل `aurelia/tts.py` إلى facade رفيع يمرر إلى `EdgeTTSProvider`، ومنع fallback الإنتاجي. يسجل `aurelia/providers/audio.py` الآن provider وvoice وlanguage وsegment index وtext SHA وoutput path وartifact size وvalidation وattempt history، ولا يحول السبب الحقيقي إلى رسالة generic.

## ENVIRONMENT CONSISTENCY

`requirements.txt` هو عقد الاعتماد الإنتاجي authoritative ويتضمن `edge-tts==7.2.8`. تم توحيد Python على `>=3.12,<3.13` في `pyproject.toml` و`.replit` وGitHub Actions. workflow يثبت `requirements.txt` ويجهز FFmpeg وffprobe وespeak والخطوط؛ `requirements-ai.txt` اختياري لمسار local-AI ولا يغير مسار production canonical. كما يثبت `scripts/post-merge.sh` الاعتمادات authoritative قبل PNPM.

## STATE MACHINE

تبدأ الوظيفة `QUEUED` ثم `RUNNING`. نجاح كل عقدة لا يثبت إلا بعد output validation. فشل stage أو artifact أو QC يبقي الجذر محفوظًا ويضع الوظيفة `FAILED`، والتوقف الصريح يضعها `STOPPED`. بعد اكتمال delivery والتحقق النهائي من FINAL MP4 وQC تصبح الوظيفة `COMPLETED` وتخرج العملية بنجاح. لا توجد حالة `AWAITING_GITHUB_ACTIONS` في دورة Factory الحالية، ولا polling أو `gh` من داخل الإنتاج.

في التشغيل الناجح، كان `production_manifest.json` دليل Factory المحلي على `PRODUCTION_COMPLETE`. أما `production_proof.json` فهو proof GitHub اللاحق الذي يثبت `accepted=true` و`acceptance_state=COMPLETED` بعد نجاح hard verification؛ لا ينبغي الخلط بين الحالتين.

## RETRY MODEL

يستخدم `FactoryExecutor` حدًا أقصى قدره محاولتان لإعادة المحاولة، أي ثلاث محاولات إجمالًا، مع backoff صغير bounded. يعاد job جديد فقط بعد `FAILED` أو `STOPPED`، مع `retry_of` وهوية جديدة. الطلبات المتزامنة لنفس identity لا تبدأ إنتاجًا مكلفًا ثانيًا إذا كان job في `QUEUED` أو `RUNNING`، ويعاد job المكتمل إذا ظل FINAL صالحًا.

Visual Pollinations يحاول مجددًا فقط عند network timeout أو response ناقص، وEdge TTS لديه retries bounded وtimeouts صريحة. لا تعاد محاولة artifact ناجح، ولا تستخدم retries لإخفاء فشل stage أو تخفيف QC.

## CHECKPOINT/DUPLICATION MODEL

هوية كل shot تتضمن job root، و`scene_index:shot_index`، والمسار المتوقع، وSHA والحجم وbackend/provenance. `VisualCheckpoint.is_done` لا يعيد استخدام الملف إلا إذا تطابق expected path ووجود الملف وسلامته وSHA. يحفظ manifest مصدر الطلب وrun وasset SHA وprompt وseed وهوية shot، بينما تسجل provider logs هوية scene/shot.

في التشغيل النهائي كان هناك `19` shot identity فريدًا، و`19` visual treatments و`19` depth artifacts و`16` transition عبر `19` shots، مع `0` Pillow fallback. كانت النتائج البصرية كلها `cloud-api/pollinations`. لم يظهر call path موازٍ؛ إعادة المحاولة بقيت محصورة بالفشل الحقيقي.

## GITHUB ACTIONS PARITY

القبول النهائي الموثق صدر من GitHub Actions، لا من إنتاج محلي بديل:

| الحقل | القيمة |
|---|---|
| Workflow | `production-e2e-test.yml` |
| Run ID | `32995131471` |
| Event | `workflow_dispatch` |
| Head SHA | `cd0243300065d03ceaeef579293ad302ae0f6bb5` |
| Job | `production-test` |
| Factory job | `beb99ca80744498abc6ec83e6acf705c` |
| Status | `completed` |
| Conclusion | `success` |
| Artifact | `aurelia-production-proof` |
| Artifact ID | `9617577554` |
| Artifact ZIP bytes | `417170338` |
| Artifact digest | `77fe049394ae13b8253cd6e3b92cc8b7013b431983a2387daedd4c918d89ce29` |

استخدم التشغيل طلب Chat-equivalent للـEpisode `0003` من `scripts/episode-0001-arabic-test.txt` باللغة `ar`. قبل الإنتاج شغل workflow suite الاختبارات، ثم نفذ Chat acceptance وFactory وvisual/audio/editing/QC/delivery وhard artifact verification. لم يحدث exit `124`، ولم ينتظر Factory نجاح GitHub Actions.

## REMAINING RISKS

| FILE | FUNCTION | ROOT CAUSE | IMPACT |
|---|---|---|---|
| `aurelia/factory_runner.py` | state/manifest lifecycle | `COMPLETED` المحلي يعني Factory completion، بينما GitHub promotion لاحقة | يجب قراءة `production_proof.json` عند تقرير القبول الخارجي؛ لا يعد ذلك محركًا موازيًا |
| `aurelia/visual_checkpoint.py` | checkpoint identity | source text/prompt hashes محفوظة في manifest/provenance لا كحقول مستقلة داخل checkpoint record نفسه | حماية resume الحالية سليمة بالـjob root/path/SHA؛ الفصل المباشر للحقول يمكن أن يكون تحسينًا لاحقًا غير حاجب |
| `requirements-ai.txt` | optional local AI dependencies | ملف منفصل intentionally وليس جزءًا من production contract | لا يؤثر على canonical production ما دام `requirements.txt` هو المستخدم |
| suite dependencies | pytest warnings | تحذيرات dependencies/deprecations غير حاجبة | لا تمنع production readiness ولا تغير نتيجة QC |

لم تظهر في التدقيق النهائي أي مخاطرة حاجبة: لا fallback بصري، لا TTS degraded، لا duplicate shot identity، لا missing artifact، ولا قبول مبني على وجود MP4 فقط.

## FINAL PRODUCTION READINESS

الـFINAL MP4 المستخرج للتدقيق من artifact GitHub هو `episode-0003-FINAL.mp4`، وليس إنتاجًا محليًا بديلًا. حجمه `49,109,522` bytes، وSHA-256 هو:

```text
52ab6b9d2c81ef148b3f39b24d66c9099f065434b30bae37c23d98812ef5a3f5
```

مدته `81.301s`، والفيديو H.264 بدقة `1920×1080`، والصوت AAC. اجتاز التدقيق المستقل `ffprobe`، وFFmpeg full decode، و`freezedetect=n=-60dB:d=0.5` دون freeze duration، و`aurelia.qc_engine.run_qc(require_audio_quality=True)`، و`validate_master`، وقياس audio quality.

نتائج الصوت: Edge TTS، العربية `ar-SA-HamedNeural`، `fallback=false`، `degraded=false`، `attempts=1`، وnarration duration `81.288027s`. سجّل artifact `-16.0 LUFS` و`-3.7 dBFS true peak` وclipping `false`. ملف SRT موجود واجتاز subtitle completeness. المعاينة البصرية المستقلة لثلاثة إطارات أظهرت تنوع بيئيًا ومعالجة لونية سينمائية وترجمة عربية مقروءة ضمن safe area، دون debug UI أو نص تشخيصي.

تطابقت نتيجة proof مع الملف النهائي: `accepted=true`، `acceptance_state=COMPLETED`، commit `cd0243300065d03ceaeef579293ad302ae0f6bb5`، run `32995131471`، وGitHub conclusion `success`. اجتازت البوابات full decode وfreeze وtemporal/visual variation بعتبة `0.005` وaudio loudness/true peak/clipping وsubtitle/narration وA/V وformat، مع `qc.delivery_blocked=false` وقائمة `fatals` فارغة.

الاختبارات الداخلية قبل E2E: `87 passed, 7 warnings`، مع نجاح Python compile، typecheck/build لعقود API وDB، diff-check، وstatic scan. تم توثيق الإصلاح على `main` في commit `cd0243300065d03ceaeef579293ad302ae0f6bb5`، مع إبقاء هذه الوثيقة بلا تشغيل E2E جديد.

PRODUCTION READY: YES
