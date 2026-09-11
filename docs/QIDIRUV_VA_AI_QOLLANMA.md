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

Avval lotin/kirill va yozilish variantlari normallanadi. Tasdiqlangan alias aniq topilsa u darhol ishlatiladi. Keyin token va `pg_trgm` typo qidiruvi birga olinadi, ID bo'yicha birlashtiriladi va nom, o'lcham, qalinlik, marka bilan qayta saralanadi. Eng yaxshi 20 saqlanadi; AI faqat saralangan top-8 ni ko'radi.

Aniq moslik avtomatik tanlanadi. Masalan, `fanera` bir necha qalinlikda bo'lsa bot tanlab yubormaydi: 2–3 variant va aniqlashtirish savolini ko'rsatadi. `0.3mm` ni `3mm` ga avtomatik o'zgartirish taqiqlangan. Mijoz miqdor yozmasa parser buni buyurtmaga o'tkazmaydi.

## AI xavfsizligi va tezligi

AIga mahsulotlar faqat ID bilan beriladi va u faqat shu IDlardan birini qaytarishi mumkin. Boshqa ID, takror satr, `NaN`, 0–1 dan tashqari confidence yoki buzilgan JSON tashlab yuboriladi. AI ishlamasa mavjud deterministic variantlar qoladi.

Har HTTP urinish 8 soniyadan oshmaydi; faqat timeout/tarmoq/429/5xx uchun bitta retry bor. Savatdagi AI ishi 12 soniyada tugaydi. Cache 24 soat va model, prompt versiyasi, til hamda kandidat tartibi bilan ajratilgan.

`LLM_MODEL` orqali model tanlanadi (prod hozir Luna). `LLM_TIMEOUT_SECONDS`, `LLM_TOTAL_DEADLINE_SECONDS`, `LLM_MAX_RETRIES` faqat shu servisga tegishli; secretlarni commit qilmang.

## Tekshirish

```bash
docker run --rm -v "$PWD:/app" -w /app qurbot-test:dev pytest -q
docker run --rm -v "$PWD:/app" -w /app qurbot-test:dev ruff check app tests
docker run --rm -v "$PWD:/app" -w /app qurbot-test:dev mypy app
```

Model solishtiruvi yozuv yaratmaydigan alohida SQLite muhitida bajariladi:

```bash
python -m scripts.eval_models gpt-5.6-luna gpt-5.6-terra
```

U faqat anonim test so'rovlaridan foydalanishi kerak. Telefon, manzil, Telegram ID, username, token yoki xom chatni eval/log/gitga qo'shmang. `llm_calls`da model, outcome va retry soni kuzatiladi; eski qatorlar `unknown` deb talqin qilinadi.

## Deploy

Avval test/lint/type-check va GitHub CI yashil bo'lishi shart. So'ng `master` push qilinadi; server deploy jarayoni image SHA bilan ishga tushadi. Prod'da `/ready`, web/worker, webhook va yozuv yaratmaydigan qidiruv smoke tekshiruv qilinadi. Xato bo'lsa oldingi image/modelga qaytiladi; migration yangi ustunlarni ataylab saqlab qoladi.
