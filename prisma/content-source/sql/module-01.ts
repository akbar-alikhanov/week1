import type { ModuleSeed } from "@/../prisma/content-source/types";

const schemaHint = `customers(customer_id, name, region, signup_date)
products(product_id, name, category, price)
orders(order_id, customer_id, product_id, quantity, order_date, status)
payments(payment_id, order_id, amount, paid_at, method)`;

export const module01: ModuleSeed = {
  slug: "module-01-sql-basics",
  title: "SQL Basics",
  description: "Что такое SQL, базы данных, таблицы, ключи, SELECT/FROM/WHERE.",
  lessons: [
    {
      slug: "01-what-is-sql",
      title: "Что такое SQL",
      description: "Язык запросов к реляционным базам данных.",
      objectives: ["Объяснить, зачем нужен SQL", "Назвать основные категории SQL-команд"],
      theory: `SQL (Structured Query Language) — язык для работы с реляционными базами данных: чтения, изменения и структурирования данных. SQL делится на подъязыки: **DQL** (запросы, SELECT), **DML** (изменение данных: INSERT/UPDATE/DELETE), **DDL** (структура: CREATE/ALTER/DROP).

В этом курсе мы фокусируемся на DQL — чтении и анализе данных с помощью SELECT.`,
      example: `\`\`\`sql
SELECT name, region
FROM customers;
\`\`\`

Простейший запрос: выбрать столбцы \`name\` и \`region\` из таблицы \`customers\`.`,
      commonMistakes: [
        "Путать SQL (язык запросов) с конкретной СУБД (PostgreSQL, MySQL и т.д.) — SQL один, диалекты немного отличаются.",
      ],
      exercise: {
        type: "MULTIPLE_CHOICE",
        title: "Категории SQL",
        description: "К какой категории SQL относится команда SELECT?",
        difficulty: "BEGINNER",
        points: 10,
        data: { type: "MULTIPLE_CHOICE", options: ["DDL", "DML", "DQL", "TCL"] },
        correctAnswer: { type: "MULTIPLE_CHOICE", correctIndices: [2] },
        explanation:
          "SELECT относится к DQL — языку запросов данных (Data Query Language).",
      },
      quiz: [
        {
          question: "Что расшифровывается как SQL?",
          options: [
            "Structured Query Language",
            "Simple Query Logic",
            "System Query List",
            "Standard Quality Language",
          ],
          correctIndex: 0,
          explanation:
            "SQL — Structured Query Language, язык структурированных запросов.",
        },
        {
          question: "К какой категории относится команда CREATE TABLE?",
          options: ["DQL", "DML", "DDL", "DCL"],
          correctIndex: 2,
          explanation:
            "CREATE, ALTER, DROP — команды DDL (Data Definition Language), меняющие структуру.",
        },
        {
          question:
            "Какая категория SQL отвечает за изменение данных (INSERT/UPDATE/DELETE)?",
          options: ["DQL", "DML", "DDL", "DCL"],
          correctIndex: 1,
          explanation:
            "DML (Data Manipulation Language) изменяет сами данные, а не структуру.",
        },
      ],
    },
    {
      slug: "02-databases",
      title: "Базы данных",
      description: "Что такое реляционная база данных.",
      objectives: ["Объяснить понятие реляционной базы данных"],
      theory: `Реляционная база данных хранит данные в виде связанных таблиц. Связи между таблицами строятся через ключи (например, \`customer_id\` в таблице заказов ссылается на клиента). Это позволяет избегать дублирования данных и поддерживать их согласованность.`,
      example: `В нашей учебной базе четыре связанные таблицы: \`customers\`, \`products\`, \`orders\`, \`payments\`. Каждый заказ (\`orders\`) ссылается на клиента и товар, а каждый платёж (\`payments\`) — на заказ.`,
      commonMistakes: [
        "Хранить одни и те же данные (например, имя клиента) в нескольких таблицах вместо ссылки по ключу.",
      ],
      exercise: {
        type: "TRUE_FALSE",
        title: "Связи между таблицами",
        description:
          "В реляционной базе данных таблицы могут быть связаны между собой через ключи.",
        difficulty: "BEGINNER",
        points: 10,
        data: { type: "TRUE_FALSE" },
        correctAnswer: { type: "TRUE_FALSE", value: true },
        explanation:
          "Именно связи через ключи и делают базу данных «реляционной» (relational).",
      },
      quiz: [
        {
          question: "Зачем нужны связи между таблицами?",
          options: [
            "Чтобы избежать дублирования данных",
            "Чтобы ускорить запуск СУБД",
            "Чтобы уменьшить количество таблиц до одной",
            "Это не обязательно",
          ],
          correctIndex: 0,
          explanation:
            "Связи позволяют хранить данные один раз и ссылаться на них, а не дублировать.",
        },
        {
          question: "Сколько таблиц в нашей учебной базе данных?",
          options: ["2", "3", "4", "5"],
          correctIndex: 2,
          explanation: "customers, products, orders, payments — четыре таблицы.",
        },
      ],
    },
    {
      slug: "03-tables",
      title: "Таблицы",
      description: "Строки, столбцы и структура таблицы.",
      objectives: ["Объяснить структуру таблицы: строки, столбцы, типы данных"],
      theory: `Таблица состоит из **столбцов** (каждый со своим именем и типом данных: текст, число, дата) и **строк** — отдельных записей. Например, таблица \`products\` имеет столбцы \`product_id\`, \`name\`, \`category\`, \`price\`, а каждая строка — конкретный товар.`,
      example: `\`\`\`sql
SELECT * FROM products;
\`\`\`

\`*\` означает «все столбцы» — запрос вернёт все строки таблицы products со всеми её столбцами.`,
      commonMistakes: [
        "Использовать SELECT * в реальных отчётах — лучше явно перечислять нужные столбцы.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Выбери все товары",
        description:
          "Напиши запрос, который выбирает все столбцы и все строки таблицы products.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: { type: "SQL_QUERY", referenceQuery: "SELECT * FROM products;" },
        explanation:
          "SELECT * FROM products; возвращает все столбцы и строки таблицы products.",
      },
      quiz: [
        {
          question: "Что означает * в SELECT * FROM products?",
          options: ["Умножение", "Все столбцы", "Первая строка", "Ошибка синтаксиса"],
          correctIndex: 1,
          explanation: "* — специальный символ, означающий «выбрать все столбцы».",
        },
      ],
    },
    {
      slug: "04-primary-key",
      title: "Primary Key",
      description: "Уникальный идентификатор строки в таблице.",
      objectives: ["Объяснить назначение первичного ключа"],
      theory: `**Primary Key** (первичный ключ) — столбец (или набор столбцов), который однозначно идентифицирует каждую строку таблицы. Значения первичного ключа уникальны и не могут быть NULL. Например, \`customer_id\` в таблице \`customers\`.`,
      example: `В таблице \`customers\` столбец \`customer_id\` — первичный ключ: каждый клиент имеет свой уникальный номер, и по нему легко находить конкретного клиента.`,
      commonMistakes: [
        "Выбирать в качестве первичного ключа столбец, значения которого могут повторяться (например, имя клиента).",
      ],
      exercise: {
        type: "MULTIPLE_CHOICE",
        title: "Первичный ключ",
        description: "Какое из свойств обязательно для Primary Key?",
        difficulty: "BEGINNER",
        points: 10,
        data: {
          type: "MULTIPLE_CHOICE",
          options: [
            "Может повторяться",
            "Может быть NULL",
            "Уникален для каждой строки",
            "Всегда текстовый",
          ],
        },
        correctAnswer: { type: "MULTIPLE_CHOICE", correctIndices: [2] },
        explanation: "Primary Key обязан быть уникальным и не может быть NULL.",
      },
      quiz: [
        {
          question: "Может ли Primary Key содержать значение NULL?",
          options: ["Да, всегда", "Нет, никогда", "Только один раз", "Зависит от СУБД"],
          correctIndex: 1,
          explanation:
            "Primary Key никогда не может быть NULL — иначе строку нельзя однозначно идентифицировать.",
        },
      ],
    },
    {
      slug: "05-foreign-key",
      title: "Foreign Key",
      description: "Ссылка на первичный ключ другой таблицы.",
      objectives: [
        "Объяснить назначение внешнего ключа",
        "Находить внешние ключи в схеме",
      ],
      theory: `**Foreign Key** (внешний ключ) — столбец, значения которого ссылаются на Primary Key другой таблицы, устанавливая связь между ними. Например, \`orders.customer_id\` — внешний ключ, ссылающийся на \`customers.customer_id\`.`,
      example: `В таблице \`orders\` столбцы \`customer_id\` и \`product_id\` — внешние ключи, ссылающиеся на \`customers\` и \`products\` соответственно. Это и позволяет соединять (JOIN) заказы с клиентами и товарами.`,
      commonMistakes: [
        "Путать Foreign Key с Primary Key той же таблицы — это ссылка на ключ ДРУГОЙ таблицы.",
      ],
      exercise: {
        type: "TEXT_INPUT",
        title: "Найди внешний ключ",
        description:
          "В таблице orders(order_id, customer_id, product_id, quantity, order_date, status) какой столбец ссылается на таблицу customers? Введи имя столбца.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "TEXT_INPUT" },
        correctAnswer: { type: "TEXT_INPUT", acceptedAnswers: ["customer_id"] },
        explanation:
          "customer_id в таблице orders — внешний ключ, ссылающийся на customers.customer_id.",
      },
      quiz: [
        {
          question: "На что ссылается Foreign Key?",
          options: [
            "На случайный столбец",
            "На Primary Key другой таблицы",
            "На саму себя",
            "На имя таблицы",
          ],
          correctIndex: 1,
          explanation:
            "Foreign Key всегда ссылается на Primary Key (или уникальный ключ) другой таблицы.",
        },
      ],
    },
    {
      slug: "06-select",
      title: "SELECT",
      description: "Выбор столбцов из таблицы.",
      objectives: ["Писать простые SELECT-запросы", "Выбирать конкретные столбцы"],
      theory: `\`SELECT\` определяет, какие столбцы вернуть в результате запроса. Можно перечислить конкретные столбцы через запятую или использовать \`*\` для всех столбцов.

\`\`\`sql
SELECT столбец1, столбец2 FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT name, category, price FROM products;
\`\`\`

Вернёт только три столбца: name, category, price — без остальных.`,
      commonMistakes: [
        "Забывать точку с запятой в конце запроса (в большинстве СУБД это не обязательно, но хорошая привычка).",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Выбери имя и цену товаров",
        description:
          "Напиши запрос, который выбирает столбцы name и price из таблицы products.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT name, price FROM products;",
        },
        explanation:
          "SELECT name, price FROM products; возвращает только эти два столбца.",
      },
      additionalExercises: [
        {
          type: "SQL_QUERY",
          title: "Выбери имена клиентов",
          description:
            "Напиши запрос, который выбирает только столбец name из таблицы customers.",
          difficulty: "BEGINNER",
          points: 15,
          data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
          correctAnswer: {
            type: "SQL_QUERY",
            referenceQuery: "SELECT name FROM customers;",
          },
          explanation:
            "SELECT name FROM customers; возвращает один столбец name для всех клиентов.",
        },
        {
          type: "SQL_QUERY",
          title: "Выбери статусы заказов",
          description:
            "Напиши запрос, который выбирает order_id и status из таблицы orders.",
          difficulty: "BEGINNER",
          points: 15,
          data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
          correctAnswer: {
            type: "SQL_QUERY",
            referenceQuery: "SELECT order_id, status FROM orders;",
          },
          explanation:
            "SELECT order_id, status FROM orders; возвращает id и статус каждого заказа.",
        },
      ],
      quiz: [
        {
          question: "Что делает SELECT * FROM orders?",
          options: [
            "Удаляет таблицу orders",
            "Возвращает все столбцы и строки orders",
            "Возвращает только первую строку",
            "Создаёт копию таблицы orders",
          ],
          correctIndex: 1,
          explanation: "SELECT * возвращает все столбцы указанной таблицы.",
        },
        {
          question: "Как выбрать только столбцы name и price?",
          options: [
            "SELECT name AND price FROM products",
            "SELECT name, price FROM products",
            "SELECT name; price FROM products",
            "SELECT [name, price] FROM products",
          ],
          correctIndex: 1,
          explanation: "Столбцы перечисляются через запятую после SELECT.",
        },
        {
          question: "SELECT — команда какой категории SQL?",
          options: ["DDL", "DQL", "DML", "DCL"],
          correctIndex: 1,
          explanation: "SELECT — команда чтения данных, относится к DQL.",
        },
      ],
    },
    {
      slug: "07-from",
      title: "FROM",
      description: "Указываем источник данных для запроса.",
      objectives: ["Указывать таблицу-источник в FROM"],
      theory: `\`FROM\` указывает, из какой таблицы (или нескольких таблиц, при JOIN) брать данные. Без FROM запрос SELECT не будет знать, откуда читать строки.

\`\`\`sql
SELECT столбцы FROM таблица;
\`\`\`
`,
      example: `\`\`\`sql
SELECT * FROM payments;
\`\`\`

FROM payments указывает, что данные читаются из таблицы payments.`,
      commonMistakes: [
        "Указывать неверное имя таблицы или опечатку — СУБД вернёт ошибку «relation does not exist».",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Выбери все платежи",
        description: "Напиши запрос, который выбирает все столбцы из таблицы payments.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: { type: "SQL_QUERY", referenceQuery: "SELECT * FROM payments;" },
        explanation:
          "SELECT * FROM payments; читает все столбцы и строки из таблицы payments.",
      },
      quiz: [
        {
          question: "Что произойдёт, если в FROM указать несуществующую таблицу?",
          options: [
            "Запрос вернёт пустой результат",
            "СУБД вернёт ошибку",
            "Запрос выполнится частично",
            "Ничего не произойдёт",
          ],
          correctIndex: 1,
          explanation:
            "СУБД вернёт ошибку о том, что такой таблицы (relation) не существует.",
        },
      ],
    },
    {
      slug: "08-where",
      title: "WHERE",
      description: "Фильтрация строк по условию.",
      objectives: [
        "Фильтровать строки с помощью WHERE",
        "Использовать операторы сравнения",
      ],
      theory: `\`WHERE\` фильтрует строки, оставляя только те, что удовлетворяют условию. Условие может использовать операторы сравнения: \`=\`, \`!=\`, \`>\`, \`<\`, \`>=\`, \`<=\`.

\`\`\`sql
SELECT столбцы FROM таблица WHERE условие;
\`\`\`
`,
      example: `\`\`\`sql
SELECT name, price FROM products WHERE price > 1000;
\`\`\`

Вернёт только товары дороже 1000.`,
      commonMistakes: [
        "Использовать = для сравнения с NULL — для этого нужен IS NULL, а не WHERE column = NULL.",
      ],
      exercise: {
        type: "SQL_QUERY",
        title: "Дорогие товары",
        description: "Напиши запрос, который выбирает name и price товаров дороже 1000.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
        correctAnswer: {
          type: "SQL_QUERY",
          referenceQuery: "SELECT name, price FROM products WHERE price > 1000;",
        },
        explanation:
          "WHERE price > 1000 оставляет только строки, где значение price больше 1000.",
      },
      additionalExercises: [
        {
          type: "SQL_QUERY",
          title: "Клиенты региона North",
          description:
            "Напиши запрос, который выбирает всех клиентов (все столбцы) из региона 'North'.",
          difficulty: "INTERMEDIATE",
          points: 20,
          data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
          correctAnswer: {
            type: "SQL_QUERY",
            referenceQuery: "SELECT * FROM customers WHERE region = 'North';",
          },
          explanation:
            "WHERE region = 'North' оставляет только клиентов из этого региона.",
        },
        {
          type: "SQL_QUERY",
          title: "Отменённые заказы",
          description:
            "Напиши запрос, который выбирает order_id всех заказов со статусом 'cancelled'.",
          difficulty: "INTERMEDIATE",
          points: 20,
          data: { type: "SQL_QUERY", datasetId: "shop", schemaHint },
          correctAnswer: {
            type: "SQL_QUERY",
            referenceQuery: "SELECT order_id FROM orders WHERE status = 'cancelled';",
          },
          explanation: "WHERE status = 'cancelled' фильтрует только отменённые заказы.",
        },
      ],
      quiz: [
        {
          question: "Какой оператор используется для проверки на NULL?",
          options: ["= NULL", "IS NULL", "== NULL", "LIKE NULL"],
          correctIndex: 1,
          explanation:
            "Для проверки на NULL используется специальный оператор IS NULL (или IS NOT NULL).",
        },
        {
          question: "Что вернёт WHERE price >= 1000?",
          options: [
            "Только строки со значением строго больше 1000",
            "Строки со значением 1000 и больше",
            "Строки со значением меньше 1000",
            "Все строки",
          ],
          correctIndex: 1,
          explanation: ">= включает и само значение 1000, и всё, что больше.",
        },
        {
          question: "В каком порядке выполняются FROM и WHERE логически?",
          options: [
            "Сначала WHERE, потом FROM",
            "Сначала FROM, потом WHERE",
            "Одновременно",
            "Порядка не существует",
          ],
          correctIndex: 1,
          explanation:
            "Логически сначала определяется источник данных (FROM), затем к нему применяется фильтр (WHERE).",
        },
      ],
    },
  ],
};
