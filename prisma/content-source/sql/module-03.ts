import type { ModuleSeed } from "@/../prisma/content-source/types";

const schemaHint = `customers(customer_id, name, region, signup_date)
products(product_id, name, category, price)
orders(order_id, customer_id, product_id, quantity, order_date, status)
payments(payment_id, order_id, amount, paid_at, method)`;

export const module03: ModuleSeed = {
  slug: "module-03-aggregation",
  title: "Aggregation",
  description: "COUNT, SUM, AVG, MIN, MAX, GROUP BY, HAVING.",
  lessons: [
    {
      slug: "16-count",
      title: "COUNT",
      description: "Считает количество строк.",
      objectives: ["Считать строки с COUNT"],
      theory: `\`COUNT(*)\` считает количество строк в результате, \`COUNT(столбец)\` — количество непустых (не NULL) значений в столбце.

\`\`\`sql
SELECT COUNT(*) FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT COUNT(*) FROM orders WHERE status = 'cancelled';
\`\`\`

Посчитает количество отменённых заказов.`,
      commonMistakes: [
        "Путать COUNT(*) (все строки) с COUNT(column) (только непустые значения этого столбца).",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Количество клиентов",
        description: "Посчитай общее количество клиентов в таблице customers.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT COUNT(*) FROM customers;",
        },
        explanation: "COUNT(*) возвращает общее количество строк в таблице customers.",
      },
      quiz: [
        {
          question: "Чем COUNT(column) отличается от COUNT(*)?",
          options: [
            "Ничем, это одно и то же",
            "COUNT(column) не считает NULL-значения этого столбца",
            "COUNT(column) быстрее COUNT(*)",
            "COUNT(column) считает только уникальные значения",
          ],
          correctIndex: 1,
          explanation:
            "COUNT(column) игнорирует строки, где значение этого столбца NULL.",
        },
      ],
    },
    {
      slug: "17-sum",
      title: "SUM",
      description: "Суммирует значения числового столбца.",
      objectives: ["Считать сумму с помощью SUM"],
      theory: `\`SUM\` складывает все значения числового столбца в результирующем наборе строк.

\`\`\`sql
SELECT SUM(столбец) FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT SUM(amount) FROM payments;
\`\`\`

Посчитает суммарную сумму всех платежей.`,
      commonMistakes: [
        "Пытаться применить SUM к текстовому столбцу — СУБД вернёт ошибку типов.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Суммарные платежи",
        description:
          "Посчитай суммарную сумму (amount) всех платежей в таблице payments.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT SUM(amount) FROM payments;",
        },
        explanation: "SUM(amount) складывает значения столбца amount по всем строкам.",
      },
      quiz: [
        {
          question: "SUM игнорирует значения NULL в столбце?",
          options: [
            "Да",
            "Нет, они считаются как 0",
            "Запрос вызовет ошибку",
            "Зависит от СУБД",
          ],
          correctIndex: 0,
          explanation:
            "Как и большинство агрегатных функций, SUM пропускает NULL-значения.",
        },
      ],
    },
    {
      slug: "18-avg",
      title: "AVG",
      description: "Среднее значение числового столбца.",
      objectives: ["Считать среднее с помощью AVG"],
      theory: `\`AVG\` возвращает среднее арифметическое значений числового столбца, игнорируя NULL.

\`\`\`sql
SELECT AVG(столбец) FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT AVG(price) FROM products;
\`\`\`

Посчитает среднюю цену товара.`,
      commonMistakes: [
        "Ожидать целое число от AVG для integer-столбца — результат может быть дробным.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Средняя цена товара",
        description: "Посчитай среднюю цену (price) товаров в таблице products.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT AVG(price) FROM products;",
        },
        explanation: "AVG(price) делит сумму цен на количество товаров.",
      },
      quiz: [
        {
          question: "Может ли AVG вернуть дробное число для integer-столбца?",
          options: ["Да", "Нет, всегда округляется", "Только с ROUND", "Никогда"],
          correctIndex: 0,
          explanation:
            "AVG может вернуть дробный результат, даже если исходный столбец целочисленный.",
        },
      ],
    },
    {
      slug: "19-min-max",
      title: "MIN и MAX",
      description: "Минимальное и максимальное значение столбца.",
      objectives: ["Находить минимум и максимум с MIN/MAX"],
      theory: `\`MIN\` и \`MAX\` возвращают наименьшее и наибольшее значение столбца соответственно — работают и с числами, и с датами, и с текстом (по алфавиту).

\`\`\`sql
SELECT MIN(столбец), MAX(столбец) FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT MIN(price), MAX(price) FROM products;
\`\`\`

Вернёт самую низкую и самую высокую цену товара одним запросом.`,
      commonMistakes: [
        "Писать два отдельных запроса вместо одного с MIN и MAX в одном SELECT.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Диапазон цен",
        description: "Выбери минимальную и максимальную цену товаров одним запросом.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT MIN(price), MAX(price) FROM products;",
        },
        explanation: "MIN и MAX можно вычислить в одном SELECT через запятую.",
      },
      quiz: [
        {
          question: "Работают ли MIN/MAX с датами?",
          options: [
            "Нет, только с числами",
            "Да",
            "Только с текстом",
            "Только с булевыми значениями",
          ],
          correctIndex: 1,
          explanation:
            "MIN/MAX применимы к любому сравнимому типу: числам, датам, тексту.",
        },
      ],
    },
    {
      slug: "20-group-by",
      title: "GROUP BY",
      description: "Группировка строк для агрегации по категориям.",
      objectives: [
        "Группировать строки перед агрегацией",
        "Комбинировать GROUP BY с агрегатными функциями",
      ],
      theory: `\`GROUP BY\` разбивает строки на группы по значению одного или нескольких столбцов, и агрегатные функции (COUNT, SUM, AVG...) считаются отдельно для каждой группы.

\`\`\`sql
SELECT столбец, АГРЕГАТ(другой_столбец)
FROM таблица
GROUP BY столбец;
\`\`\`
`,
      example: `\`\`\`sql
SELECT category, AVG(price) AS avg_price
FROM products
GROUP BY category;
\`\`\`

Вернёт среднюю цену отдельно для каждой категории товаров.`,
      commonMistakes: [
        "Выбирать в SELECT столбец, не входящий ни в GROUP BY, ни в агрегатную функцию — СУБД вернёт ошибку.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Средняя цена по категориям",
        description:
          "Выведи category и среднюю цену (avg_price) товаров, сгруппировав по категории.",
        difficulty: "INTERMEDIATE",
        points: 25,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT category, AVG(price) AS avg_price FROM products GROUP BY category;",
        },
        explanation:
          "GROUP BY category считает AVG(price) отдельно для каждой уникальной категории.",
      },
      quiz: [
        {
          question: "Что должно быть в SELECT, если используется GROUP BY?",
          options: [
            "Любые столбцы",
            "Только столбцы из GROUP BY и агрегатные функции",
            "Только агрегатные функции",
            "Только столбцы из WHERE",
          ],
          correctIndex: 1,
          explanation:
            "Не сгруппированные и не агрегированные столбцы в SELECT вызывают ошибку.",
        },
        {
          question: "В каком порядке выполняются WHERE и GROUP BY?",
          options: [
            "Сначала GROUP BY, потом WHERE",
            "Сначала WHERE, потом GROUP BY",
            "Одновременно",
            "Порядка нет",
          ],
          correctIndex: 1,
          explanation:
            "WHERE фильтрует строки до группировки; для фильтрации после группировки нужен HAVING.",
        },
      ],
    },
    {
      slug: "21-having",
      title: "HAVING",
      description: "Фильтрация групп после агрегации.",
      objectives: ["Фильтровать результаты GROUP BY через HAVING"],
      theory: `\`HAVING\` фильтрует группы **после** агрегации — в отличие от WHERE, которая фильтрует строки до группировки. HAVING может ссылаться на результат агрегатной функции.

\`\`\`sql
SELECT столбец, АГРЕГАТ(...)
FROM таблица
GROUP BY столбец
HAVING АГРЕГАТ(...) > значение;
\`\`\`
`,
      example: `\`\`\`sql
SELECT category, AVG(price) AS avg_price
FROM products
GROUP BY category
HAVING AVG(price) > 1000;
\`\`\`

Вернёт только те категории, средняя цена товаров в которых выше 1000.`,
      commonMistakes: [
        "Пытаться использовать агрегатную функцию в WHERE вместо HAVING — это вызовет ошибку.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Дорогие категории",
        description:
          "Выведи category и среднюю цену (avg_price), оставив только категории со средней ценой выше 1000.",
        difficulty: "ADVANCED",
        points: 30,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery:
            "SELECT category, AVG(price) AS avg_price FROM products GROUP BY category HAVING AVG(price) > 1000;",
        },
        explanation:
          "HAVING AVG(price) > 1000 фильтрует уже сгруппированные и агрегированные результаты.",
      },
      quiz: [
        {
          question: "В чём главное отличие HAVING от WHERE?",
          options: [
            "HAVING работает до группировки, а WHERE — после",
            "HAVING фильтрует группы после агрегации, WHERE — строки до неё",
            "Это полные синонимы",
            "HAVING работает только с текстом",
          ],
          correctIndex: 1,
          explanation:
            "WHERE фильтрует исходные строки, HAVING — уже сгруппированные и агрегированные результаты.",
        },
      ],
    },
  ],
};
