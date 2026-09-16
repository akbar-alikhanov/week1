import type { ModuleSeed } from "@/../prisma/content-source/types";

const schemaHint = `customers(customer_id, name, region, signup_date)
products(product_id, name, category, price)
orders(order_id, customer_id, product_id, quantity, order_date, status)
payments(payment_id, order_id, amount, paid_at, method)`;

export const module04: ModuleSeed = {
  slug: "module-04-joins",
  title: "JOINs",
  description:
    "INNER JOIN, LEFT JOIN, RIGHT JOIN, FULL JOIN и объединение нескольких таблиц.",
  lessons: [
    {
      slug: "22-inner-join",
      title: "INNER JOIN",
      description: "Соединяет только строки, у которых есть совпадение в обеих таблицах.",
      objectives: ["Писать INNER JOIN по ключу", "Понимать, какие строки исключаются"],
      theory: `\`INNER JOIN\` соединяет строки двух таблиц там, где есть совпадение по указанному условию (обычно — по внешнему ключу). Строки без совпадения в обеих таблицах в результат не попадают.

\`\`\`sql
SELECT ...
FROM таблица1
INNER JOIN таблица2 ON таблица1.ключ = таблица2.ключ;
\`\`\`
`,
      example: `\`\`\`sql
SELECT o.order_id, c.name
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id;
\`\`\`

Вернёт заказы вместе с именем клиента — только для заказов, у которых есть клиент.`,
      commonMistakes: [
        "Забывать условие ON — без него получится декартово произведение всех строк обеих таблиц.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Заказы с именами клиентов",
        description:
          "Выведи order_id и name клиента для каждого заказа, используя INNER JOIN между orders и customers.",
        difficulty: "INTERMEDIATE",
        points: 25,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT o.order_id, c.name FROM orders o INNER JOIN customers c ON o.customer_id = c.customer_id;",
        },
        explanation: "INNER JOIN по customer_id соединяет каждый заказ с его клиентом.",
      },
      quiz: [
        {
          question: "Какие строки попадают в результат INNER JOIN?",
          options: [
            "Все строки обеих таблиц",
            "Только строки, у которых есть совпадение в обеих таблицах",
            "Только строки левой таблицы",
            "Только строки правой таблицы",
          ],
          correctIndex: 1,
          explanation:
            "INNER JOIN возвращает пересечение — строки, совпадающие по условию ON в обеих таблицах.",
        },
      ],
    },
    {
      slug: "23-left-join",
      title: "LEFT JOIN",
      description: "Сохраняет все строки левой таблицы, даже без совпадения.",
      objectives: ["Писать LEFT JOIN", "Понимать, когда появляется NULL"],
      theory: `\`LEFT JOIN\` возвращает все строки левой таблицы, и там, где нет совпадения в правой таблице, столбцы правой таблицы заполняются NULL.

\`\`\`sql
SELECT ...
FROM таблица1
LEFT JOIN таблица2 ON таблица1.ключ = таблица2.ключ;
\`\`\`
`,
      example: `\`\`\`sql
SELECT o.order_id, p.amount
FROM orders o
LEFT JOIN payments p ON o.order_id = p.order_id;
\`\`\`

Вернёт все заказы, даже те, для которых ещё нет платежа (amount будет NULL).`,
      commonMistakes: [
        "Использовать LEFT JOIN, а затем WHERE p.amount = ... без учёта, что NULL не равен ничему — часть строк неожиданно исчезает.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Заказы без оплаты",
        description:
          "Выведи order_id всех заказов, для которых ещё нет платежа (payment_id IS NULL), используя LEFT JOIN между orders и payments.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT o.order_id FROM orders o LEFT JOIN payments p ON o.order_id = p.order_id WHERE p.payment_id IS NULL;",
        },
        explanation:
          "LEFT JOIN сохраняет заказы без платежа с NULL вместо payment_id, что и отфильтровывает WHERE ... IS NULL.",
      },
      quiz: [
        {
          question: "Что произойдёт со столбцами правой таблицы, если совпадения нет?",
          options: [
            "Строка исключается из результата",
            "Они заполняются NULL",
            "Они заполняются 0",
            "Запрос вернёт ошибку",
          ],
          correctIndex: 1,
          explanation:
            "LEFT JOIN подставляет NULL в столбцы правой таблицы при отсутствии совпадения.",
        },
      ],
    },
    {
      slug: "24-right-join",
      title: "RIGHT JOIN",
      description: "Сохраняет все строки правой таблицы, даже без совпадения.",
      objectives: [
        "Писать RIGHT JOIN",
        "Понимать эквивалентность LEFT JOIN с переставленными таблицами",
      ],
      theory: `\`RIGHT JOIN\` — зеркало LEFT JOIN: сохраняет все строки правой таблицы, а несовпавшие столбцы левой заполняет NULL. На практике RIGHT JOIN редко используется — его почти всегда можно переписать как LEFT JOIN, поменяв таблицы местами.

\`\`\`sql
SELECT ...
FROM таблица1
RIGHT JOIN таблица2 ON таблица1.ключ = таблица2.ключ;
\`\`\`
`,
      example: `\`\`\`sql
SELECT c.name, o.order_id
FROM orders o
RIGHT JOIN customers c ON o.customer_id = c.customer_id;
\`\`\`

Вернёт всех клиентов, даже тех, у кого ещё нет заказов.`,
      commonMistakes: [
        "Путать, какая таблица «правая» в длинных запросах с несколькими JOIN.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Все клиенты, включая без заказов",
        description:
          "Выведи name клиента и order_id, используя RIGHT JOIN так, чтобы сохранить всех клиентов из customers.",
        difficulty: "INTERMEDIATE",
        points: 25,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT c.name, o.order_id FROM orders o RIGHT JOIN customers c ON o.customer_id = c.customer_id;",
        },
        explanation:
          "RIGHT JOIN customers сохраняет всех клиентов, даже тех, для кого нет строки в orders.",
      },
      quiz: [
        {
          question: "Чем RIGHT JOIN можно заменить, поменяв таблицы местами?",
          options: ["INNER JOIN", "LEFT JOIN", "FULL JOIN", "Ничем"],
          correctIndex: 1,
          explanation: "A RIGHT JOIN B эквивалентно B LEFT JOIN A.",
        },
      ],
    },
    {
      slug: "25-full-join",
      title: "FULL JOIN",
      description: "Сохраняет все строки из обеих таблиц.",
      objectives: ["Писать FULL JOIN"],
      theory: `\`FULL JOIN\` (FULL OUTER JOIN) возвращает все строки из обеих таблиц: там, где нет совпадения с одной из сторон, соответствующие столбцы заполняются NULL.

\`\`\`sql
SELECT ...
FROM таблица1
FULL JOIN таблица2 ON таблица1.ключ = таблица2.ключ;
\`\`\`
`,
      example: `\`\`\`sql
SELECT c.name, o.order_id
FROM customers c
FULL JOIN orders o ON c.customer_id = o.customer_id;
\`\`\`

Вернёт клиентов без заказов И заказы без клиента (если такие есть), а также все совпадения.`,
      commonMistakes: [
        "Использовать FULL JOIN там, где хватило бы INNER или LEFT — это усложняет чтение результата без необходимости.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Все клиенты и все заказы",
        description:
          "Выведи name клиента и order_id так, чтобы не потерять ни клиентов без заказов, ни (гипотетически) заказы без клиента.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT c.name, o.order_id FROM customers c FULL JOIN orders o ON c.customer_id = o.customer_id;",
        },
        explanation:
          "FULL JOIN сохраняет строки из обеих таблиц независимо от наличия совпадения.",
      },
      quiz: [
        {
          question: "Когда FULL JOIN вернёт строку с NULL с обеих сторон одновременно?",
          options: [
            "Никогда",
            "Это невозможно логически",
            "Такого не бывает при обычном FULL JOIN двух таблиц",
            "Когда сравниваются три и более таблиц с особыми условиями",
          ],
          correctIndex: 2,
          explanation:
            "При простом FULL JOIN двух таблиц каждая строка результата берёт данные хотя бы с одной стороны.",
        },
      ],
    },
    {
      slug: "26-multiple-joins",
      title: "Multiple JOINs",
      description: "Соединяем три и более таблиц в одном запросе.",
      objectives: ["Соединять более двух таблиц последовательными JOIN"],
      theory: `В одном запросе можно использовать несколько JOIN подряд, постепенно «подтягивая» данные из разных таблиц по цепочке связей.

\`\`\`sql
SELECT ...
FROM таблица1
JOIN таблица2 ON ...
JOIN таблица3 ON ...;
\`\`\`
`,
      example: `\`\`\`sql
SELECT c.name, p.name AS product, pay.amount
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN products p ON o.product_id = p.product_id
LEFT JOIN payments pay ON o.order_id = pay.order_id;
\`\`\`

Соединяет заказ с клиентом, товаром и (если есть) платежом — все четыре таблицы в одном запросе.`,
      commonMistakes: [
        "Соединять таблицы не по внешнему ключу, а по «похожим» столбцам — это даёт неверные результаты.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Клиент, товар и сумма заказа",
        description:
          "Выведи name клиента, name товара (как product) и quantity, соединив orders с customers и products.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT c.name, p.name AS product, o.quantity FROM orders o JOIN customers c ON o.customer_id = c.customer_id JOIN products p ON o.product_id = p.product_id;",
        },
        explanation:
          "Два последовательных JOIN подтягивают данные клиента и товара к каждому заказу.",
      },
      quiz: [
        {
          question: "Сколько таблиц максимум можно соединить в одном запросе?",
          options: ["Только 2", "Только 3", "Практически неограниченно", "Не более 5"],
          correctIndex: 2,
          explanation:
            "SQL не ограничивает количество JOIN в одном запросе, хотя производительность стоит учитывать.",
        },
      ],
    },
  ],
};
