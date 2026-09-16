import type { ModuleSeed } from "@/../prisma/content-source/types";

const schemaHint = `customers(customer_id, name, region, signup_date)
products(product_id, name, category, price)
orders(order_id, customer_id, product_id, quantity, order_date, status)
payments(payment_id, order_id, amount, paid_at, method)`;

export const module02: ModuleSeed = {
  slug: "module-02-filtering-sorting",
  title: "Filtering & Sorting",
  description: "ORDER BY, LIMIT, DISTINCT, IN, BETWEEN, LIKE, IS NULL.",
  lessons: [
    {
      slug: "09-order-by",
      title: "ORDER BY",
      description: "Сортировка результатов запроса.",
      objectives: [
        "Сортировать результат по возрастанию/убыванию",
        "Сортировать по нескольким столбцам",
      ],
      theory: `\`ORDER BY\` сортирует результат запроса по одному или нескольким столбцам. По умолчанию — по возрастанию (\`ASC\`), для убывания указывается \`DESC\`.

\`\`\`sql
SELECT столбцы FROM таблица ORDER BY столбец [ASC|DESC];
\`\`\`
`,
      example: `\`\`\`sql
SELECT name, price FROM products ORDER BY price DESC;
\`\`\`

Вернёт товары, отсортированные от самого дорогого к самому дешёвому.`,
      commonMistakes: [
        "Забывать DESC и получать сортировку по возрастанию вместо ожидаемого убывания.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Самые дорогие товары",
        description: "Выбери name и price из products, отсортировав по цене по убыванию.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT name, price FROM products ORDER BY price DESC;",
        },
        explanation:
          "ORDER BY price DESC сортирует товары от самой высокой цены к самой низкой.",
      },
      additionalExercises: [
        {
          type: "SQL_QUERY",
          title: "Клиенты по алфавиту",
          description: "Выбери name из customers, отсортировав по имени по возрастанию.",
          difficulty: "BEGINNER",
          points: 15,
          data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
          correctAnswer: {
            type: "SQL_QUERY",
            referenceQuery: "SELECT name FROM customers ORDER BY name ASC;",
          },
          explanation:
            "ORDER BY name ASC сортирует клиентов по алфавиту (это поведение по умолчанию).",
        },
        {
          type: "SQL_QUERY",
          title: "Недавние заказы",
          description:
            "Выбери order_id и order_date из orders, отсортировав по дате заказа от новых к старым.",
          difficulty: "INTERMEDIATE",
          points: 20,
          data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
          correctAnswer: {
            type: "SQL_QUERY",
            referenceQuery:
              "SELECT order_id, order_date FROM orders ORDER BY order_date DESC;",
          },
          explanation: "ORDER BY order_date DESC ставит самые недавние заказы первыми.",
        },
      ],
      quiz: [
        {
          question:
            "Какая сортировка используется по умолчанию, если не указать ASC/DESC?",
          options: ["По убыванию", "По возрастанию", "Случайная", "Сортировки не будет"],
          correctIndex: 1,
          explanation: "По умолчанию ORDER BY сортирует по возрастанию (ASC).",
        },
        {
          question: "Как отсортировать по цене от большего к меньшему?",
          options: [
            "ORDER BY price ASC",
            "ORDER BY price DESC",
            "SORT BY price DOWN",
            "ORDER price DESC",
          ],
          correctIndex: 1,
          explanation: "DESC (descending) сортирует от большего значения к меньшему.",
        },
        {
          question: "Можно ли сортировать сразу по нескольким столбцам?",
          options: [
            "Нет",
            "Да, через запятую",
            "Только по двум",
            "Только по числовым столбцам",
          ],
          correctIndex: 1,
          explanation:
            "ORDER BY col1, col2 DESC — можно сортировать по нескольким ключам сразу.",
        },
      ],
    },
    {
      slug: "10-limit",
      title: "LIMIT",
      description: "Ограничение количества возвращаемых строк.",
      objectives: ["Ограничивать количество строк результата"],
      theory: `\`LIMIT\` ограничивает количество строк, возвращаемых запросом — полезно для просмотра «топ-N» записей вместе с ORDER BY.

\`\`\`sql
SELECT столбцы FROM таблица ORDER BY столбец DESC LIMIT N;
\`\`\`
`,
      example: `\`\`\`sql
SELECT name, price FROM products ORDER BY price DESC LIMIT 3;
\`\`\`

Вернёт три самых дорогих товара.`,
      commonMistakes: [
        "Использовать LIMIT без ORDER BY, когда важен порядок — тогда «первые N строк» не гарантированы.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Топ-3 самых дорогих товара",
        description: "Выбери name и price трёх самых дорогих товаров.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT name, price FROM products ORDER BY price DESC LIMIT 3;",
        },
        explanation: "ORDER BY price DESC LIMIT 3 возвращает три самых дорогих товара.",
      },
      quiz: [
        {
          question: "Зачем LIMIT обычно комбинируют с ORDER BY?",
          options: [
            "Это обязательное требование синтаксиса",
            "Чтобы гарантировать, какие именно строки попадут в ограниченный результат",
            "Чтобы ускорить фильтрацию",
            "Незачем, это не связано",
          ],
          correctIndex: 1,
          explanation:
            "Без сортировки порядок строк не гарантирован, и LIMIT может вернуть произвольные строки.",
        },
      ],
    },
    {
      slug: "11-distinct",
      title: "DISTINCT",
      description: "Убираем повторяющиеся значения из результата.",
      objectives: ["Получать уникальные значения столбца"],
      theory: `\`DISTINCT\` убирает дублирующиеся строки из результата — возвращает только уникальные комбинации выбранных столбцов.

\`\`\`sql
SELECT DISTINCT столбец FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT DISTINCT region FROM customers;
\`\`\`

Вернёт список уникальных регионов, даже если у многих клиентов регион повторяется.`,
      commonMistakes: [
        "Ставить DISTINCT перед каждым столбцом отдельно — DISTINCT относится ко всей выборке, а не к одному столбцу.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Уникальные категории товаров",
        description: "Выбери список уникальных категорий (category) товаров.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT DISTINCT category FROM products;",
        },
        explanation:
          "DISTINCT category возвращает каждую категорию один раз, без повторов.",
      },
      quiz: [
        {
          question: "Что делает SELECT DISTINCT region FROM customers?",
          options: [
            "Удаляет столбец region",
            "Возвращает каждое уникальное значение region один раз",
            "Считает количество регионов",
            "Сортирует регионы",
          ],
          correctIndex: 1,
          explanation:
            "DISTINCT убирает дубликаты из результата, оставляя уникальные значения.",
        },
      ],
    },
    {
      slug: "12-in",
      title: "IN",
      description: "Проверка вхождения значения в список.",
      objectives: ["Фильтровать по списку значений через IN"],
      theory: `\`IN\` проверяет, входит ли значение столбца в заданный список — компактная альтернатива цепочке условий через OR.

\`\`\`sql
SELECT * FROM таблица WHERE столбец IN (значение1, значение2, ...);
\`\`\`
`,
      example: `\`\`\`sql
SELECT * FROM orders WHERE status IN ('pending', 'shipped');
\`\`\`

Вернёт заказы, статус которых — «pending» ИЛИ «shipped».`,
      commonMistakes: [
        "Писать WHERE status = 'pending' OR 'shipped' — это синтаксическая ошибка, нужно повторять столбец или использовать IN.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Заказы в обработке",
        description:
          "Выбери все заказы (все столбцы), у которых статус 'pending' или 'shipped'.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT * FROM orders WHERE status IN ('pending', 'shipped');",
        },
        explanation:
          "IN ('pending', 'shipped') проверяет вхождение статуса в список значений.",
      },
      quiz: [
        {
          question: "Чем можно заменить WHERE status IN ('a','b')?",
          options: [
            "WHERE status = 'a' OR status = 'b'",
            "WHERE status = 'a' AND status = 'b'",
            "Ничем, IN уникален",
            "WHERE status BETWEEN 'a' AND 'b'",
          ],
          correctIndex: 0,
          explanation:
            "IN — это сокращённая запись цепочки условий через OR для одного столбца.",
        },
      ],
    },
    {
      slug: "13-between",
      title: "BETWEEN",
      description: "Проверка вхождения значения в диапазон.",
      objectives: ["Фильтровать значения в числовом или датовом диапазоне"],
      theory: `\`BETWEEN\` проверяет, попадает ли значение в диапазон (включительно с обеих границ).

\`\`\`sql
SELECT * FROM таблица WHERE столбец BETWEEN значение1 AND значение2;
\`\`\`
`,
      example: `\`\`\`sql
SELECT name, price FROM products WHERE price BETWEEN 500 AND 2000;
\`\`\`

Вернёт товары с ценой от 500 до 2000 включительно.`,
      commonMistakes: [
        "Забывать, что BETWEEN включает обе границы диапазона (в отличие от строгого >  и <).",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Товары в ценовом диапазоне",
        description: "Выбери name и price товаров с ценой от 500 до 2000 включительно.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT name, price FROM products WHERE price BETWEEN 500 AND 2000;",
        },
        explanation: "BETWEEN 500 AND 2000 включает границы 500 и 2000.",
      },
      quiz: [
        {
          question: "Включает ли BETWEEN границы диапазона?",
          options: [
            "Да, обе границы включены",
            "Нет, обе границы исключены",
            "Только нижняя включена",
            "Только верхняя включена",
          ],
          correctIndex: 0,
          explanation:
            "BETWEEN a AND b эквивалентно >= a AND <= b — обе границы включены.",
        },
      ],
    },
    {
      slug: "14-like",
      title: "LIKE",
      description: "Поиск текста по шаблону.",
      objectives: ["Использовать LIKE с шаблонами % и _"],
      theory: `\`LIKE\` ищет текст, соответствующий шаблону: \`%\` заменяет любое количество символов, \`_\` — ровно один символ.

\`\`\`sql
SELECT * FROM таблица WHERE столбец LIKE 'шаблон%';
\`\`\`
`,
      example: `\`\`\`sql
SELECT name FROM customers WHERE name LIKE 'A%';
\`\`\`

Вернёт клиентов, чьё имя начинается на «A».`,
      commonMistakes: [
        "Забывать, что LIKE в большинстве СУБД чувствителен к регистру (для нечувствительного поиска нужен ILIKE в PostgreSQL).",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Клиенты на букву A",
        description: "Выбери name клиентов, чьё имя начинается на 'A'.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT name FROM customers WHERE name LIKE 'A%';",
        },
        explanation:
          "LIKE 'A%' ищет строки, начинающиеся с буквы A, за которой следует что угодно.",
      },
      quiz: [
        {
          question: "Что означает символ % в шаблоне LIKE?",
          options: [
            "Ровно один произвольный символ",
            "Любое количество произвольных символов (включая ноль)",
            "Процент",
            "Экранирование",
          ],
          correctIndex: 1,
          explanation:
            "% соответствует любой последовательности символов, включая пустую.",
        },
      ],
    },
    {
      slug: "15-is-null",
      title: "IS NULL",
      description: "Проверка отсутствия значения.",
      objectives: ["Проверять пустые значения через IS NULL/IS NOT NULL"],
      theory: `\`NULL\` означает «значение неизвестно/отсутствует». Сравнение \`= NULL\` не работает — для проверки нужен специальный оператор \`IS NULL\` (или \`IS NOT NULL\` для обратной проверки).

\`\`\`sql
SELECT * FROM таблица WHERE столбец IS NULL;
\`\`\`
`,
      example: `\`\`\`sql
SELECT order_id FROM payments WHERE paid_at IS NULL;
\`\`\`

Вернёт платежи, у которых ещё не заполнена дата оплаты.`,
      commonMistakes: [
        "Писать WHERE column = NULL вместо WHERE column IS NULL — это не вызовет ошибку, но всегда вернёт пустой результат.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Незавершённые платежи",
        description:
          "Выбери payment_id платежей, у которых paid_at ещё не заполнено (NULL).",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT payment_id FROM payments WHERE paid_at IS NULL;",
        },
        explanation:
          "IS NULL корректно проверяет отсутствие значения, в отличие от = NULL.",
      },
      quiz: [
        {
          question: "Почему WHERE column = NULL не работает как ожидается?",
          options: [
            "Это синтаксическая ошибка",
            "NULL нельзя сравнивать оператором =, нужен IS NULL",
            "Это работает, просто медленно",
            "NULL и '' — одно и то же",
          ],
          correctIndex: 1,
          explanation:
            "NULL — особое состояние «неизвестно», для его проверки используется IS NULL / IS NOT NULL.",
        },
        {
          question: "Что вернёт WHERE paid_at IS NOT NULL?",
          options: [
            "Платежи без даты оплаты",
            "Платежи с заполненной датой оплаты",
            "Все платежи",
            "Ни одного платежа",
          ],
          correctIndex: 1,
          explanation:
            "IS NOT NULL — обратная проверка: возвращает строки, где значение заполнено.",
        },
      ],
    },
  ],
};
