import type { ModuleSeed } from "@/../prisma/content-source/types";

const schemaHint = `customers(customer_id, name, region, signup_date)
products(product_id, name, category, price)
orders(order_id, customer_id, product_id, quantity, order_date, status)
payments(payment_id, order_id, amount, paid_at, method)`;

export const module05: ModuleSeed = {
  slug: "module-05-advanced-queries",
  title: "Advanced Queries",
  description: "CASE WHEN, COALESCE, подзапросы, CTE.",
  lessons: [
    {
      slug: "27-case-when",
      title: "CASE WHEN",
      description: "Условная логика прямо внутри SQL-запроса.",
      objectives: ["Строить условные выражения через CASE WHEN"],
      theory: `\`CASE WHEN\` — аналог ЕСЛИ из Excel внутри SQL: проверяет условия по порядку и возвращает соответствующее значение.

\`\`\`sql
CASE
  WHEN условие1 THEN значение1
  WHEN условие2 THEN значение2
  ELSE значение_по_умолчанию
END
\`\`\`
`,
      example: `\`\`\`sql
SELECT name,
  CASE WHEN price > 1000 THEN 'Дорогой' ELSE 'Доступный' END AS price_tier
FROM products;
\`\`\`

Присвоит каждому товару категорию по цене.`,
      commonMistakes: ["Забывать END в конце выражения CASE."],
      exercise: {
        type: "SQL_QUERY",
        title: "Категория товара по цене",
        description:
          "Выведи name и price_tier ('Дорогой' если price > 1000, иначе 'Доступный') для каждого товара.",
        difficulty: "INTERMEDIATE",
        points: 25,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT name, CASE WHEN price > 1000 THEN 'Дорогой' ELSE 'Доступный' END AS price_tier FROM products;",
        },
        explanation:
          "CASE WHEN проверяет условие price > 1000 для каждой строки отдельно.",
      },
      quiz: [
        {
          question: "Чем CASE WHEN в SQL похож на ЕСЛИ в Excel?",
          options: [
            "Ничем не похож",
            "Оба реализуют условную логику: разные значения для разных условий",
            "Оба работают только с текстом",
            "CASE WHEN работает только с числами",
          ],
          correctIndex: 1,
          explanation:
            "Обе конструкции возвращают разные значения в зависимости от условия.",
        },
      ],
    },
    {
      slug: "28-coalesce",
      title: "COALESCE",
      description: "Возвращает первое не-NULL значение из списка.",
      objectives: ["Использовать COALESCE для значений по умолчанию"],
      theory: `\`COALESCE\` возвращает первый не-NULL аргумент из переданного списка — удобно для подстановки значения по умолчанию вместо NULL.

\`\`\`sql
COALESCE(значение1, значение2, ..., запасное_значение)
\`\`\`
`,
      example: `\`\`\`sql
SELECT order_id, COALESCE(amount, 0) AS amount
FROM payments;
\`\`\`

Если amount NULL, вернёт 0 вместо NULL.`,
      commonMistakes: [
        "Путать COALESCE с ЕСЛИОШИБКА из Excel — COALESCE проверяет именно NULL, а не ошибки вычисления.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Сумма платежа по умолчанию",
        description: "Выведи order_id и amount платежей, заменив NULL в amount на 0.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT order_id, COALESCE(amount, 0) AS amount FROM payments;",
        },
        explanation: "COALESCE(amount, 0) подставляет 0 везде, где amount равен NULL.",
      },
      quiz: [
        {
          question: "Что вернёт COALESCE(NULL, NULL, 5)?",
          options: ["NULL", "5", "0", "Ошибку"],
          correctIndex: 1,
          explanation:
            "COALESCE возвращает первое не-NULL значение из списка — здесь это 5.",
        },
      ],
    },
    {
      slug: "29-subqueries",
      title: "Subqueries",
      description: "Запрос внутри запроса.",
      objectives: ["Писать подзапросы в WHERE и FROM"],
      theory: `Подзапрос (subquery) — это SELECT, вложенный внутрь другого запроса: в WHERE (для фильтрации по результату другого запроса), в FROM (как временная таблица) или в SELECT.

\`\`\`sql
SELECT * FROM таблица
WHERE столбец IN (SELECT столбец FROM другая_таблица WHERE условие);
\`\`\`
`,
      example: `\`\`\`sql
SELECT name FROM customers
WHERE customer_id IN (
  SELECT customer_id FROM orders WHERE status = 'cancelled'
);
\`\`\`

Найдёт клиентов, у которых есть хотя бы один отменённый заказ.`,
      commonMistakes: [
        "Использовать подзапрос там, где JOIN был бы проще и быстрее для чтения.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Клиенты с отменёнными заказами",
        description:
          "Выведи name клиентов, у которых есть хотя бы один заказ со статусом 'cancelled', используя подзапрос.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT name FROM customers WHERE customer_id IN (SELECT customer_id FROM orders WHERE status = 'cancelled');",
        },
        explanation:
          "Внутренний подзапрос находит customer_id с отменёнными заказами, внешний — их имена.",
      },
      quiz: [
        {
          question: "Где может использоваться подзапрос?",
          options: [
            "Только в WHERE",
            "Только в FROM",
            "В WHERE, FROM и SELECT",
            "Нигде, кроме UPDATE",
          ],
          correctIndex: 2,
          explanation:
            "Подзапросы допустимы в разных частях запроса: WHERE, FROM, SELECT.",
        },
      ],
    },
    {
      slug: "30-cte",
      title: "CTE",
      description: "Именованные временные результаты через WITH.",
      objectives: [
        "Строить CTE через WITH",
        "Понимать, зачем нужны CTE вместо вложенных подзапросов",
      ],
      theory: `CTE (Common Table Expression) — именованный временный результат запроса, объявленный через \`WITH\`, который можно использовать дальше в основном запросе. Делает сложные запросы более читаемыми, чем вложенные подзапросы.

\`\`\`sql
WITH имя_cte AS (
  SELECT ...
)
SELECT * FROM имя_cte WHERE ...;
\`\`\`
`,
      example: `\`\`\`sql
WITH cancelled_customers AS (
  SELECT DISTINCT customer_id FROM orders WHERE status = 'cancelled'
)
SELECT c.name
FROM customers c
JOIN cancelled_customers cc ON c.customer_id = cc.customer_id;
\`\`\`

Тот же результат, что и вложенный подзапрос, но читается как последовательность шагов.`,
      commonMistakes: [
        "Забывать, что CTE существует только в рамках одного запроса и не сохраняется как таблица.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "CTE для отменённых заказов",
        description:
          "Перепиши запрос «клиенты с отменёнными заказами» через WITH (CTE) вместо вложенного подзапроса.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "WITH cancelled_customers AS (SELECT DISTINCT customer_id FROM orders WHERE status = 'cancelled') SELECT c.name FROM customers c JOIN cancelled_customers cc ON c.customer_id = cc.customer_id;",
        },
        explanation:
          "WITH объявляет именованный промежуточный результат, который затем используется в основном запросе через JOIN.",
      },
      quiz: [
        {
          question: "Сохраняется ли CTE как отдельная таблица в базе данных?",
          options: [
            "Да, навсегда",
            "Нет, только на время одного запроса",
            "Да, до конца сессии",
            "Только если явно указать",
          ],
          correctIndex: 1,
          explanation:
            "CTE — временная именованная конструкция, существующая только в рамках запроса, где она объявлена.",
        },
      ],
    },
  ],
};
