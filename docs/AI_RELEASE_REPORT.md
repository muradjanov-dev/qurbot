# Matching optimallashtirish — 2026-09-13

Boshlang'ich prod: `0e55a28a72d88e0cddb992e005d534f16dbcb976`, Luna.
Yangi release SHA va prod smoke holati HANDOFF'da qayd etiladi.

## Natijalar

Bir xil izolyatsiyalangan PostgreSQL katalogida 322 yozuv (317 faol), 100 noyob savol.
80 ta aniq nom/kompakt yozilish, 20 ta xato yozilish, aniqlashtirish, yaroqsiz miqdor,
mavjud bo'lmagan material va ko'p satrli savat holati. 25 tasi oldindan holdout qilib ajratilgan.

| Mezon | Luna | Terra |
|---|---:|---:|
| To'g'ri qaror | 100/100 | 100/100 |
| Holdout | 25/25 | 25/25 |
| Top-8 recall (aniq mahsulot kutilgan holatlar) | 100% | 100% |
| Fizik atributi noto'g'ri auto-accept | 0 | 0 |
| Sovuq savat p50 | 99.02 ms | 100.92 ms |
| Sovuq savat p95 | 222.59 ms | 209.81 ms |
| API chaqiruvlari | 4 | 4 |
| Tokenlar | 4,937 | 4,394 |
| Shu yakuniy yugurishdagi tarif taxmini | $0.001799 | $0.011468 |
| Issiq cache hit | 4 | 4 |

Luna bir xil qarorga arzonroq kelgani uchun saqlanadi. Faqat 4 tadan jonli chaqiruv:
model tezligi va haqiqiy foydalanuvchilardagi aniqlik haqida keng kafolat berib bo'lmaydi.
p95 savatning umumiy vaqtidir; uni AI chaqiruvining p95 vaqti deb o'qimang.
Har bir savolning sovuq va issiq vaqti `eval_final.json`da.

Development deterministic: 74/75 (98.67%), top-8 100%, p95 213.24 ms.
Qolgan `paner` holatini AI aniqlashtiradi.
Eski `0e55a28`ning aynan shu snapshotdagi deterministic baseline'i development 13/75,
holdout 2/25. Bu **jonli prod aniqligi emas**: snapshot shaxsiy aliaslar va savdo
yozuvlarini o'z ichiga olmaydi; search_doc ochiq nomlardan qayta yig'ilgan. Narxi bor
katalog mahsulotlariga qarshi izolyatsiyalangan taqqoslashdir. Baseline o'lchovi
`docs/eval_baseline.json`da; soxta oldingi prod foizi keltirilmagan.

## Sarf va manbalar

Barcha tajribalar uchun jami eng yuqori rezerv: **$1.196215**, ruxsat etilgan $2 ichida.
Rezerv haqiqiy billing emas: input UTF-8 baytlaridan konservativ baholanadi, maksimal
output to'liq hisoblanadi va har retry oldindan rezerv oladi. Hisobotdagi xarajatlar
tokenlar va rasmiy tarifdan hisoblangan taxmin; provider invoice tekshirilmagan.

2026-09-12 da tekshirilgan tariflar (1M input/output):
[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) $0.20/$1.20,
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) $2/$12.
Noma'lum model narxi `unknown_price`; admin ekranidagi legacy summalar aniq invoice emas.

## Tekshiruv va xavfsizlik

- 12 soniyalik real timer testi: 6.5s parser + 6.5s matching 13s kutmaydi, savol bilan qaytadi.
- API auth/429/5xx, buzilgan JSON, begona ID/satr, duplicate, NaN, cache expiry va model ajratish.
- `0.3mm`, `3m`, `03m`, noto'g'ri qalinlik va noma'lum atribut auto-acceptni taqiqlaydi.
- Bot/sayt bir xil qaror va ruscha savol berishi integration testda tekshirildi.
- AI qayta ajratgan savat satrlari mijoz tasdig'ini talab qiladi.
- To'liq lokal regression: 698 test o'tdi; keyingi qo'shilgan deadline/cache/channel testlari
  alohida o'tdi. Release CI yakuniy commitni to'liq qayta tekshiradi.
- `EXPLAIN ANALYZE`: 322 satrda `paner` trigram lookup 7.459 ms. Kichik jadvalda
  planner sequential scan tanlashi normal. Mavjud GIN indeks uchun `%>` sharti qo'shildi;
  yangi indeks zarurati aniqlanmadi.

## Qolgan amaliy cheklovlar

Korpus katalog va sun'iy yozilish variantlariga tayangan; jonli foydalanuvchi taqsimotini
ifodalamaydi. Prod'da sifatni keyingi anonim namunalarda kuzatish kerak. Eval budjet
ledger'i bitta runner uchun; bir nechta eval'ni parallel ishga tushirmang.
App uchun maxsus model narxini boshqa provider tarifiga avtomatik tenglashtirmang.
Android qurilmasida real Telegram UX tekshiruvi bu matching eval'ining o'rnini bosmaydi.
