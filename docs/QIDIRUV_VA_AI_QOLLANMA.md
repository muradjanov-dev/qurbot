# QurBot qidiruvi va AI qo'llanmasi

## Oqim

`Telegram bot / sayt` → `CatalogService` → PostgreSQL katalogi → (faqat noaniq bo'lsa) AI → savat → quote → buyurtma.

- `app/bot` Telegram ekranlari va callbacklari.
- `app/web/storefront` sayt hamda savat APIlari.
- `app/services/catalog_service.py` bot va sayt uchun yagona qidiruv oqimi.
- `app/domain` matnni normallashtirish, miqdor parseri va kandidat saralashi.
- `app/db` PostgreSQL modellari va repositorylari.
- `app/llm` prompt, cache va OpenAI-compatible client.

## Qidiruv qanday qaror qiladi

Avval lotin/kirill va yozilish variantlari normallanadi. Tasdiqlangan alias ham faol katalog, kategoriya, taklif va fizik atribut tekshiruvidan o'tadi. Umumiy nom bitta qalinlikka avtomatik bog'lanmaydi. Token va `pg_trgm` qidiruvidan 40 tadan nomzod olinadi; ular ID bo'yicha birlashtirilgach, limit qo'llashdan oldin saralanadi. Eng yaxshi 20 saqlanadi; AI saralangan top-8 ni ko'radi.

Aniq moslik avtomatik tanlanadi. Masalan, `fanera` bir necha qalinlikda bo'lsa bot tanlab yubormaydi: 2–3 variant va aniqlashtirish savolini ko'rsatadi. `0.3mm` ni `3mm` ga avtomatik o'zgartirish taqiqlangan. Mijoz miqdor yozmasa parser buni buyurtmaga o'tkazmaydi.

## AI xavfsizligi va tezligi

AIga mahsulotlar faqat ID bilan beriladi va u faqat shu IDlardan birini qaytarishi mumkin. Boshqa ID, takror satr, `NaN`, 0–1 dan tashqari confidence yoki buzilgan JSON tashlab yuboriladi. AI ishlamasa mavjud deterministic variantlar qoladi.

Har HTTP urinish 8 soniyadan oshmaydi; faqat timeout/tarmoq/429/5xx uchun bitta retry bor. Savatdagi AI ishi 12 soniyada tugaydi. Cache 24 soat va model, prompt versiyasi, til hamda kandidat tartibi bilan ajratilgan.

`LLM_PROVIDER` (`openai` yoki `anthropic`) va `LLM_MODEL` birga modelni tanlaydi.
Anthropic uchun `ANTHROPIC_API_KEY` ishlatiladi va javoblar native Messages API orqali
strict JSON schema bilan olinadi; OpenAI uchun `OPENAI_API_KEY` ishlatiladi.
`LLM_TIMEOUT_SECONDS`, `LLM_TOTAL_DEADLINE_SECONDS`, `LLM_MAX_RETRIES` faqat shu
servisga tegishli; secretlarni commit qilmang.

## Tekshirish

```bash
docker run --rm -v "$PWD:/app" -w /app qurbot-test:dev pytest -q
docker run --rm -v "$PWD:/app" -w /app qurbot-test:dev ruff check app tests
docker run --rm -v "$PWD:/app" -w /app qurbot-test:dev mypy app
```

Release eval'i alohida PostgreSQL bazasida bajariladi. `scripts/eval_models.py` eski SQLite tajribasi bo'lib, release mezoni emas. Yangi runner faqat `qurbot_matching_eval` nomli PostgreSQL bazasini qabul qiladi, unga anonim katalog snapshotini yuklaydi. Prod DBga ulanmaydi, order yoki Telegram xabari yaratmaydi:

```bash
export EVAL_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:55439/qurbot_matching_eval
python -m scripts.eval_matching --split development --output docs/eval_deterministic.json
# Jonli API uchun alohida kalit va tasdiqlangan budjet kerak:
python -m scripts.eval_matching --split all --models gpt-5.6-luna gpt-5.6-terra --output docs/eval_final.json
```

U faqat anonim test so'rovlaridan foydalanishi kerak. Telefon, manzil, Telegram ID, username, token yoki xom chatni eval/log/gitga qo'shmang. `llm_calls`da model, outcome va retry soni kuzatiladi; eski qatorlar `unknown` deb talqin qilinadi.

100 ta holat `tests/fixtures/matching_eval.json`da: 75 development, 25 holdout. Holdout threshold sozlash uchun ishlatilmaydi. Har API urinishdan oldin eng ko'p token xarajati rezerv qilinadi, timeout bo'lsa ham rezerv bo'shatilmaydi. `.pytest_cache/llm-eval-budget.json` budjetni restartlar orasida saqlaydi; davom etayotgan tajribada bu faylni o'chirmang. Bu runner bir vaqtda bitta jarayonda bajariladi.

Natijalar va cheklovlar: [AI release hisoboti](AI_RELEASE_REPORT.md).

## Deploy

Avval test/lint/type-check va GitHub CI yashil bo'lishi shart. So'ng `master` push qilinadi; server deploy jarayoni image SHA bilan ishga tushadi. Prod'da `/ready`, web/worker, webhook va yozuv yaratmaydigan qidiruv smoke tekshiruv qilinadi. Xato bo'lsa oldingi image/modelga qaytiladi; migration yangi ustunlarni ataylab saqlab qoladi.
