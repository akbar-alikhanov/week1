import type { ModuleSeed } from "@/../prisma/content-source/types";

const schemaHint = `customers(customer_id, name, region, signup_date)
products(product_id, name, category, price)
orders(order_id, customer_id, product_id, quantity, order_date, status)
payments(payment_id, order_id, amount, paid_at, method)`;

export const module06: ModuleSeed = {
  slug: "module-06-window-functions",
  title: "Window Functions",
  description: "ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, SUM OVER, AVG OVER.",
  lessons: [
    {
      slug: "31-row-number",
      title: "ROW_NUMBER",
      description: "Присваивает порядковый номер каждой строке.",
      objectives: ["Нумеровать строки с ROW_NUMBER", "Использовать PARTITION BY"],
      theory: `\`ROW_NUMBER()\` — оконная функция, присваивающая уникальный порядковый номер каждой строке в пределах окна, заданного \`OVER (...)\`. \`PARTITION BY\` разбивает нумерацию на независимые группы.

\`\`\`sql
ROW_NUMBER() OVER (PARTITION BY столбец ORDER BY другой_столбец)
\`\`\`
`,
      example: `\`\`\`sql
SELECT name, price,
  ROW_NUMBER() OVER (PARTITION BY category ORDER BY price DESC) AS rank_in_category
FROM products;
\`\`\`

Пронумерует товары от самого дорогого к дешёвому отдельно внутри каждой категории.`,
      commonMistakes: [
        "Забывать ORDER BY внутри OVER — тогда порядок нумерации не определён.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Номер товара по цене",
        description:
          "Выведи name, price и порядковый номер (row_num) товара при сортировке по убыванию цены, используя ROW_NUMBER.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT name, price, ROW_NUMBER() OVER (ORDER BY price DESC) AS row_num FROM products;",
        },
        explanation:
          "ROW_NUMBER() OVER (ORDER BY price DESC) нумерует товары от самого дорогого (1) и далее.",
      },
      quiz: [
        {
          question: "Зачем нужен PARTITION BY внутри OVER?",
          options: [
            "Чтобы удалить дубликаты",
            "Чтобы разбить строки на независимые группы для оконной функции",
            "Чтобы отсортировать всю таблицу",
            "Чтобы объединить таблицы",
          ],
          correctIndex: 1,
          explanation:
            "PARTITION BY задаёт группы, внутри которых оконная функция считается отдельно.",
        },
      ],
    },
    {
      slug: "32-rank",
      title: "RANK",
      description: "Ранжирует строки с одинаковыми местами при равенстве значений.",
      objectives: ["Отличать RANK от ROW_NUMBER"],
      theory: `\`RANK()\` похож на ROW_NUMBER, но при равных значениях столбца сортировки присваивает одинаковый ранг, а следующий ранг пропускает (например, 1, 2, 2, 4).

\`\`\`sql
RANK() OVER (ORDER BY столбец DESC)
\`\`\`
`,
      example: `Если два товара имеют одинаковую цену 1000 и оба претендуют на 2-е место, RANK даст обоим ранг 2, а следующий товар получит ранг 4 (не 3).`,
      commonMistakes: [
        "Путать RANK с DENSE_RANK — RANK пропускает номера после «связки», DENSE_RANK — нет.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Ранг товара по цене",
        description:
          "Выведи name, price и ранг (price_rank) товара по убыванию цены, используя RANK.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT name, price, RANK() OVER (ORDER BY price DESC) AS price_rank FROM products;",
        },
        explanation:
          "RANK() OVER (ORDER BY price DESC) присваивает одинаковый ранг товарам с равной ценой.",
      },
      quiz: [
        {
          question: "Если два товара делят 2-е место, какой ранг получит следующий?",
          options: ["3", "4", "2", "5"],
          correctIndex: 1,
          explanation:
            "RANK пропускает номера пропорционально количеству строк с одинаковым рангом (1,2,2,4).",
        },
      ],
    },
    {
      slug: "33-dense-rank",
      title: "DENSE_RANK",
      description: "Ранжирует без пропуска номеров при равенстве.",
      objectives: ["Использовать DENSE_RANK для рангов без пропусков"],
      theory: `\`DENSE_RANK()\` работает как RANK, но не оставляет «дыр» в нумерации после связки: 1, 2, 2, 3 (а не 1, 2, 2, 4).

\`\`\`sql
DENSE_RANK() OVER (ORDER BY столбец DESC)
\`\`\`
`,
      example: `Те же два товара по цене 1000 на 2-м месте — DENSE_RANK присвоит им ранг 2, а следующий товар получит ранг 3.`,
      commonMistakes: [
        "Выбирать RANK, когда по смыслу задачи (например, топ-N уникальных ценовых уровней) нужен именно DENSE_RANK.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Плотный ранг товара",
        description:
          "Выведи name, price и dense_rank товара по убыванию цены, используя DENSE_RANK.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT name, price, DENSE_RANK() OVER (ORDER BY price DESC) AS dense_rank FROM products;",
        },
        explanation: "DENSE_RANK не пропускает номера после связки одинаковых значений.",
      },
      quiz: [
        {
          question: "Чем DENSE_RANK отличается от RANK?",
          options: [
            "DENSE_RANK не пропускает номера после связки одинаковых значений",
            "DENSE_RANK работает только с текстом",
            "Это одна и та же функция",
            "DENSE_RANK не поддерживает PARTITION BY",
          ],
          correctIndex: 0,
          explanation:
            "После связки одинаковых значений DENSE_RANK продолжает нумерацию без пропусков.",
        },
      ],
    },
    {
      slug: "34-lag",
      title: "LAG",
      description: "Достаёт значение из предыдущей строки окна.",
      objectives: ["Сравнивать строку с предыдущей через LAG"],
      theory: `\`LAG(столбец)\` возвращает значение столбца из **предыдущей** строки в пределах окна — удобно для сравнения «текущий период vs. предыдущий».

\`\`\`sql
LAG(столбец) OVER (ORDER BY столбец_сортировки)
\`\`\`
`,
      example: `\`\`\`sql
SELECT order_date, amount,
  LAG(amount) OVER (ORDER BY order_date) AS prev_amount
FROM payments;
\`\`\`

Для каждой строки покажет сумму предыдущего платежа рядом с текущей.`,
      commonMistakes: [
        "Забывать, что для первой строки окна LAG вернёт NULL — предыдущей строки не существует.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Сравни с предыдущим платежом",
        description:
          "Выведи payment_id, amount и prev_amount (сумма предыдущего платежа по дате paid_at), используя LAG.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT payment_id, amount, LAG(amount) OVER (ORDER BY paid_at) AS prev_amount FROM payments;",
        },
        explanation:
          "LAG(amount) OVER (ORDER BY paid_at) берёт сумму предыдущего по дате платежа.",
      },
      quiz: [
        {
          question: "Что вернёт LAG для самой первой строки окна?",
          options: ["0", "NULL", "Значение последней строки", "Ошибку"],
          correctIndex: 1,
          explanation: "У первой строки нет предыдущей, поэтому LAG возвращает NULL.",
        },
      ],
    },
    {
      slug: "35-lead",
      title: "LEAD",
      description: "Достаёт значение из следующей строки окна.",
      objectives: ["Сравнивать строку со следующей через LEAD"],
      theory: `\`LEAD(столбец)\` — зеркало LAG: возвращает значение из **следующей** строки в пределах окна.

\`\`\`sql
LEAD(столбец) OVER (ORDER BY столбец_сортировки)
\`\`\`
`,
      example: `\`\`\`sql
SELECT order_date, amount,
  LEAD(amount) OVER (ORDER BY order_date) AS next_amount
FROM payments;
\`\`\`

Покажет сумму следующего платежа рядом с текущим.`,
      commonMistakes: ["Путать направление LAG (назад) и LEAD (вперёд)."],
      exercise: {
        type: "SQL_QUERY",
        title: "Сравни со следующим платежом",
        description:
          "Выведи payment_id, amount и next_amount (сумма следующего платежа по дате paid_at), используя LEAD.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT payment_id, amount, LEAD(amount) OVER (ORDER BY paid_at) AS next_amount FROM payments;",
        },
        explanation:
          "LEAD(amount) OVER (ORDER BY paid_at) берёт сумму следующего по дате платежа.",
      },
      quiz: [
        {
          question: "Что вернёт LEAD для самой последней строки окна?",
          options: ["NULL", "0", "Значение первой строки", "Ошибку"],
          correctIndex: 0,
          explanation: "У последней строки нет следующей, поэтому LEAD возвращает NULL.",
        },
      ],
    },
    {
      slug: "36-sum-over",
      title: "SUM OVER",
      description: "Считает накопительную (running total) сумму.",
      objectives: ["Строить накопительную сумму через SUM OVER"],
      theory: `\`SUM(столбец) OVER (ORDER BY ...)\` считает накопительную сумму (running total): для каждой строки — сумму всех значений от начала окна до текущей строки включительно.

\`\`\`sql
SUM(столбец) OVER (ORDER BY столбец_сортировки)
\`\`\`
`,
      example: `\`\`\`sql
SELECT paid_at, amount,
  SUM(amount) OVER (ORDER BY paid_at) AS running_total
FROM payments;
\`\`\`

Для каждого платежа покажет накопленную сумму всех платежей до него включительно.`,
      commonMistakes: [
        "Путать SUM OVER (накопительная сумма по строкам) с обычным GROUP BY + SUM (сумма по группе целиком).",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Накопительная сумма платежей",
        description:
          "Выведи paid_at, amount и running_total (накопительная сумма amount по дате paid_at), используя SUM OVER.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT paid_at, amount, SUM(amount) OVER (ORDER BY paid_at) AS running_total FROM payments;",
        },
        explanation:
          "SUM(amount) OVER (ORDER BY paid_at) складывает все суммы от начала до текущей строки.",
      },
      quiz: [
        {
          question: "Чем SUM OVER (ORDER BY ...) отличается от обычного GROUP BY + SUM?",
          options: [
            "Ничем не отличается",
            "SUM OVER считает накопительный итог по строкам, не схлопывая их в одну",
            "SUM OVER работает только с одной строкой",
            "GROUP BY быстрее в любом случае",
          ],
          correctIndex: 1,
          explanation:
            "Оконная SUM сохраняет все исходные строки, добавляя к ним накопительный расчёт.",
        },
      ],
    },
    {
      slug: "37-avg-over",
      title: "AVG OVER",
      description: "Скользящее среднее с оконной функцией.",
      objectives: ["Строить скользящее среднее через AVG OVER"],
      theory: `\`AVG(столбец) OVER (...)\` аналогично SUM OVER, но считает среднее значение в пределах окна — например, скользящее среднее по последним N строкам.

\`\`\`sql
AVG(столбец) OVER (ORDER BY столбец_сортировки)
\`\`\`
`,
      example: `\`\`\`sql
SELECT paid_at, amount,
  AVG(amount) OVER (ORDER BY paid_at) AS running_avg
FROM payments;
\`\`\`

Для каждого платежа покажет среднее значение всех платежей до него включительно.`,
      commonMistakes: [
        "Забывать PARTITION BY, когда среднее нужно считать отдельно по группам (например, по клиенту).",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Скользящее среднее платежей",
        description:
          "Выведи paid_at, amount и running_avg (среднее amount по дате paid_at нарастающим итогом), используя AVG OVER.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT paid_at, amount, AVG(amount) OVER (ORDER BY paid_at) AS running_avg FROM payments;",
        },
        explanation:
          "AVG(amount) OVER (ORDER BY paid_at) считает среднее по всем строкам от начала окна до текущей.",
      },
      quiz: [
        {
          question:
            "Что нужно добавить в OVER, чтобы считать среднее отдельно по каждому клиенту?",
          options: [
            "ORDER BY customer_id",
            "PARTITION BY customer_id",
            "GROUP BY customer_id",
            "WHERE customer_id",
          ],
          correctIndex: 1,
          explanation:
            "PARTITION BY разбивает окно на независимые группы — здесь по клиенту.",
        },
      ],
    },
  ],
};
